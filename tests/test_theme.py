"""主题包系统（M4，specs/theme.md）的测试：loader 校验/回退 + manager 安装/切换。

fixture 不落仓库二进制：PNG/WAV 都在测试里现做（loader 只看魔数和头部，
一个程序生成的最小合法 PNG 足够；PIL 完整解码在渲染层，坏了走渲染层回退）。
"""
import json
import os
import shutil
import struct
import zipfile
import zlib

import pytest

from theme import loader, manager
from theme.loader import ThemeError

STATES8 = ('idle', 'thinking', 'tool', 'reading', 'waiting', 'attention',
           'celebrate', 'error')


# ---------- 现做素材 ----------

def png_bytes(w=1, h=1, color=(0, 0, 0, 0)):
    def chunk(typ, data):
        c = typ + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)  # 8bit RGBA
    raw = b''.join(b'\x00' + bytes(color) * w for _ in range(h))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def fake_png_dims(w, h):
    """只有头的 PNG：loader 的尺寸校验读 IHDR，不需要完整图片。"""
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + ihdr + b'\x00' * 32


def wav_bytes(n=64):
    return (b'RIFF' + (36 + n).to_bytes(4, 'little') + b'WAVE'
            + b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, 8000, 8000, 1, 8)
            + b'data' + n.to_bytes(4, 'little') + b'\x00' * n)


