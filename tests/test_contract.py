"""契约测试：Python 读取方的枚举与 contracts/state.schema.json 对齐。

specs/state.md §6：TS/Python 的枚举和字段必须通过契约测试对齐；
hooks 侧的对齐测试在 hooks/contract.test.ts。
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PET_DIR = REPO / 'pet'
if str(PET_DIR) not in sys.path:
    sys.path.insert(0, str(PET_DIR))

from core import models  # noqa: E402

SCHEMA = json.loads((REPO / 'contracts' / 'state.schema.json').read_text(encoding='utf-8'))
SCHEMA_STATES = SCHEMA['properties']['state']['enum']


class TestStateContract:
    def test_protocol_states_match_schema(self):
        assert list(models.PROTOCOL_STATES) == SCHEMA_STATES

    def test_every_protocol_state_has_sprite(self):
        """协议 §3：新状态必须配立绘/文案才允许加——枚举与 SPRITES 对齐。"""
        for state in models.PROTOCOL_STATES:
            assert state in models.SPRITES, f'协议状态 {state} 缺立绘映射'

    def test_sounds_match_schema(self):
        """schema 的 sound enum 里 'null' 是 JSON Schema 表达可空的方式，Python 侧是 None。"""
        assert list(models.SOUNDS) == ['done', 'error']
        assert set(SCHEMA['properties']['sound']['enum']) == {'done', 'error', 'null'}
