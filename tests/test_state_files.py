"""read_latest / settings 读取的行为锁定（fixtures：正常、旧格式、缺字段、坏 JSON、过期、多会话）。"""
from conftest import requires_platform, write_session


@requires_platform
class TestReadLatest:
    def test_picks_newest_mtime(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 'old', {'state': 'tool', 'text': '旧', 'project': 'p'}, age=100)
        write_session(sessions, 'new', {'state': 'error', 'text': '新', 'project': 'p'}, age=10)
        mtime, data = petmod.read_latest()
        assert data['text'] == '新'
        assert data['state'] == 'error'

    def test_skips_corrupt_json(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 'bad', raw='{not valid json', age=10)
        write_session(sessions, 'good', {'state': 'waiting', 'text': '好'}, age=20)
        mtime, data = petmod.read_latest()
        assert data['text'] == '好'

    def test_all_corrupt_returns_none(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 'bad1', raw='{{{', age=10)
        write_session(sessions, 'bad2', raw='not json', age=20)
        assert petmod.read_latest() is None

    def test_expired_file_deleted_and_ignored(self, pet_state):
        petmod, _tmp, sessions = pet_state
        expired = write_session(sessions, 'stale', {'state': 'tool', 'text': '旧'}, age=3 * 86400)
        write_session(sessions, 'fresh', {'state': 'waiting', 'text': '新'}, age=100)
        mtime, data = petmod.read_latest()
        assert data['text'] == '新'
        assert not expired.exists()  # 两天前的文件被顺手清掉

    def test_empty_dir_returns_none(self, pet_state):
        petmod, _tmp, _sessions = pet_state
        assert petmod.read_latest() is None

    def test_missing_fields_kept_as_is(self, pet_state):
        """缺字段/多字段的数据原样返回，默认值由 poll() 决定。"""
        petmod, _tmp, sessions = pet_state
        # raw：夹具的 data 路径会自动补协议必填的 ts，这里就要「最少字段」
        write_session(sessions, 'minimal', raw='{"state": "tool"}', age=10)
        _mtime, data = petmod.read_latest()
        assert data == {'state': 'tool'}


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
