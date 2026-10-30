"""#4 生命周期：活跃会话 = ts + 状态 TTL（specs/state.md §1.2），不用 pgrep/tasklist。

纯 core 逻辑，跨平台可跑；两平台 watch_lifecycle 的宽限与退出动作留在平台层（ golden 冒烟覆盖）。
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PET_DIR = REPO / 'pet'
if str(PET_DIR) not in sys.path:
    sys.path.insert(0, str(PET_DIR))

from conftest import write_session  # noqa: E402
from core import sessions, state_reader  # noqa: E402

NOW = time.time()


def test_canonical_state_aborted_maps_to_error():
    assert state_reader.canonical_state('aborted') == 'error'


def test_canonical_state_unknown_falls_back_idle():
    assert state_reader.canonical_state('hacked') == 'idle'
    assert state_reader.canonical_state(None) == 'idle'
    assert state_reader.canonical_state(123) == 'idle'


def test_live_within_ttl_by_state():
    ttl_cases = [
        ('thinking', 29 * 60, True), ('thinking', 31 * 60, False),
        ('tool', 29 * 60, True), ('tool', 31 * 60, False),
        ('reading', 29 * 60, True), ('reading', 31 * 60, False),
        ('waiting', 23 * 3600, True), ('waiting', 25 * 3600, False),
        ('attention', 23 * 3600, True), ('attention', 25 * 3600, False),
        ('error', 23 * 3600, True), ('error', 25 * 3600, False),
        ('celebrate', 4 * 60, True), ('celebrate', 6 * 60, False),
        ('idle', 4 * 60, True), ('idle', 6 * 60, False),
    ]
    for state, age, live in ttl_cases:
        assert state_reader.is_live_data({'state': state, 'ts': NOW - age}, NOW) is live, \
            f'{state} age={age}s 应为 live={live}'


def test_boundary_is_live():
    # 刚好等于 TTL 仍算活跃（now - ts <= ttl）
    assert state_reader.is_live_data({'state': 'idle', 'ts': NOW - 5 * 60}, NOW) is True


def test_aborted_uses_error_ttl():
    assert state_reader.is_live_data({'state': 'aborted', 'ts': NOW - 60}, NOW) is True
    assert state_reader.is_live_data({'state': 'aborted', 'ts': NOW - 25 * 3600}, NOW) is False


def test_unknown_state_uses_idle_ttl():
    assert state_reader.is_live_data({'state': 'hacked', 'ts': NOW - 60}, NOW) is True
    assert state_reader.is_live_data({'state': 'hacked', 'ts': NOW - 6 * 60}, NOW) is False


def test_bad_ts_not_live():
    assert state_reader.is_live_data({'state': 'waiting'}, NOW) is False
    assert state_reader.is_live_data({'state': 'waiting', 'ts': '1760000005'}, NOW) is False
    assert state_reader.is_live_data({'state': 'waiting', 'ts': None}, NOW) is False
    assert state_reader.is_live_data({'state': 'waiting', 'ts': True}, NOW) is False


def test_future_ts_beyond_tolerance_not_live():
    assert state_reader.is_live_data({'state': 'waiting', 'ts': NOW + 6 * 60}, NOW) is False
    assert state_reader.is_live_data({'state': 'waiting', 'ts': NOW + 3 * 60}, NOW) is True


class TestHasLiveSession:
    def test_one_live_among_dead(self, tmp_path):
        d = tmp_path / 'sessions'
        d.mkdir()
        write_session(d, 'dead', {'state': 'thinking', 'ts': NOW - 3600}, age=100)
        write_session(d, 'live', {'state': 'waiting', 'ts': NOW - 10}, age=1)
        write_session(d, 'bad', raw='{{{', age=1)
        assert sessions.has_live_session(str(d), NOW) is True

    def test_all_dead(self, tmp_path):
        d = tmp_path / 'sessions'
        d.mkdir()
        write_session(d, 'a', {'state': 'idle', 'ts': NOW - 3600}, age=100)
        write_session(d, 'b', {'state': 'thinking', 'ts': NOW - 3600}, age=100)
        assert sessions.has_live_session(str(d), NOW) is False

    def test_empty_dir(self, tmp_path):
        d = tmp_path / 'sessions'
        d.mkdir()
        assert sessions.has_live_session(str(d), NOW) is False
