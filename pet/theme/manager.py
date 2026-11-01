# 主题包管理（M4，specs/theme.md §4）：install / use / remove / list / info。
# 全部走 run_dir（默认 ~/.claude/desk-pet）：主题在 <run_dir>/themes/<id>/，
# 当前主题记在 settings.json 的 theme 字段（''/'builtin' = 内置皮肤）。
# 校验复用 loader；本模块只做文件系统变更，命令行入口在 theme_cli.py。
import os
import shutil
import tempfile
import zipfile

from core import state_reader

from . import loader
from .loader import ThemeError  # noqa: F401  (theme_cli 捕获用：from theme.manager import ThemeError)

BUILTIN = 'builtin'

USAGE = '''用法：theme_cli.py <命令> [参数…] <运行目录>
命令：
  list                      列出已安装的主题
  install <路径> [--force]  安装主题包（目录或 zip）；已存在时 --force 覆盖
  use <id|builtin>          切换主题；builtin = 内置皮肤
  remove <id>               删除主题（使用中的要先切走）
  info <id>                 查看主题详情'''


def themes_dir(run_dir):
    return os.path.join(run_dir, 'themes')


def _settings_path(run_dir):
    return os.path.join(run_dir, 'settings.json')


def _load_settings(run_dir):
    return state_reader.load_settings(_settings_path(run_dir))


def _save_settings(run_dir, settings):
    state_reader.save_settings(_settings_path(run_dir), settings)


def active_id(run_dir):
    theme = _load_settings(run_dir).get('theme')
    return theme if isinstance(theme, str) and theme else BUILTIN


# ---------- 安装 ----------

def _safe_unzip(zip_path, dest):
    """防 zip bomb / 路径穿越 / 符号链接条目（spec §5.2/§6）：逐条校验再解压。"""
    total, count = 0, 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace('\\', '/')
            if name.startswith('/') or ':' in name.split('/')[0] \
                    or any(p == '..' for p in name.split('/') if p):
                raise ThemeError(f'zip 条目路径不安全：{info.filename}')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:  # S_IFLNK
                raise ThemeError(f'zip 条目不允许是符号链接：{info.filename}')
            if info.is_dir():
                continue
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in loader.ALLOWED_SUFFIX:
                raise ThemeError(f'zip 里有不允许的文件类型：{info.filename}')
            total += info.file_size
            if total > loader.MAX_PACK:
                raise ThemeError(f'zip 解压后超过上限（{loader.MAX_PACK // 1024 // 1024}MB）')
            count += 1
            if count > loader.MAX_FILES:
                raise ThemeError(f'zip 文件数超过上限（{loader.MAX_FILES}）')
        zf.extractall(dest)


def install(src, run_dir, force=False):
    """校验 → 暂存目录 → 复制到 themes/<id>/。返回给用户看的消息。"""
    src = os.path.abspath(os.path.expanduser(src))
    if not os.path.exists(src):
        return f'找不到主题包：{src}'
    tdir = themes_dir(run_dir)
    os.makedirs(tdir, exist_ok=True)
    stage = tempfile.mkdtemp(prefix='.stage-', dir=tdir)  # 同卷：校验完直接挪过去
    try:
        if zipfile.is_zipfile(src):
            _safe_unzip(src, stage)
        elif os.path.isdir(src):
            # symlinks=True：保留链接原样，让 loader 的符号链接检查拦住它；
            # dereference 会把包外内容拷进来（比如链到 ~/.ssh），绝对不能开
            shutil.copytree(src, stage, dirs_exist_ok=True, symlinks=True)
        else:
            return '主题包必须是一个目录或 zip 文件'
        if not os.path.isfile(os.path.join(stage, loader.THEME_FILE)):
            # zip 打包时把包目录整个塞了进去（顶层多一层）：唯一子目录里有
            # pet.json 就把它当包根提上来；多于一个/找不到都明确报错
            inner = [d for d in os.listdir(stage)
                     if os.path.isfile(os.path.join(stage, d, loader.THEME_FILE))]
            if len(inner) != 1:
                return f'安装失败：包根目录找不到 {loader.THEME_FILE}'
            inner_dir = os.path.join(stage, inner[0])
            for name in os.listdir(inner_dir):
                os.replace(os.path.join(inner_dir, name), os.path.join(stage, name))
            os.rmdir(inner_dir)
        pack = loader.load_pack(stage)
        target = os.path.join(tdir, pack.theme_id)
        if os.path.exists(target):
            if not force:
                return (f'主题 {pack.theme_id} 已经装过了。'
                        f'要覆盖请加 --force：/pet theme install <路径> --force')
            shutil.rmtree(target)
        shutil.move(stage, target)
        stage = None  # move 之后没有暂存目录可清了
        # 装完用「正式位置」再校验一遍：拷贝过程（权限/链接）不该有惊喜，有就当场报
        pack = loader.load_pack(target)
        msg = f'已安装 {pack.name}（{pack.theme_id}）。/pet theme use {pack.theme_id} 启用'
        for w in pack.warnings:
            msg += f'\n⚠️ {w}'
        return msg
    except ThemeError as err:
        return f'安装失败：{err}'
    except (zipfile.BadZipFile, OSError) as err:
        # is_zipfile 能过的残缺 zip、读不动的目录：照常给一句人话，别糊 traceback
        return f'安装失败：{err}'
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)


