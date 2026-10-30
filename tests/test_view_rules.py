"""视图规则与资源契约锁定：SPRITES/SIZES/发呆/气泡文案（specs/state.md 的落地对照）。"""
import re
import time
from pathlib import Path

import pytest

from conftest import REPO, make_pet, pet_mac, requires_platform

EXPECTED_SPRITES = {
    'thinking': 'smile-closed',
    'tool': 'typing',
    'reading': 'notes',
    'waiting': 'knock',
    'celebrate': 'confetti',
    'idle': 'smile',
    'error': 'panic',
    'aborted': 'guilty',
    'stone': 'stone',
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
