# core：主会话 → 气泡/动画状态。纯函数，只允许依赖 models + stdlib。
from . import models


def _text(value) -> str:
    """text/project 必须是字符串；坏数据回退成空串。

    状态文件是外部写进来的，非字符串会一路流到渲染层
    （气泡绘制 / endswith 直接抛异常），必须在边界挡掉。
    """
    return value if isinstance(value, str) else ''


def normalize(data: dict) -> models.SessionState:
    """原始状态文件 → 视图无关 DTO（状态协议 v1 §1.3/§3）。

    - 'aborted' 是旧格式，映射到 error（文案保留）；
    - 未知/缺失/非字符串 state 回退 idle（协议：坏数据按「没有活跃工作」处理）；
    - v1 新增字段（v/session/agent/attention）读取方忽略。
    """
    state = data.get('state')
    if state == 'aborted':
        state = 'error'
    elif not (isinstance(state, str) and state in models.PROTOCOL_STATES):
        state = 'idle'
    sound = data.get('sound')
    if sound not in models.SOUNDS:
        sound = None
    return models.SessionState(
        state=state,
        text=_text(data.get('text', '')),
        project=_text(data.get('project', '')),
        sound=sound,
    )


def effective_state(state: str, state_since: float, now: float) -> str:
    """waiting 超过 IDLE_AFTER 转成 idle 发呆。"""
    if state == 'waiting' and now - state_since > models.IDLE_AFTER:
        return 'idle'
    return state


def display_text(state: str, text: str, now: float, state_since: float) -> str:
    """气泡文案规则（Windows 版）：发呆覆盖，其余透传。"""
    if effective_state(state, state_since, now) == 'idle':
        return models.IDLE_TEXT
    return text


def display_text_with_dots(state: str, text: str, now: float, state_since: float) -> str:
    """气泡文案规则（macOS 版）：发呆覆盖；'思考中' 类文案加跳动省略号。"""
    if effective_state(state, state_since, now) == 'idle':
        return models.IDLE_TEXT
    if state == 'thinking' and text.endswith('中'):
        return thinking_dots(text, now)
    return text


def thinking_dots(text: str, now: float) -> str:
    """'思考中' → '思考中.'/'思考中..'/'思考中...' 循环跳动。"""
    return text + '.' * (int(now * 2.5) % 3 + 1)
