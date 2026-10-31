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


# ---------- 原生通知策略（#6/#11）----------

def _gate(**kw):
    """allow() 的关键字参数填默认值，测试只写关心的那几个。"""
    args = dict(state='attention', text='需要你看一下', session='s1',
                changed=True, settings=None, now=100.0)
    args.update(kw)
    gate = core_view_model.NotifyGate()
    return gate.allow(**args), gate


def test_gate_allows_three_notify_states_on_change():
    for state in ('celebrate', 'error', 'attention'):
        ok, _ = _gate(state=state)
        assert ok is True, state


def test_gate_rejects_unchanged_and_quiet_states():
    # 同状态重复刷新（changed=False）不通知——「不反复弹窗」
    ok, _ = _gate(changed=False)
    assert ok is False
    for state in ('idle', 'thinking', 'tool', 'reading', 'waiting'):
        ok, _ = _gate(state=state)
        assert ok is False, state


def test_gate_settings_toggles():
    assert _gate(settings={'notify': False})[0] is False
    assert _gate(settings={'notify': True})[0] is True
    assert _gate(settings={})[0] is True  # 默认开


def test_gate_dnd_blocks_banner():
    # 勿扰（#11）：不弹横幅不响铃；气泡/表情照常（渲染层与此闸无关）
    assert _gate(settings={'dnd': True})[0] is False


def test_gate_dedup_same_key_within_2s():
    # 同一会话/工具/摘要 2 秒内只通知一次（#11）
    gate = core_view_model.NotifyGate()
    a = dict(state='attention', text='需要你看一下', session='s1',
             changed=True, settings=None)
    assert gate.allow(**a, now=100.0) is True
    assert gate.allow(**a, now=101.5) is False  # 窗口内同键：不刷屏
    assert gate.allow(**a, now=102.1) is True   # 窗口过了：能再弹


def test_gate_dedup_key_includes_text_and_session():
    gate = core_view_model.NotifyGate()
    a = dict(changed=True, settings=None)
    assert gate.allow(state='attention', text='需要你看一下', session='s1', now=100.0, **a) is True
    # 摘要不同（另一个工具的提醒）：不能丢
    assert gate.allow(state='attention', text='要授权网络', session='s1', now=100.5, **a) is True
    # 会话不同：不能丢
    assert gate.allow(state='attention', text='需要你看一下', session='s2', now=101.0, **a) is True


def test_gate_attention_not_eaten_by_celebrate_window():
    # 权限事件优先于完成通知（#11）：celebrate 刚弹过，attention 不被 2 秒窗口吃掉
    gate = core_view_model.NotifyGate()
    a = dict(session='s1', changed=True, settings=None)
    assert gate.allow(state='celebrate', text='搞定啦！轮到你～', now=100.0, **a) is True
    assert gate.allow(state='attention', text='需要你看一下', now=100.5, **a) is True


def test_notify_sound_only_attention():
    # 通知自带声音（#11）：只有 attention 响铃；完成/出错的声音走状态文件的提示音
    assert core_view_model.notify_sound('attention') is True
    assert core_view_model.notify_sound('celebrate') is False
    assert core_view_model.notify_sound('error') is False


def test_notify_body():
    assert core_view_model.notify_body('搞定啦！', 'demo', False) == '搞定啦！ · demo（双击桌宠回到终端）'
    assert core_view_model.notify_body('搞定啦！', 'demo', True) == '搞定啦！（双击桌宠回到终端）'  # 隐私：不带项目名
    assert core_view_model.notify_body('需要你看一下', '', False) == '需要你看一下（双击桌宠回到终端）'
