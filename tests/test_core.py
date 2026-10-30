"""pet/core 纯函数单测：不依赖平台 GUI（pyobjc/tkinter），任何平台都能跑。

golden 测试（test_state_files 等）从 pet_mac/pet.pyw 外侧锁定行为；
这里从 core 内侧锁定同一批规则，重构后两边的等价关系由 golden 测试兜底。
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PET_DIR = REPO / 'pet'
if str(PET_DIR) not in sys.path:
    sys.path.insert(0, str(PET_DIR))

from conftest import write_session  # noqa: E402
from core import models, sessions, state_reader, view_model  # noqa: E402

NOW = time.time()
OLD = NOW - 700  # 超过 IDLE_AFTER（600s）


class TestNormalize:
    def test_full_mapping(self):
        s = view_model.normalize({'state': 'tool', 'text': '在跑命令…', 'project': 'demo',
                                  'sound': 'done'})
        assert s == models.SessionState('tool', '在跑命令…', 'demo', 'done')

    def test_unknown_state_falls_back(self):
        assert view_model.normalize({'state': 'nope', 'text': 'x'}).state == 'waiting'

    def test_missing_everything(self):
        s = view_model.normalize({})
        assert s == models.SessionState('waiting', '', '', None)

    def test_sound_filtered(self):
        assert view_model.normalize({'sound': 'hacked'}).sound is None
        assert view_model.normalize({'sound': 'error'}).sound == 'error'
        assert view_model.normalize({}).sound is None


class TestEffectiveState:
    def test_waiting_expires_to_idle(self):
        assert view_model.effective_state('waiting', OLD, NOW) == 'idle'

    def test_waiting_fresh(self):
        assert view_model.effective_state('waiting', NOW - 10, NOW) == 'waiting'

    def test_boundary_not_idle(self):
        # 旧实现是严格大于：刚好 600s 不算发呆
        assert view_model.effective_state('waiting', NOW - 600, NOW) == 'waiting'

    def test_non_waiting_never_idle(self):
        assert view_model.effective_state('tool', OLD, NOW) == 'tool'


class TestDisplayText:
    def test_idle_override(self):
        assert view_model.display_text('waiting', 'x', NOW, OLD) == models.IDLE_TEXT
        assert view_model.display_text_with_dots('waiting', 'x', NOW, OLD) == models.IDLE_TEXT

    def test_passthrough(self):
        assert view_model.display_text('tool', '在跑命令…', NOW, NOW - 5) == '在跑命令…'

    def test_dots_variant(self):
        assert view_model.display_text_with_dots('thinking', '思考中', NOW, NOW - 5) \
            == view_model.thinking_dots('思考中', NOW)

    def test_thinking_without_中_no_dots(self):
        assert view_model.display_text_with_dots('thinking', 'thinking', NOW, NOW - 5) == 'thinking'


class TestStateReader:
    def test_is_expired_boundary(self):
        assert state_reader.is_expired(NOW - state_reader.EXPIRE_AFTER - 1, NOW)
        assert not state_reader.is_expired(NOW - state_reader.EXPIRE_AFTER, NOW)

    def test_settings_roundtrip_and_corrupt(self, tmp_path):
        p = tmp_path / 'settings.json'
        assert state_reader.load_settings(str(p)) == {}
        state_reader.save_settings(str(p), {'size': '小'})
        assert state_reader.load_settings(str(p)) == {'size': '小'}
        p.write_text('{broken', encoding='utf-8')
        assert state_reader.load_settings(str(p)) == {}


class TestSessionsReadLatest:
    def test_newest_and_expired(self, tmp_path):
        sessions_dir = tmp_path / 'sessions'
        sessions_dir.mkdir()
        write_session(sessions_dir, 'old', {'state': 'tool', 'text': '旧'}, age=100)
        expired = write_session(sessions_dir, 'stale', {'state': 'error'}, age=3 * 86400)
        write_session(sessions_dir, 'new', {'state': 'waiting', 'text': '新'}, age=10)
        found = sessions.read_latest(str(sessions_dir))
        assert found is not None
        _mtime, data = found
        assert data['text'] == '新'
        assert not expired.exists()

    def test_all_corrupt_returns_none(self, tmp_path):
        sessions_dir = tmp_path / 'sessions'
        sessions_dir.mkdir()
        write_session(sessions_dir, 'bad', raw='{{{')
        assert sessions.read_latest(str(sessions_dir)) is None
