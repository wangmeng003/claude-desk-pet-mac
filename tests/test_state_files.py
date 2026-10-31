"""settings 读取的行为锁定（状态文件读取的 TTL/优先级/损坏容忍由 test_aggregate.py 锁定）。"""
from conftest import requires_platform  # noqa: F401  (pet_state 夹具要平台模块)


@requires_platform
class TestLoadSettings:
    def test_corrupt_settings_returns_empty(self, pet_state):
        petmod, tmp, _sessions = pet_state
        (tmp / 'settings.json').write_text('{broken', encoding='utf-8')
        assert petmod.load_settings() == {}

    def test_missing_settings_returns_empty(self, pet_state):
        petmod, _tmp, _sessions = pet_state
        assert petmod.load_settings() == {}

    def test_roundtrip(self, pet_state):
        petmod, _tmp, _sessions = pet_state
        petmod.save_settings({'size': '小', 'sound': False})
        assert petmod.load_settings() == {'size': '小', 'sound': False}
