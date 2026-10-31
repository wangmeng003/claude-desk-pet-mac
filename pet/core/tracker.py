# core：多会话 poll 帧逻辑（M3 #21，specs/state.md §5）。把「这一帧该显示
# 什么/响什么/通知什么」从平台层收进 core：pet_mac / pet.pyw 只执行效果，
# 不复制判断（架构门槛：view model 与渲染分离）。
from dataclasses import dataclass

from . import aggregate, models, view_model


@dataclass(frozen=True)
class NotifyEvent:
    """一个会话转入需通知状态（celebrate/error/attention）的事件。"""
    state: str
    text: str
    project: str
    session: str


@dataclass(frozen=True)
class FrameEffects:
    """一次 poll 的全部效果：平台层照单执行，不做业务判断。"""
    display_state: str          # 可能是 'stone'（渲染层彩蛋）
    display_text: str
    project: str
    main_session: str
    reset_since: bool           # 显示内容变了：重置发呆计时/起跳动画
    sound: str | None           # 本帧要播的一条提示音（None = 不播）
    notifies: list[NotifyEvent] # 本帧要弹的通知（去重/开关/勿扰在平台层 NotifyGate）


class SessionTracker:
    """跨 poll 帧的会话跟踪：每会话上次 (state, ts)、error 连击。

    - 事件 = ts 变化（写入方每次写文件都更新 ts）：石化连击、提示音按事件算；
    - 状态迁移 = state 变化（首见算迁移）：通知按迁移触发；
    - 首见不发声音（对齐旧版 last_mtime_seen 门：桌宠启动不重播历史提示音）。
    """

    def __init__(self) -> None:
        self._prev: dict[str, tuple[str, float]] = {}
        self._streak: dict[str, int] = {}
        self._last_display: tuple[str, str, str, str] | None = None

    def reset(self) -> None:
        """没有活跃会话时清空跟踪：会话过期后同 id 复活按首见处理。"""
        self._prev.clear()
        self._streak.clear()
        self._last_display = None

    def apply(self, states: list[models.SessionState],
              main: models.SessionState) -> FrameEffects:
        live = {s.session for s in states}
        self._prev = {k: v for k, v in self._prev.items() if k in live}
        self._streak = {k: v for k, v in self._streak.items() if k in live}

        notifies: list[NotifyEvent] = []
        sound_candidates: list[models.SessionState] = []
        for s in states:
            prev = self._prev.get(s.session)
            if prev is None:
                first = True
                is_event = changed = True
            else:
                first = False
                is_event = prev[1] != s.ts
                changed = prev[0] != s.state
            self._prev[s.session] = (s.state, s.ts)
            if is_event:
                if s.state == 'error':
                    self._streak[s.session] = self._streak.get(s.session, 0) + 1
                else:
                    self._streak[s.session] = 0
                if not first and s.sound:
                    sound_candidates.append(s)
            if changed and s.state in view_model.NOTIFY_STATES:
                notifies.append(NotifyEvent(s.state, s.text, s.project, s.session))

        # 同帧多个会话都带声音只播优先级最高的一条，不叠音
        winner = max(sound_candidates, key=aggregate.sort_key, default=None)

        state, text = main.state, main.text
        # 石化彩蛋（协议 §3）：主会话连续 3 次 error 由渲染层触发；后台会话的
        # 连击只记账不上屏。
        if state == 'error' and self._streak.get(main.session, 0) >= 3:
            state, text = 'stone', '石化了…'

        display = (main.session, state, text, main.project)
        reset = self._last_display != display
        self._last_display = display
        return FrameEffects(state, text, main.project, main.session, reset,
                            winner.sound if winner is not None else None, notifies)
