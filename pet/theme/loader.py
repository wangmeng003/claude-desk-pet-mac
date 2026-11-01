# 主题包校验与加载（M4，specs/theme.md §5 校验 / §6 安全 / §3 状态映射）。
# 纯函数 + 只读：不写文件、不联网、不执行任何包内内容；装/切/删在 manager.py。
# 只允许 stdlib：图片校验到魔数字节 + 头部尺寸为止，完整解码交给渲染层
# （渲染层解不开就回退内置，spec §5.3——坏图不能崩桌宠）。
import json
import os
import re
import stat

from core.models import PROTOCOL_STATES

THEME_FILE = 'pet.json'
SCHEMA = 1
MAX_JSON = 64 * 1024          # pet.json 上限（§5.2）
MAX_PACK = 20 * 1024 * 1024   # 单包解压后上限（§5.2 建议值）
MAX_FILES = 200               # 文件数上限（§5.2）
MAX_IMAGE_DIM = 4096          # 单张图边长上限（§5.2）
MIN_FRAME, MAX_FRAME = 32, 1024  # 帧尺寸范围（§5.1）
MAX_SOUND = 2 * 1024 * 1024   # 单个音频上限（§5.2）
ALLOWED_SUFFIX = {'.json', '.png', '.webp', '.wav', '.mp3'}  # §6：只允许数据文件
ID_RE = re.compile(r'^[a-z0-9_-]{1,64}$')

# Petdex/Codex 行名 → 本项目状态（§3.2）。idle/waiting 同名直通，不在此表。
PETDEX_ROWS = {
    'running': 'tool',
    'running-left': 'tool',   # 方向动画行：本项目不区分方向，与 running 同待遇
    'running-right': 'tool',
    'review': 'reading',
    'jumping': 'celebrate',
    'waving': 'attention',
    'failed': 'error',
}
# 缺状态回退（§3.2）：attention/celebrate → waiting，其余 → idle。
FALLBACK = {'attention': 'waiting', 'celebrate': 'waiting'}


class ThemeError(Exception):
    """校验失败；message 面向用户（/pet theme 直接回显）。"""


def canon_state_key(key):
    """manifest states 的键 → 协议状态；未知键返回 None（忽略，不报错）。"""
    if key in PROTOCOL_STATES:
        return key
    return PETDEX_ROWS.get(key)


class ThemePack:
    """加载完成、可直接给渲染层用的主题包。

    frames: 协议状态 → (图片绝对路径, 帧矩形或 None)。网格布局存第一帧
    （帧动画后续再接，先保证「换装」闭环）；单图布局 rect 为 None。
    sounds: 'done'/'error' → 音频绝对路径（可能缺）。
    """

    def __init__(self, root, theme_id, name, author, license, layout,
                 frames, sounds, warnings=(), frame_size=None):
        self.root = root
        self.theme_id = theme_id
        self.name = name
        self.author = author
        self.license = license
        self.layout = layout
        self.frames = frames
        self.sounds = sounds
        self.warnings = tuple(warnings)
        self.frame_size = frame_size  # 网格布局的 (w, h)；单图为 None

    def image_for(self, state):
        """状态 → (路径, 帧矩形)；按 §3.2 沿回退链走到底。

        attention/celebrate 先退 waiting，waiting 也没有就退 idle——只画 idle
        的极简包也能覆盖全部状态。渲染层彩蛋（stone 等）不进主题。
        """
        if state not in PROTOCOL_STATES:
            return None
        chain = [state]
        if state in FALLBACK:
            chain.append(FALLBACK[state])
        if state != 'idle':
            chain.append('idle')
        for key in chain:
            ref = self.frames.get(key)
            if ref is not None:
                return ref
        return None

    def coverage_text(self):
        """info 用：8 状态各自是「直出 / 回退到 x / 内置」。"""
        rows = []
        for state in PROTOCOL_STATES:
            if state in self.frames:
                rows.append(f'{state} ✓')
            elif FALLBACK.get(state, 'idle') in self.frames:
                rows.append(f'{state} → {FALLBACK.get(state, "idle")}')
            else:
                rows.append(f'{state} → 内置')
        return '、'.join(rows)


# ---------- 路径安全（§6） ----------

