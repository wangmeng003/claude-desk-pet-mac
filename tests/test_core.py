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
from core import cli_args, models, sessions, state_reader, view_model  # noqa: E402

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

    def test_non_string_text_becomes_empty(self):
        """坏数据里的非字符串 text/project 不能流到渲染层（否则气泡绘制崩）。"""
        s = view_model.normalize({'state': 'tool', 'text': 123, 'project': {'a': 1}})
        assert s.text == ''
        assert s.project == ''

    def test_non_string_text_keeps_string_text(self):
        s = view_model.normalize({'state': 'tool', 'text': '在跑命令…'})
        assert s.text == '在跑命令…'

    def test_unhashable_state_does_not_raise(self):
        """state 是个 list 时不能抛 TypeError（unhashable），要回退成 waiting。"""
        s = view_model.normalize({'state': ['tool'], 'text': 'x'})
        assert s.state == 'waiting'
        assert s.text == 'x'


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

    def test_load_settings_non_object_returns_empty(self, tmp_path):
        """settings.json 里是数组/标量时必须回退成空 dict（否则写设置会 TypeError）。"""
        p = tmp_path / 'settings.json'
        p.write_text('[1,2,3]', encoding='utf-8')
        assert state_reader.load_settings(str(p)) == {}
        p.write_text('"hi"', encoding='utf-8')
        assert state_reader.load_settings(str(p)) == {}
        p.write_text('null', encoding='utf-8')
        assert state_reader.load_settings(str(p)) == {}

    def test_save_settings_is_atomic(self, tmp_path, monkeypatch):
        """写到一半炸掉也不能把旧设置留成半截 JSON，且不留临时文件。"""
        p = tmp_path / 'settings.json'
        state_reader.save_settings(str(p), {'size': '小'})

        def boom(*_a, **_k):
            raise OSError('磁盘满了')

        monkeypatch.setattr(state_reader.json, 'dump', boom)
        state_reader.save_settings(str(p), {'size': '大'})
        assert state_reader.load_settings(str(p)) == {'size': '小'}  # 旧值还在
        assert [f.name for f in tmp_path.iterdir()] == ['settings.json']  # 无临时文件残留


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


class TestCliArgs:
    """命令行解析：--shot 的路径不是运行目录（否则桌宠找不到状态文件）。"""

    def test_run_dir_only(self):
        run_dir, shot = cli_args.parse_args(['/run/dir'], '/default')
        assert (run_dir, shot) == ('/run/dir', None)

    def test_shot_path_is_not_run_dir(self):
        run_dir, shot = cli_args.parse_args(['--shot', '/tmp/shot.png'], '/default')
        assert run_dir == '/default'
        assert shot == '/tmp/shot.png'

    def test_run_dir_and_shot(self):
        run_dir, shot = cli_args.parse_args(['--shot', '/tmp/s.png', '/run/dir'], '/default')
        assert (run_dir, shot) == ('/run/dir', '/tmp/s.png')

    def test_shot_without_path(self):
        run_dir, shot = cli_args.parse_args(['--shot'], '/default')
        assert run_dir == '/default'
        assert shot == ''

    def test_flags_are_not_positional(self):
        run_dir, shot = cli_args.parse_args(['--verbose', '/run/dir'], '/default')
        assert run_dir == '/run/dir'

    def test_empty_uses_default(self):
        run_dir, shot = cli_args.parse_args([], '/default')
        assert run_dir == '/default'
        assert shot is None
