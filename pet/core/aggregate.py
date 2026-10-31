# core：多会话聚合（M3 #20，specs/state.md §5）。纯函数，只允许依赖
# models/state_reader/view_model + stdlib + fs；平台层只消费结果，不做业务判断。
import glob
import os
from dataclasses import dataclass, replace

from . import models, state_reader, view_model


def collect(sessions_dir, now: float) -> list[models.SessionState]:
    """扫描 sessions/*.json → 活跃会话列表（§5.1）。

    - TTL 按状态推导（ts + STATE_TTL），不按 mtime；
    - ts 在未来超过 5 分钟 / 缺 ts / 坏 JSON → 跳过；
    - session 字段缺失时用文件名补（协议 §6 旧格式兼容）；
    - 超过 EXPIRE_AFTER 的旧文件顺手清掉（沿用 read_latest 的清理语义）。
    """
    out = []
    for p in glob.glob(os.path.join(sessions_dir, '*.json')):
        try:
            if now - os.path.getmtime(p) > state_reader.EXPIRE_AFTER:
                os.remove(p)
                continue
            data = state_reader.read_state_file(p)
            if data is None:
                continue
            s = view_model.normalize(data)
            if s.session == '':
                sid = os.path.splitext(os.path.basename(p))[0]
                s = replace(s, session=sid)
            if not state_reader.is_live_data(data, now):
                continue
            out.append(s)
        except Exception:
            continue
    return out


def sort_key(s: models.SessionState):
    """主会话排序键（§5.2）：需要你 > 优先级 > 新事件 > 确定性 tie-break。

    max() 语义下 True > False、ts 大者胜、id 大者胜；同一输入必然同一输出。
    """
    return (s.attention, models.PRIORITY[s.state], s.ts, s.session)


@dataclass(frozen=True)
class AggregateResult:
    """一次聚合的结果：主会话 + 会话数 + 需要处理的数量（气泡/菜单消费）。"""
    main: models.SessionState | None
    total: int
    waiting: int


def pick(states: list[models.SessionState], pinned: str = '') -> AggregateResult:
    """选主会话 + 计数（§5.2/§5.3）。

    pinned（#19 设计口径）：用户点菜单选中的会话 id，存活期间一直当主会话，
    优先级规则不抢；该会话不在列表里（过期/结束）就自然回退到聚合主会话。
    """
    if not states:
        return AggregateResult(None, 0, 0)
    main = None
    if pinned:
        main = next((s for s in states if s.session == pinned), None)
    if main is None:
        main = max(states, key=sort_key)
    waiting = sum(1 for s in states if s.attention)
    return AggregateResult(main, len(states), waiting)


def session_entries(states: list[models.SessionState], main_session: str,
                    now: float) -> list[tuple[str, str, bool]]:
    """菜单会话区的数据（M3 #22）：(文案, session id, 是否主会话)，按 sort_key 倒序。

    平台层（mac NSMenu / Windows tkinter）只画这个列表，不排序不拼文案。
    """
    return [(view_model.session_label(s, now), s.session, s.session == main_session)
            for s in sorted(states, key=sort_key, reverse=True)]
