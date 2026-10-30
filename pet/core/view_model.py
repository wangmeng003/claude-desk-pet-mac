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


# 要发原生通知的状态（#6）：长任务完成（celebrate）、出错（error）、需要你看（attention）。
# 同状态重复刷新由调用方的 changed 挡掉，这里只看状态本身。
NOTIFY_STATES = frozenset({'celebrate', 'error', 'attention'})


def wants_notify(state: str, changed: bool, settings: dict | None = None) -> bool:
    """状态切换到值得打扰用户的状态时发一次原生通知。

    - settings['notify'] 为 False 时整体关闭（桌宠菜单开关）；
    - changed=False（同状态重复写文件）不通知，避免反复弹窗。
    """
    if settings is not None and not settings.get('notify', True):
        return False
    return changed and state in NOTIFY_STATES


def notify_body(text: str, project: str, privacy: bool) -> str:
    """通知正文（#6）：气泡文案 + 聚焦提示；隐私模式下不带项目名。

    通知点按在脚本进程里拿不到回调（点击聚焦做不到），
    正文常备「双击桌宠回到终端」，失败路径按 issue 要求展示项目名。
    """
    head = f'{text} · {project}' if (project and not privacy) else text
    return f'{head}（双击桌宠回到终端）'
