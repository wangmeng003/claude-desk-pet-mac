"""Step 0 characterization tests 的公共夹具。

mac 渲染已抽到 pet/platforms/mac/（Step 2），Windows 渲染仍在 pet.pyw；
本文件负责按平台加载被测模块、准备临时运行目录，让测试只触碰纯逻辑：
read_latest / poll 的状态映射 / effective_state / display_text / SPRITES 约定。
"""
import importlib
import importlib.util
import json
import os
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PET_DIR = REPO / 'pet'

# pet_mac.py / pet.pyw 以 `from core...` 绝对导入（运行时 pet/ 在 sys.path[0]），
# 测试经 SourceFileLoader 加载，需要手动补上
if str(PET_DIR) not in sys.path:
    sys.path.insert(0, str(PET_DIR))
importlib.invalidate_caches()


def _load_module(name: str, path: Path):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


# import 被测模块（接缝改动后 import 无副作用；平台相关 import 仍然只在对应平台可行）
pet_mac = None
pet_win = None
if sys.platform == 'darwin':
    pet_mac = _load_module('pet_mac_under_test', PET_DIR / 'pet_mac.py')
elif sys.platform == 'win32':
    pet_win = _load_module('pet_win_under_test', PET_DIR / 'pet.pyw')

# 两平台共享同一套状态约定，测试统一走 petmod
petmod = pet_mac or pet_win

requires_platform = pytest.mark.skipif(
    petmod is None, reason=f'被测模块在 {sys.platform} 上不可导入')


def write_session(sessions_dir: Path, sid: str, data=None, raw: str | None = None,
                  age: float = 0.0) -> Path:
    """写一个会话状态文件；age 秒前修改（mtime），用于新旧/过期场景。"""
    p = sessions_dir / f'{sid}.json'
    if raw is not None:
        p.write_text(raw, encoding='utf-8')
    else:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    ts = time.time() - age
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def pet_state(tmp_path, monkeypatch):
    """隔离的运行目录：sessions/ + settings.json，并把被测模块指过去。"""
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    settings = tmp_path / 'settings.json'
    monkeypatch.setattr(petmod, 'SESSIONS', str(sessions))
    monkeypatch.setattr(petmod, 'SETTINGS', str(settings))
    monkeypatch.setattr(petmod, 'RUN_DIR', str(tmp_path))
    return petmod, tmp_path, sessions


def make_pet():
    """不跑 __init__（要 GUI）的 Pet 实例，只装 poll 需要的字段。"""
    pet = petmod.Pet.__new__(petmod.Pet)
    pet.state = 'waiting'
    pet.text = '我来啦～'
    pet.project = ''
    pet.state_since = time.time()
    pet.last_mtime = 0
    pet.last_mtime_seen = 0
    pet.hop_at = time.time()
    pet.error_streak = 0
    pet.settings = {'sound': True}
    pet.refresh = lambda: None  # 实例属性盖掉方法，渲染不执行
    if pet_win is not None and petmod is pet_win:
        pet.canvas = _CanvasStub(pet)
        pet.root = _RootStub()  # Windows 版 poll() 末尾用 root.after 调度下一帧
        pet.draw_bubble = lambda: None
        pet.sound_var = _VarStub(True)
        pet.images = {name: _ImageStub(name) for name in petmod.SPRITES}
        pet.fallback_image = None
        pet.sprite = 1
    return pet


class _RootStub:
    def after(self, _ms, _cb):
        return None


class _CanvasStub:
    def __init__(self, pet):
        self.pet = pet
        self.itemconfig_calls = []

    def itemconfig(self, *args, **kwargs):
        self.itemconfig_calls.append((args, kwargs))

    def itemcget(self, *_a, **_k):
        return str(self.pet.images.get('idle'))


class _VarStub:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _ImageStub:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f'img:{self.name}'
