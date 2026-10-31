"""M3 #20 多会话聚合器单测：优先级选主、TTL 过滤、损坏容忍、确定性（specs/state.md §5）。

聚合器是纯函数（架构门槛）：输入目录/时间，输出视图无关结果；
平台层（pet_mac/pet.pyw）只消费，不做业务判断。
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PET_DIR = REPO / 'pet'
if str(PET_DIR) not in sys.path:
    sys.path.insert(0, str(PET_DIR))

import pytest  # noqa: E402

from conftest import write_session  # noqa: E402
from core import aggregate, models, state_reader, view_model  # noqa: E402

NOW = time.time()


def make(state, ts, session='s', **kw):
    """构造聚合器入参 SessionState 的捷径。"""
    return view_model.normalize({'state': state, 'session': session, 'ts': ts, **kw})


class TestNormalizeNewFields:
    """#20：normalize 读取 ts/attention（此前忽略）；聚合/计数依赖这两个字段。"""

    def test_ts_read(self):
        assert view_model.normalize({'state': 'tool', 'ts': 123.5}).ts == 123.5

    def test_ts_bad_type_falls_back_to_zero(self):
        """非数字 ts（字符串/bool/缺失）= 坏数据，回退 0；TTL 判定自然淘汰。"""
        assert view_model.normalize({'state': 'tool', 'ts': 'x'}).ts == 0.0
        assert view_model.normalize({'state': 'tool', 'ts': True}).ts == 0.0
        assert view_model.normalize({'state': 'tool'}).ts == 0.0

    def test_attention_explicit_bool_overrides_default(self):
        assert view_model.normalize({'state': 'waiting', 'attention': False}).attention is False
        assert view_model.normalize({'state': 'tool', 'attention': True}).attention is True

    def test_attention_default_by_state(self):
        """协议 §3：waiting/attention/error 默认需要你；SessionStart 的 waiting
        由写入方显式 attention=false（§4.1），读取方这里只管缺省推导。"""
        assert view_model.normalize({'state': 'waiting'}).attention is True
        assert view_model.normalize({'state': 'error'}).attention is True
        assert view_model.normalize({'state': 'attention'}).attention is True
        for s in ('tool', 'thinking', 'reading', 'celebrate', 'idle'):
            assert view_model.normalize({'state': s}).attention is False

    def test_attention_non_bool_ignored(self):
        assert view_model.normalize({'state': 'tool', 'attention': 'yes'}).attention is False


class TestCollect:
    """collect：目录 → 活跃 SessionState 列表（TTL 过滤 + 坏数据跳过 + 顺手清过期）。"""

    def test_live_sessions_collected_with_identity(self, tmp_path):
        write_session(tmp_path, 'abc', {'v': 1, 'session': 'abc', 'state': 'tool',
                                        'text': '在改 x.ts', 'project': 'demo', 'ts': NOW - 10})
        states = aggregate.collect(str(tmp_path), now=NOW)
        assert len(states) == 1
        s = states[0]
        assert (s.session, s.state, s.text, s.project) == ('abc', 'tool', '在改 x.ts', 'demo')
        assert s.ts == pytest.approx(NOW - 10)

    def test_session_id_falls_back_to_filename(self, tmp_path):
        """协议 §6：旧格式无 session 字段，用文件名（不含 .json）补。"""
        write_session(tmp_path, 'old1', {'state': 'tool', 'ts': NOW - 10})
        assert aggregate.collect(str(tmp_path), now=NOW)[0].session == 'old1'

    def test_ttl_by_state(self, tmp_path):
        """§1.2：tool 30 分钟过期、waiting 24 小时保留、celebrate 5 分钟。"""
        write_session(tmp_path, 'a', {'state': 'tool', 'ts': NOW - 31 * 60})
        write_session(tmp_path, 'b', {'state': 'waiting', 'ts': NOW - 23 * 3600})
        write_session(tmp_path, 'c', {'state': 'celebrate', 'ts': NOW - 6 * 60})
        got = {s.session for s in aggregate.collect(str(tmp_path), now=NOW)}
        assert got == {'b'}

    def test_future_ts_beyond_tolerance_skipped(self, tmp_path):
        write_session(tmp_path, 'a', {'state': 'tool', 'ts': NOW + 6 * 60})
        write_session(tmp_path, 'b', {'state': 'tool', 'ts': NOW + 4 * 60})
        got = {s.session for s in aggregate.collect(str(tmp_path), now=NOW)}
        assert got == {'b'}

    def test_missing_ts_not_live(self, tmp_path):
        """§8.3：缺 ts → 不参与聚合（normalize ts=0 → 必然超 TTL）。"""
        write_session(tmp_path, 'a', raw='{"state": "tool"}')  # raw：绕过夹具自动补 ts
        assert aggregate.collect(str(tmp_path), now=NOW) == []

    def test_bad_json_skipped(self, tmp_path):
        write_session(tmp_path, 'bad', raw='{"state": "tool", ')
        write_session(tmp_path, 'good', {'state': 'tool', 'ts': NOW - 10})
        got = {s.session for s in aggregate.collect(str(tmp_path), now=NOW)}
        assert got == {'good'}

    def test_stale_file_removed(self, tmp_path):
        """沿用 read_latest 语义：超过 EXPIRE_AFTER 的文件顺手清掉。"""
        write_session(tmp_path, 'dead', {'state': 'waiting', 'ts': NOW},
                      age=state_reader.EXPIRE_AFTER + 60)
        assert aggregate.collect(str(tmp_path), now=NOW) == []
        assert not (tmp_path / 'dead.json').exists()

    def test_empty_dir(self, tmp_path):
        assert aggregate.collect(str(tmp_path), now=NOW) == []