def resolve_in_theme(base, rel):
    """主题内相对路径 → 绝对路径；拒绝绝对路径、..、~、符号链接（含祖先目录）。"""
    if not isinstance(rel, str) or not rel.strip():
        raise ThemeError(f'路径不合法：{rel!r}')
    norm = rel.strip().replace('\\', '/')
    if norm.startswith('/') or norm.startswith('~'):
        raise ThemeError(f'不允许绝对路径：{rel}')
    drive = os.path.splitdrive(norm)[0]
    if drive:
        raise ThemeError(f'不允许绝对路径：{rel}')
    parts = [p for p in norm.split('/') if p not in ('', '.')]
    if not parts:
        raise ThemeError(f'路径不合法：{rel!r}')
    if any(p == '..' for p in parts):
        raise ThemeError(f'路径不允许包含 ..：{rel}')
    target = os.path.join(base, *parts)
    # 祖先链上任何一级是符号链接都拒绝：realpath 只能兜底最终落点，链路要逐级看
    acc = base
    for p in parts:
        acc = os.path.join(acc, p)
        if os.path.islink(acc):
            raise ThemeError(f'不允许符号链接：{rel}')
    if os.path.commonpath([os.path.realpath(base), os.path.realpath(target)]) \
            != os.path.realpath(base):
        raise ThemeError(f'路径逃出主题目录：{rel}')
    return target


def _magic_ok(path, suffix):
    """按魔数字节确认文件类型（§6 渲染安全：只当纹理画，先别让假图片进来）。"""
    try:
        with open(path, 'rb') as f:
            head = f.read(16)
    except OSError:
        return False
    if suffix == '.png':
        return head.startswith(b'\x89PNG\r\n\x1a\n')
    if suffix == '.webp':
        return head[:4] == b'RIFF' and head[8:12] == b'WEBP'
    if suffix == '.wav':
        return head[:4] == b'RIFF' and head[8:12] == b'WAVE'
    if suffix == '.mp3':
        return head[:3] == b'ID3' or (len(head) >= 2 and head[0] == 0xFF
                                      and head[1] & 0xE0 == 0xE0)
    return suffix == '.json'


def _png_dims(path):
    """PNG 头部宽高（IHDR 在固定偏移）；读不出返回 None（跳过尺寸校验）。

    WebP 的头有多种 chunk 布局，不值得在 stdlib 里解析——尺寸校验只覆盖 PNG。
    """
    try:
        with open(path, 'rb') as f:
            head = f.read(33)
    except OSError:
        return None
    if not head.startswith(b'\x89PNG\r\n\x1a\n') or len(head) < 24:
        return None
    if head[12:16] != b'IHDR':
        return None
    return int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')


# ---------- 目录级检查（§5.2 资源限制 / §6 只允许数据） ----------

def walk_checks(theme_dir):
    """全包扫描：文件数/总大小上限、后缀白名单、拒绝符号链接和特殊文件。

    硬链接不查：st_nlink>1 区分不了「包内正常复制」和「指向包外的硬链接」，
    包内文件不会被执行，风险只在泄露——zip 安装路径已按条目校验，目录安装
    保持简单。已安装目录同样会再走一遍本检查。
    """
    count, total = 0, 0
    for root, dirs, files in os.walk(theme_dir):
        for name in dirs:
            if os.path.islink(os.path.join(root, name)):
                raise ThemeError(f'不允许符号链接目录：{name}')
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path):
                raise ThemeError(f'不允许符号链接：{name}')
            st = os.stat(path)
            if not stat.S_ISREG(st.st_mode):
                raise ThemeError(f'不允许特殊文件：{name}')
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in ALLOWED_SUFFIX:
                raise ThemeError(
                    f'不允许的文件类型 {suffix or "(无后缀)"}：{name}'
                    f'（只允许 {"、".join(sorted(ALLOWED_SUFFIX))}）')
            count += 1
            if count > MAX_FILES:
                raise ThemeError(f'文件数超过上限（{MAX_FILES}）')
            total += st.st_size
            if total > MAX_PACK:
                raise ThemeError(f'主题包总大小超过上限（{MAX_PACK // 1024 // 1024}MB）')


# ---------- manifest 校验 ----------