def make_states_pack(root, states=STATES8, **overrides):
    """单图布局主题包：每个状态一张 1x1 PNG；overrides 直接进 pet.json。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / 'states').mkdir(exist_ok=True)
    manifest = {
        'schema': 1, 'id': root.name, 'name': root.name, 'author': 'tester',
        'license': 'CC-BY-4.0', 'layout': 'states',
        'states': {s: f'states/{s}.png' for s in states},
    }
    for s in states:
        (root / 'states' / f'{s}.png').write_bytes(png_bytes())
    manifest.update(overrides)
    (root / 'pet.json').write_text(json.dumps(manifest), encoding='utf-8')
    return root


def make_sheet_pack(root, states=None, columns=8, rows=9, size=64):
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        'schema': 1, 'id': root.name, 'name': root.name, 'author': 'tester',
        'license': 'CC-BY-4.0', 'layout': 'spritesheet',
        'frame': {'width': size, 'height': size, 'columns': columns, 'rows': rows},
        'states': states or {'idle': [0, 1], 'tool': [16, 17]},
    }
    (root / 'pet.json').write_text(json.dumps(manifest), encoding='utf-8')
    (root / 'spritesheet.png').write_bytes(png_bytes())
    return root


def make_zip(src: 'os.PathLike', dest: 'os.PathLike', prefix=''):
    with zipfile.ZipFile(dest, 'w') as zf:
        for base, _dirs, files in os.walk(src):
            for fn in files:
                full = os.path.join(base, fn)
                zf.write(full, prefix + os.path.relpath(full, src))


# ---------- loader：合法包与回退 ----------

def test_states_pack_load_and_fallback(tmp_path):
    pack = loader.load_pack(make_states_pack(tmp_path / 'p1'))
    assert pack.theme_id == 'p1' and pack.layout == 'states'
    for s in STATES8:
        assert pack.frames[s][1] is None  # 单图布局无帧矩形
        assert pack.image_for(s)[0].endswith(f'{s}.png')
    assert pack.image_for('stone') is None  # 渲染层彩蛋不进主题


def test_missing_states_fallback_chain(tmp_path):
    # 只给 idle/tool：attention/celebrate → waiting → … → idle（spec §3.2）
    pack = loader.load_pack(make_states_pack(tmp_path / 'p', states=('idle', 'tool')))
    assert pack.image_for('attention')[0].endswith('idle.png')
    assert pack.image_for('waiting')[0].endswith('idle.png')
    assert pack.image_for('celebrate')[0].endswith('idle.png')
    assert pack.image_for('tool')[0].endswith('tool.png')


def test_sheet_pack_frame_rects(tmp_path):
    pack = loader.load_pack(make_sheet_pack(tmp_path / 'sheet'))
    assert pack.frame_size == (64, 64)
    # 8 列网格：索引 16 → 第 2 行第 0 列；多帧取第一帧
    assert pack.frames['tool'] == (str(tmp_path / 'sheet' / 'spritesheet.png'),
                                   (0, 128, 64, 64))
    assert pack.image_for('reading')[0].endswith('spritesheet.png')  # 缺 → 回退 idle


def test_petdex_row_names_mapped(tmp_path):
    pack = loader.load_pack(make_sheet_pack(tmp_path / 'dex', states={
        'idle': [0], 'running': [8], 'review': [16], 'jumping': [24],
        'waving': [32], 'failed': [40]}))
    assert set(pack.frames) == {'idle', 'tool', 'reading', 'celebrate', 'attention', 'error'}


def test_unknown_state_key_ignored_with_warning(tmp_path):
    pack = loader.load_pack(make_states_pack(
        tmp_path / 'p', states=('idle', 'sleeping')))
    assert 'sleeping' not in pack.frames
    assert any('sleeping' in w for w in pack.warnings)


def test_license_unknown_warns_but_loads(tmp_path):
    pack = loader.load_pack(make_states_pack(tmp_path / 'p', license='unknown'))
    assert any('unknown' in w for w in pack.warnings)


def test_sound_path_resolution(tmp_path):
    builtin = tmp_path / 'sounds'
    builtin.mkdir()
    (builtin / 'done.wav').write_bytes(wav_bytes())
    # sounds 字段乱写（拿图片冒充音频）→ 整包拒绝；没主题音时回退内置
    with pytest.raises(ThemeError, match='WAV/MP3'):
        loader.load_pack(make_states_pack(
            tmp_path / 'p', sounds={'done': 'states/idle.png'}))
    assert loader.sound_path(None, 'done', str(builtin)) == str(builtin / 'done.wav')

    # 合法主题音（mp3）+ 未知音频键忽略
    root = make_states_pack(tmp_path / 'q', states=('idle',))
    (root / 'done.mp3').write_bytes(b'ID3' + b'\x00' * 32)
    (root / 'pet.json').write_text(json.dumps({
        'schema': 1, 'id': 'q', 'name': 'q', 'license': 'MIT', 'layout': 'states',
        'states': {'idle': 'states/idle.png'},
        'sounds': {'done': 'done.mp3', 'meow': 'done.mp3'}}), encoding='utf-8')
    pack_mp3 = loader.load_pack(root)
    assert pack_mp3.sounds == {'done': str(root / 'done.mp3')}
    assert any('meow' in w for w in pack_mp3.warnings)
    # wav_only（Windows winsound 只吃 WAV）：主题是 mp3 时回退内置
    assert loader.sound_path(pack_mp3, 'done', str(builtin), wav_only=True) \
        == str(builtin / 'done.wav')
    assert loader.sound_path(pack_mp3, 'done', str(builtin)).endswith('done.mp3')
    assert loader.sound_path(None, 'error', str(builtin)) == str(builtin / 'error.wav')


# ---------- loader：拒绝类 ----------

def test_missing_idle_rejected(tmp_path):
    with pytest.raises(ThemeError, match='idle'):
        loader.load_pack(make_states_pack(tmp_path / 'p', states=('tool',)))


def test_missing_license_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    m = json.loads((root / 'pet.json').read_text(encoding='utf-8'))
    del m['license']
    (root / 'pet.json').write_text(json.dumps(m), encoding='utf-8')
    with pytest.raises(ThemeError, match='license'):
        loader.load_pack(root)


def test_bad_frame_index_rejected(tmp_path):
    with pytest.raises(ThemeError, match='越界'):
        loader.load_pack(make_sheet_pack(tmp_path / 'p', states={'idle': [0, 72]}))


def test_bad_frame_spec_rejected(tmp_path):
    root = make_sheet_pack(tmp_path / 'p')
    m = json.loads((root / 'pet.json').read_text(encoding='utf-8'))
    m['frame']['width'] = 16  # 低于 32 下限
    (root / 'pet.json').write_text(json.dumps(m), encoding='utf-8')
    with pytest.raises(ThemeError, match='帧尺寸'):
        loader.load_pack(root)


@pytest.mark.parametrize('rel', ['../outside/x.png', '/etc/x.png', 'C:\\x.png', '..\\x.png'])
def test_path_escapes_rejected(tmp_path, rel):
    root = make_states_pack(tmp_path / 'p')
    m = json.loads((root / 'pet.json').read_text(encoding='utf-8'))
    m['states']['idle'] = rel
    (root / 'pet.json').write_text(json.dumps(m), encoding='utf-8')
    with pytest.raises(ThemeError):
        loader.load_pack(root)


@pytest.mark.skipif(os.name == 'nt', reason='Windows 建符号链接要特权')
def test_symlink_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    outside = tmp_path / 'outside.png'
    outside.write_bytes(png_bytes())
    link = root / 'states' / 'tool.png'
    link.unlink()
    os.symlink(outside, link)
    with pytest.raises(ThemeError, match='符号链接'):
        loader.load_pack(root)


def test_oversized_json_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    m = json.loads((root / 'pet.json').read_text(encoding='utf-8'))
    m['name'] = 'x' * (64 * 1024)
    (root / 'pet.json').write_text(json.dumps(m), encoding='utf-8')
    with pytest.raises(ThemeError, match='64KB'):
        loader.load_pack(root)


def test_bad_image_magic_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    (root / 'states' / 'idle.png').write_bytes(b'this is not a png')
    with pytest.raises(ThemeError, match='PNG/WebP'):
        loader.load_pack(root)


def test_oversized_png_dims_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    (root / 'states' / 'idle.png').write_bytes(fake_png_dims(8192, 8))
    with pytest.raises(ThemeError, match='4096'):
        loader.load_pack(root)


def test_disallowed_suffix_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    (root / 'evil.py').write_text('print(1)')
    with pytest.raises(ThemeError, match='不允许的文件类型'):
        loader.load_pack(root)


def test_too_many_files_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    junk = root / 'junk'
    junk.mkdir()
    for i in range(210):
        (junk / f'{i}.png').write_bytes(png_bytes())
    with pytest.raises(ThemeError, match='文件数'):
        loader.load_pack(root)


def test_oversized_sound_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    big = b'RIFF' + b'\xff\xff\x00\x00' + b'WAVE' + b'\x00' * (2 * 1024 * 1024)
    (root / 'states' / 'big.wav').write_bytes(big)
    m = json.loads((root / 'pet.json').read_text(encoding='utf-8'))
    m['sounds'] = {'done': 'states/big.wav'}
    (root / 'pet.json').write_text(json.dumps(m), encoding='utf-8')
    with pytest.raises(ThemeError, match='2MB'):
        loader.load_pack(root)


@pytest.mark.parametrize('mutate', [
    lambda m: m.update(schema=2),
    lambda m: m.update(id='Bad Id'),
    lambda m: m.update(layout='gif'),
    lambda m: m.update(states={}),
])
def test_bad_manifest_rejected(tmp_path, mutate):
    root = make_states_pack(tmp_path / 'p')
    m = json.loads((root / 'pet.json').read_text(encoding='utf-8'))
    mutate(m)
    (root / 'pet.json').write_text(json.dumps(m), encoding='utf-8')
    with pytest.raises(ThemeError):
        loader.load_pack(root)


def test_broken_manifest_json_rejected(tmp_path):
    root = make_states_pack(tmp_path / 'p')
    (root / 'pet.json').write_text('{"schema": 1,', encoding='utf-8')
    with pytest.raises(ThemeError):
        loader.load_pack(root)


def test_load_active_never_raises(tmp_path):
    assert loader.load_active(tmp_path / 'themes', '') is None
    assert loader.load_active(tmp_path / 'themes', 'builtin') is None
    assert loader.load_active(tmp_path / 'themes', 'nope') is None
    broken = make_states_pack(tmp_path / 'themes' / 'broken', states=('tool',))
    assert loader.load_active(broken.parent, 'broken') is None  # 回退内置，不抛


# ---------- manager：安装 / 切换 / 删除 ----------

@pytest.fixture
def run_dir(tmp_path):
    (tmp_path / 'sessions').mkdir()
    return tmp_path


def test_install_use_persist_and_builtin(run_dir, tmp_path):
    src = make_states_pack(tmp_path / 'src-pack')
    msg = manager.install(str(src), str(run_dir))
    assert '已安装' in msg
    assert (run_dir / 'themes' / 'src-pack' / 'pet.json').is_file()

    msg = manager.use('src-pack', str(run_dir))
    assert '已切换' in msg
    settings = json.loads((run_dir / 'settings.json').read_text(encoding='utf-8'))
    assert settings['theme'] == 'src-pack'  # 持久化：重启后 renderer 启动即读

    assert '内置' in manager.use('builtin', str(run_dir))
    settings = json.loads((run_dir / 'settings.json').read_text(encoding='utf-8'))
    assert settings['theme'] == ''


def test_install_dup_requires_force(run_dir, tmp_path):
    src = make_states_pack(tmp_path / 'pack')
    assert '已安装' in manager.install(str(src), str(run_dir))
    assert 'force' in manager.install(str(src), str(run_dir))
    assert '已安装' in manager.install(str(src), str(run_dir), force=True)
    assert manager.install(str(tmp_path / 'nope'), str(run_dir)).startswith('找不到')


def test_install_rejects_bad_pack_and_cleans(run_dir, tmp_path):
    src = make_states_pack(tmp_path / 'bad', states=('tool',))  # 缺 idle
    msg = manager.install(str(src), str(run_dir))
    assert msg.startswith('安装失败')
    assert not (run_dir / 'themes' / 'bad').exists()
    assert not any(p.name.startswith('.stage-')
                   for p in (run_dir / 'themes').iterdir())


def test_install_zip_and_inner_dir(run_dir, tmp_path):
    src = make_states_pack(tmp_path / 'pack')
    flat = tmp_path / 'flat.zip'
    make_zip(src, flat)
    assert '已安装' in manager.install(str(flat), str(run_dir))
    assert (run_dir / 'themes' / 'pack' / 'pet.json').is_file()

    wrapped = tmp_path / 'wrapped.zip'
    make_zip(src, wrapped, prefix='pack-dir/')  # 顶层多一层目录
    shutil.rmtree(run_dir / 'themes' / 'pack')
    assert '已安装' in manager.install(str(wrapped), str(run_dir))


def test_install_zip_traversal_rejected(run_dir, tmp_path):
    evil = tmp_path / 'evil.zip'
    with zipfile.ZipFile(evil, 'w') as zf:
        zf.writestr('../escape.png', b'x')
    msg = manager.install(str(evil), str(run_dir))
    assert msg.startswith('安装失败')
    assert not (tmp_path / 'escape.png').exists()
    assert not (tmp_path.parent / 'escape.png').exists()


def test_remove_rules(run_dir, tmp_path):
    src = make_states_pack(tmp_path / 'pack')
    manager.install(str(src), str(run_dir))
    manager.use('pack', str(run_dir))
    assert 'use builtin' in manager.remove('pack', str(run_dir))
    manager.use('builtin', str(run_dir))
    assert '已删除' in manager.remove('pack', str(run_dir))
    assert '没有安装' in manager.remove('pack', str(run_dir))
    assert '不能删' in manager.remove('builtin', str(run_dir))


def test_list_and_info_and_cli(run_dir, tmp_path):
    src = make_states_pack(tmp_path / 'pack')
    manager.install(str(src), str(run_dir))
    manager.use('pack', str(run_dir))
    text, code = manager.main(['list', str(run_dir)])
    assert code == 0 and '→ pack' in text
    text, _ = manager.main(['info', 'pack', str(run_dir)])
    assert 'pack' in text and 'CC-BY-4.0' in text and '单图' in text
    text, code = manager.main(['nonsense', str(run_dir)])
    assert code == 2 and '用法' in text
    text, _ = manager.main(['list'])  # 缺 run_dir
    assert code == 2


# ---------- 渲染层接线：settings 外部变更立即生效（spec §4.1「use 立即重载」） ----------

def test_sync_settings_reloads_on_theme_change(pet_state):
    import types

    from conftest import make_pet, pet_mac

    petmod, _tmp, _sessions = pet_state
    pet = make_pet()
    calls = []
    if pet_mac is not None:  # mac 走 window.resize()，Windows 走 self.resize()
        pet.window = types.SimpleNamespace(resize=lambda: calls.append(1))
    else:
        pet.resize = lambda: calls.append(1)
    pet.sync_settings()  # 测试造的 Pet 没有 _settings_mtime：直接跳过，不碰窗口
    assert calls == []
    pet._settings_mtime = 0.0
    petmod.save_settings({'theme': 'rock'})
    pet.sync_settings()
    assert calls == [1]  # theme 变了 → 重载立绘
    assert pet.settings.get('theme') == 'rock'
    pet.sync_settings()  # mtime 没再变：不重复重载
    assert calls == [1]
