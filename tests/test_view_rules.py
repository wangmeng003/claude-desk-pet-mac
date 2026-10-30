"""视图规则与资源契约锁定：SPRITES/SIZES/发呆/气泡文案（specs/state.md 的落地对照）。"""
import re
import time
from pathlib import Path

import pytest

from conftest import REPO, make_pet, pet_mac, requires_platform
from core import view_model as core_view_model

EXPECTED_SPRITES = {
    'thinking': 'smile-closed',
    'tool': 'typing',
    'reading': 'notes',
    'waiting': 'knock',
    'attention': 'knock',
    'celebrate': 'confetti',
    'idle': 'smile',
    'error': 'panic',
    'stone': 'stone',   # 渲染层彩蛋，不是协议状态
}
EXPECTED_SIZES = {'小': 140, '中': 190, '大': 250}


@requires_platform
class TestContract:
    def test_sprites_mapping(self, pet_state):
        petmod, _tmp, _s = pet_state
        assert petmod.SPRITES == EXPECTED_SPRITES

    def test_sizes(self, pet_state):
        petmod, _tmp, _s = pet_state
        assert petmod.SIZES == EXPECTED_SIZES

    def test_idle_after_10_minutes(self, pet_state):
        petmod, _tmp, _s = pet_state
        assert petmod.IDLE_AFTER == 10 * 60

    def test_every_sprite_has_png(self, pet_state):
        sprites = Path(REPO) / 'pet' / 'sprites'
        for name in EXPECTED_SPRITES.values():
            assert (sprites / f'{name}.png').is_file(), f'缺立绘 {name}.png'


@requires_platform
class TestEffectiveState:
    def test_waiting_becomes_idle_after_threshold(self, pet_state):
        pet = make_pet()
        pet.state = 'waiting'
        pet.state_since = time.time() - 601
        assert pet.effective_state() == 'idle'

    def test_waiting_stays_waiting_when_fresh(self, pet_state):
        pet = make_pet()
        pet.state = 'waiting'
        pet.state_since = time.time()
        assert pet.effective_state() == 'waiting'

    def test_non_waiting_never_idle(self, pet_state):
        pet = make_pet()
        pet.state = 'tool'
        pet.state_since = time.time() - 3600
        assert pet.effective_state() == 'tool'


@requires_platform
class TestDisplayText:
    def test_idle_text(self, pet_state):
        pet = make_pet()
        pet.state = 'waiting'
        pet.state_since = time.time() - 601
        assert pet.display_text() == '在发呆～ zZ'

    def test_passthrough(self, pet_state):
        pet = make_pet()
        pet.state = 'tool'
        pet.text = '在跑命令…'
        assert pet.display_text() == '在跑命令…'

    @pytest.mark.skipif(pet_mac is None, reason='思考中点点点在 mac 版 display_text 里实现')
    def test_thinking_dots_mac(self, pet_state):
        pet = make_pet()
        pet.state = 'thinking'
        pet.text = '思考中'
        assert re.fullmatch(r'思考中\.{1,3}', pet.display_text())


# ---------- 原生通知策略（#6）----------

def test_wants_notify_three_states():
    for state in ('celebrate', 'error', 'attention'):
        assert core_view_model.wants_notify(state, changed=True) is True, state


def test_wants_notify_only_on_change():
    # 同状态重复刷新（changed=False）不通知——「不反复弹窗」
    assert core_view_model.wants_notify('error', changed=False) is False
    # 其他状态从不通知
    for state in ('idle', 'thinking', 'tool', 'reading', 'waiting'):
        assert core_view_model.wants_notify(state, changed=True) is False, state


def test_wants_notify_settings_toggle():
    assert core_view_model.wants_notify('error', True, {'notify': False}) is False
    assert core_view_model.wants_notify('error', True, {'notify': True}) is True
    assert core_view_model.wants_notify('error', True, {}) is True  # 默认开


def test_notify_body():
    assert core_view_model.notify_body('搞定啦！', 'demo', False) == '搞定啦！ · demo（双击桌宠回到终端）'
    assert core_view_model.notify_body('搞定啦！', 'demo', True) == '搞定啦！（双击桌宠回到终端）'  # 隐私：不带项目名
    assert core_view_model.notify_body('需要你看一下', '', False) == '需要你看一下（双击桌宠回到终端）'