def _require_str(m, key, max_len):
    val = m.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ThemeError(f'pet.json 缺少必填字段 {key}')
    if len(val) > max_len:
        raise ThemeError(f'pet.json 的 {key} 超过 {max_len} 字符')
    return val.strip()


def _validate_frame_spec(m):
    """网格布局的 frame 段；返回 (w, h, columns, rows)。"""
    frame = m.get('frame')
    if not isinstance(frame, dict):
        raise ThemeError('网格布局缺少 frame 段（width/height/columns/rows）')
    vals = {}
    for key in ('width', 'height', 'columns', 'rows'):
        v = frame.get(key)
        if isinstance(v, bool) or not isinstance(v, int):
            raise ThemeError(f'frame.{key} 必须是整数')
        vals[key] = v
    if not (MIN_FRAME <= vals['width'] <= MAX_FRAME
            and MIN_FRAME <= vals['height'] <= MAX_FRAME):
        raise ThemeError(
            f'帧尺寸必须在 {MIN_FRAME}–{MAX_FRAME} px'
            f'（当前 {vals["width"]}x{vals["height"]}）')
    if vals['columns'] < 1 or vals['rows'] < 1:
        raise ThemeError('frame.columns/rows 必须 ≥ 1')
    return vals['width'], vals['height'], vals['columns'], vals['rows']


def _resolve_image(base, rel):
    """单图布局的一张图：路径安全 + 存在 + 魔数 + PNG 尺寸上限。"""
    path = resolve_in_theme(base, rel)
    if not os.path.isfile(path):
        raise ThemeError(f'图片不存在：{rel}')
    if os.path.splitext(path)[1].lower() not in ('.png', '.webp'):
        raise ThemeError(f'图片必须是 PNG/WebP：{rel}')
    if not _magic_ok(path, os.path.splitext(path)[1].lower()):
        raise ThemeError(f'不是有效的 PNG/WebP 文件：{rel}')
    dims = _png_dims(path)
    if dims and max(dims) > MAX_IMAGE_DIM:
        raise ThemeError(f'图片超过 {MAX_IMAGE_DIM}x{MAX_IMAGE_DIM}：{rel}')
    return path


def _resolve_sound(base, rel):
    path = resolve_in_theme(base, rel)
    if not os.path.isfile(path):
        raise ThemeError(f'音频不存在：{rel}')
    if os.path.splitext(path)[1].lower() not in ('.wav', '.mp3'):
        raise ThemeError(f'音频必须是 WAV/MP3：{rel}')
    if os.path.getsize(path) > MAX_SOUND:
        raise ThemeError(f'音频超过 {MAX_SOUND // 1024 // 1024}MB：{rel}')
    if not _magic_ok(path, os.path.splitext(path)[1].lower()):
        raise ThemeError(f'不是有效的 WAV/MP3 文件：{rel}')
    return path