# ---------- 切换 / 删除 ----------

def use(theme_id, run_dir):
    settings = _load_settings(run_dir)
    if not theme_id or theme_id == BUILTIN:
        settings['theme'] = ''
        _save_settings(run_dir, settings)
        return '已切回内置皮肤'
    target = os.path.join(themes_dir(run_dir), theme_id)
    try:
        pack = loader.load_pack(target)
    except ThemeError as err:
        return f'切换失败：{theme_id} 不可用（{err}）'
    settings['theme'] = pack.theme_id
    _save_settings(run_dir, settings)
    return (f'已切换到 {pack.name}（{pack.theme_id}）。'
            f'开着的桌宠几秒内自动换装；没开就下次启动生效')


def remove(theme_id, run_dir):
    if not theme_id or theme_id == BUILTIN:
        return '内置皮肤不能删'
    if active_id(run_dir) == theme_id:
        return f'{theme_id} 正在用，先 /pet theme use builtin 再删'
    target = os.path.join(themes_dir(run_dir), theme_id)
    if not os.path.isdir(target):
        return f'没有安装主题 {theme_id}（/pet theme list 看看装了哪些）'
    shutil.rmtree(target)
    return f'已删除 {theme_id}'


# ---------- 展示 ----------

def list_text(run_dir):
    active = active_id(run_dir)
    tdir = themes_dir(run_dir)
    rows = []
    if os.path.isdir(tdir):
        for name in sorted(os.listdir(tdir)):
            if not os.path.isdir(os.path.join(tdir, name)) or name.startswith('.stage-'):
                continue  # 半截安装的暂存目录不进列表（install 崩溃才会留下）
            try:
                pack = loader.load_pack(os.path.join(tdir, name))
                rows.append(f'{"→" if name == active else " "} {pack.theme_id}  {pack.name}'
                            f'  by {pack.author or "?"}  {pack.license}')
            except ThemeError:
                rows.append(f'! {name}  （损坏，建议 remove 后重装）')
    head = f'当前主题：{active}'
    if not rows:
        return head + ('\n（还没有已安装的主题。把主题文件夹或 zip 拿来：'
                       '/pet theme install <路径>）')
    return head + '\n' + '\n'.join(rows)


def info_text(theme_id, run_dir):
    try:
        pack = loader.load_pack(os.path.join(themes_dir(run_dir), theme_id))
    except ThemeError as err:
        return f'查看失败：{err}'
    size = f'{pack.frame_size[0]}x{pack.frame_size[1]}' if pack.frame_size else '单图'
    lines = [
        f'{pack.name}（{pack.theme_id}）',
        f'作者：{pack.author or "?"}    许可证：{pack.license}',
        f'布局：{pack.layout}    帧尺寸：{size}',
        f'状态覆盖：{pack.coverage_text()}',
        f'音频：{"、".join(sorted(pack.sounds)) or "无"}',
    ]
    lines += [f'⚠️ {w}' for w in pack.warnings]
    return '\n'.join(lines)


# ---------- 命令行入口 ----------

def main(argv):
    """theme_cli.py 的主体；返回 (输出文本, 退出码)。用法见 USAGE。"""
    if not argv or argv[0] in ('-h', '--help', 'help'):
        return USAGE, 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd == 'list':
        if len(rest) != 1:
            return USAGE, 2
        return list_text(rest[0]), 0
    if cmd == 'install':
        if '--force' in rest:
            rest = [a for a in rest if a != '--force']
            force = True
        else:
            force = False
        if len(rest) != 2:
            return USAGE, 2
        return install(' '.join(rest[:-1]), rest[-1], force), 0
    if cmd in ('use', 'remove', 'info'):
        if len(rest) != 2:
            return USAGE, 2
        fn = {'use': use, 'remove': remove, 'info': info_text}[cmd]
        return fn(rest[0], rest[1]), 0
    return USAGE, 2
