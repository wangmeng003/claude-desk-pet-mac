# #15 卡片接线（宠物侧）：HTTP 线程入队 → 主线程弹卡 → 决策回桥 → 桥侧结束关卡。
# 卡片窗口本身是 GUI，用桩替身；这里锁定接线的纯逻辑部分。
import time

import pytest
from conftest import make_pet, pet_mac, petmod, requires_platform

from core.models import PermissionRequestViewModel


def _vm(rid='p1', risk='high'):
    return PermissionRequestViewModel(
        id=rid, session='s1', tool='Bash', project='demo',
        summary='rm -rf build', detail='rm -rf build', risk=risk, ts=1.0)


class FakeBridge:
    def __init__(self):
        self.decisions = []

    def decide(self, rid, decision, reason='user'):
        self.decisions.append((rid, decision, reason))
        return True


class StubCard:
    made = []

    def __init__(self, pet, vm, deadline):
        self.pet, self.vm, self.deadline = pet, vm, deadline
        self.closed = False
        StubCard.made.append(self)

    def show(self, origin=None):
        pass

    def settle_if_matching(self, rid):
        if rid == self.vm.id and not self.closed:
            self.closed = True
            return True
        return False


@pytest.fixture
def card_stub(pet_state, monkeypatch):
    StubCard.made = []
    if pet_mac is not None and petmod is pet_mac:
        monkeypatch.setattr(petmod.mac_card, 'PermissionCard', StubCard)
    else:
        monkeypatch.setattr(petmod, 'PermissionCard', StubCard)
    return StubCard


@requires_platform
class TestCardWiring:
    def test_incoming_to_card(self, card_stub):
        pet = make_pet()
        pet.attach_bridge(FakeBridge())
        pet.permission_incoming(_vm())
        pet.drain_card_events()
        assert len(card_stub.made) == 1
        card = card_stub.made[0]
        assert card.vm.id == 'p1' and card.pet is pet
        assert card.deadline == pytest.approx(time.time() + 600, abs=5)

    def test_busy_second_request_no_second_card(self, card_stub):
        pet = make_pet()
        pet.attach_bridge(FakeBridge())
        pet.permission_incoming(_vm('a'))
        pet.permission_incoming(_vm('b'))
        pet.drain_card_events()
        assert len(card_stub.made) == 1  # 忙时 bridge 已 409；防御性只弹一张

    def test_decision_flows_to_bridge(self, card_stub):
        pet = make_pet()
        bridge = FakeBridge()
        pet.attach_bridge(bridge)
        pet.permission_incoming(_vm('p1'))
        pet.drain_card_events()
        card_stub.made[0].pet.permission_decide('p1', 'deny')
        assert bridge.decisions == [('p1', 'deny', 'user')]
        assert pet.card is None

    def test_settled_event_closes_matching_card_only(self, card_stub):
        pet = make_pet()
        pet.attach_bridge(FakeBridge())
        pet.permission_incoming(_vm('p1'))
        pet.drain_card_events()
        card = card_stub.made[0]
        pet.permission_settled('other', 'ask', 'timeout')
        pet.drain_card_events()
        assert not card.closed and pet.card is card
        pet.permission_settled('p1', 'ask', 'timeout')
        pet.drain_card_events()
        assert card.closed and pet.card is None

    def test_no_bridge_attached_is_silent(self, card_stub):
        pet = make_pet()  # 没 attach_bridge（既有 golden 测试的形态）
        pet.permission_incoming(_vm())
        pet.drain_card_events()  # 不弹卡、不抛错
        assert card_stub.made == []

    def test_detail_never_written_to_disk(self, card_stub, pet_state):
        _petmod, tmp, _sessions = pet_state
        before = sorted(p.name for p in tmp.rglob('*'))
        pet = make_pet()
        pet.attach_bridge(FakeBridge())
        pet.permission_incoming(_vm())
        pet.drain_card_events()
        pet.permission_decide('p1', 'allow')
        after = sorted(p.name for p in tmp.rglob('*'))
        assert before == after  # 卡片链路全程零写盘（detail 只在内存）
        for p in tmp.rglob('*'):
            if p.is_file():
                assert 'rm -rf build' not in p.read_text(encoding='utf-8', errors='ignore')


@requires_platform
class TestCardRules:
    """卡片规则纯函数（core.view_model，specs §5.5）。"""

    def test_countdown_text(self):
        from core import view_model
        assert view_model.card_countdown_text(600) == '10:00'
        assert view_model.card_countdown_text(65.4) == '01:05'
        assert view_model.card_countdown_text(0) == '已超时，回退终端…'
        assert view_model.card_countdown_text(-3) == '已超时，回退终端…'

    def test_default_focus_by_risk(self):
        from core import view_model
        assert view_model.card_default_focus('high') == 'defer'
        assert view_model.card_default_focus('medium') == 'allow'
        assert view_model.card_default_focus('low') == 'allow'