def validate_manifest(m, base):
    """校验 manifest 并解析出全部资源引用。

    返回 (字段 dict, frames, sounds, warnings, frame_size)；frame_size 只有
    网格布局有（帧矩形要靠它算，单图布局为 None）。
    """
    if not isinstance(m, dict):
        raise ThemeError('pet.json 不是 JSON 对象')
    if m.get('schema') != SCHEMA:
        raise ThemeError(f'不支持的 schema 版本：{m.get("schema")!r}（当前只支持 {SCHEMA}）')
    theme_id = _require_str(m, 'id', 64)
    if not ID_RE.match(theme_id):
        raise ThemeError('id 只允许小写字母/数字/-/_，最长 64 字符')
    name = _require_str(m, 'name', 80)
    license_ = _require_str(m, 'license', 64)
    warnings = []
    if license_.lower() == 'unknown':
        warnings.append('license 是 unknown——确认素材来源后再分发')
    layout = m.get('layout')
    if layout not in ('spritesheet', 'states'):
        raise ThemeError(f'layout 必须是 spritesheet 或 states（当前 {layout!r}）')

    states = m.get('states')
    if not isinstance(states, dict) or not states:
        raise ThemeError('pet.json 缺少 states 段')
    frames, frame_size = {}, None
    if layout == 'spritesheet':
        w, h, columns, rows = _validate_frame_spec(m)
        frame_size = (w, h)
        sheet_rel = m.get('image', 'spritesheet.png')
        sheet = _resolve_image(base, sheet_rel)
        for raw_key, indices in states.items():
            key = canon_state_key(raw_key)
            if key is None:
                warnings.append(f'未知状态 {raw_key!r} 已忽略')
                continue
            if isinstance(indices, int):
                indices = [indices]
            if not isinstance(indices, list) or not indices \
                    or any(isinstance(i, bool) or not isinstance(i, int) for i in indices):
                raise ThemeError(f'states.{raw_key} 必须是非空帧索引数组')
            for i in indices:
                if not 0 <= i < columns * rows:
                    raise ThemeError(
                        f'帧索引越界：states.{raw_key} 里的 {i}'
                        f'（网格只有 {columns}x{rows}={columns * rows} 帧）')
            if key not in frames:  # 同状态多次出现取第一组（方向行等价，谁先谁算）
                col, row = indices[0] % columns, indices[0] // columns
                frames[key] = (sheet, (col * w, row * h, w, h))
    else:
        for raw_key, rel in states.items():
            key = canon_state_key(raw_key)
            if key is None:
                warnings.append(f'未知状态 {raw_key!r} 已忽略')
                continue
            frames[key] = (_resolve_image(base, rel), None)

    if 'idle' not in frames:
        raise ThemeError('states 至少要有 idle（spec §5.1）')

    sounds = {}
    raw_sounds = m.get('sounds')
    if raw_sounds is not None:
        if not isinstance(raw_sounds, dict):
            raise ThemeError('sounds 必须是对象')
        for key, rel in raw_sounds.items():
            if key not in ('done', 'error'):
                warnings.append(f'未知音频 {key!r} 已忽略')
                continue
            sounds[key] = _resolve_sound(base, rel)

    preview = m.get('preview')
    if preview is not None:
        _resolve_image(base, preview)  # 只校验可达，不进 ThemePack（预览图 M4 可选）

    fields = {'id': theme_id, 'name': name, 'author': str(m.get('author') or ''),
              'license': license_, 'layout': layout}
    return fields, frames, sounds, warnings, frame_size


# ---------- 入口 ----------

def load_pack(theme_dir):
    """加载并校验一个主题目录；任何问题抛 ThemeError（调用方决定回退）。"""
    theme_dir = os.fspath(theme_dir)  # Path 进来时保证后续 join 出的是 str
    manifest_path = os.path.join(theme_dir, THEME_FILE)
    if not os.path.isfile(manifest_path):
        raise ThemeError(f'缺少 {THEME_FILE}')
    if os.path.getsize(manifest_path) > MAX_JSON:
        raise ThemeError(f'{THEME_FILE} 超过 {MAX_JSON // 1024}KB')
    try:
        with open(manifest_path, encoding='utf-8') as f:
            m = json.load(f)
    except (OSError, ValueError) as err:
        raise ThemeError(f'{THEME_FILE} 读不出来：{err}') from err
    walk_checks(theme_dir)
    fields, frames, sounds, warnings, frame_size = validate_manifest(m, theme_dir)
    fields['theme_id'] = fields.pop('id')  # manifest 字段名 id → ThemePack.theme_id
    return ThemePack(theme_dir, **fields, frames=frames, sounds=sounds,
                     warnings=warnings, frame_size=frame_size)


def load_active(themes_dir, theme_id):
    """渲染层入口：当前主题加载失败一律回 None（回退内置，绝不崩桌宠，§5.3）。"""
    if not theme_id or theme_id == 'builtin':
        return None
    try:
        return load_pack(os.path.join(themes_dir, theme_id))
    except Exception:  # 主题坏了不能比主题坏了更糟：记 debug 由调用方处理，这里只回退
        return None


def sound_path(pack, name, builtin_dir, wav_only=False):
    """提示音解析：主题音优先；缺/不合平台格式回退内置 sounds/。

    wav_only 给 Windows（winsound 只吃 WAV）：主题是 mp3 时直接用内置的。
    """
    if pack is not None:
        p = pack.sounds.get(name)
        if p and not (wav_only and not p.lower().endswith('.wav')):
            return p
    return os.path.join(builtin_dir, name + '.wav')