class TestPick:
    """pick：优先级选主 + 计数（specs §5.2/§5.3）。"""

    def test_priority_order(self):
        """attention > error > waiting > celebrate > tool/reading > thinking > idle。"""
        states = [
            make('idle', NOW - 1, 'a'),
            make('thinking', NOW - 2, 'b'),
            make('tool', NOW - 3, 'c'),
            make('celebrate', NOW - 4, 'd'),
            make('waiting', NOW - 5, 'e'),
            make('error', NOW - 6, 'f'),
            make('attention', NOW - 7, 'g'),
        ]
        assert aggregate.pick(states).main.session == 'g'
        states = [s for s in states if s.session != 'g']
        assert aggregate.pick(states).main.session == 'f'
        states = [s for s in states if s.session != 'f']
        assert aggregate.pick(states).main.session == 'e'
        states = [s for s in states if s.session != 'e']
        assert aggregate.pick(states).main.session == 'd'
        states = [s for s in states if s.session != 'd']
        assert aggregate.pick(states).main.session == 'c'
        states = [s for s in states if s.session != 'c']
        assert aggregate.pick(states).main.session == 'b'

    def test_same_priority_newer_ts_wins(self):
        states = [make('tool', NOW - 100, 'old'), make('tool', NOW - 1, 'new')]
        assert aggregate.pick(states).main.session == 'new'

    def test_same_priority_same_ts_session_id_breaks_tie(self):
        """确定性 tie-break：完全同时的事件按 session id，两次调用结果一致。"""
        states = [make('tool', NOW - 5, 'zzz'), make('tool', NOW - 5, 'aaa')]
        picked = aggregate.pick(states).main.session
        assert picked == aggregate.pick(states).main.session
        assert picked == 'zzz'  # max() 语义：id 大者胜

    def test_counts(self):
        """3 会话 2 个等你：waiting/error 默认 attention=True。"""
        states = [
            make('tool', NOW - 1, 'a'),
            make('waiting', NOW - 2, 'b'),
            make('error', NOW - 3, 'c'),
        ]
        r = aggregate.pick(states)
        assert (r.total, r.waiting) == (3, 2)
        assert r.main.session == 'c'

    def test_attention_false_excludes_from_waiting_count(self):
        """SessionStart 的 waiting（attention=false）不算「等你」（§4.1）。"""
        states = [make('waiting', NOW - 1, 'a', attention=False),
                  make('waiting', NOW - 2, 'b')]
        r = aggregate.pick(states)
        assert (r.total, r.waiting) == (2, 1)
        assert r.main.session == 'b'

    def test_empty(self):
        r = aggregate.pick([])
        assert r.main is None
        assert (r.total, r.waiting) == (0, 0)

    def test_pinned_wins_over_priority(self):
        """#19 设计口径：pin 的会话存活期间一直当主会话，优先级不抢。"""
        states = [make('attention', NOW - 1, 'hot'), make('tool', NOW - 2, 'mine')]
        assert aggregate.pick(states, pinned='mine').main.session == 'mine'

    def test_pinned_missing_falls_back(self):
        """被 pin 的会话过期/消失 → 自动回聚合主会话。"""
        states = [make('attention', NOW - 1, 'hot'), make('tool', NOW - 2, 'mine')]
        assert aggregate.pick(states, pinned='gone').main.session == 'hot'

    def test_pinned_empty_string_is_no_pin(self):
        states = [make('attention', NOW - 1, 'hot')]
        assert aggregate.pick(states, pinned='').main.session == 'hot'


class TestPriorityTable:
    def test_matches_spec(self):
        """specs/state.md §3 优先级表（数值越大越优先）。"""
        assert models.PRIORITY == {
            'attention': 90, 'error': 80, 'waiting': 70, 'celebrate': 50,
            'tool': 40, 'reading': 40, 'thinking': 30, 'idle': 0,
        }
