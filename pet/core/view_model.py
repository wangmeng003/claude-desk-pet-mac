# core：主会话 → 气泡/动画状态。纯函数，只允许依赖 models + stdlib。
from . import models, state_reader


def normalize(data: dict) -> models.SessionState:
    """原始状态文件 → 视图无关 DTO（默认值与非法值回退和旧实现一致）。"""
    state = data.get('state', 'waiting')
    if not state_reader.known_state(state):
        state = 'waiting'
    sound = data.get('sound')
    if sound not in models.SOUNDS:
        sound = None
    return models.SessionState(
        state=state,
        text=data.get('text', ''),
        project=data.get('project', ''),
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
