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
    - v1 新增字段里 session/ts/attention 保留（#11 去重键、M3 #20 聚合排序/计数），
      v/agent 读取方忽略。
    """
    state = data.get('state')
    if state == 'aborted':
        state = 'error'
    elif not (isinstance(state, str) and state in models.PROTOCOL_STATES):
        state = 'idle'
    sound = data.get('sound')
    if sound not in models.SOUNDS:
        sound = None
    ts = data.get('ts')
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        ts = 0.0
    attention = data.get('attention')
    if not isinstance(attention, bool):
        attention = state in models.DEFAULT_ATTENTION
    return models.SessionState(
        state=state,
        text=_text(data.get('text', '')),
        project=_text(data.get('project', '')),
        sound=sound,
        session=_text(data.get('session', '')),
        ts=float(ts),
        attention=attention,
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
NOTIFY_STATES = frozenset({'celebrate', 'error', 'attention'})

# 同一件事 2 秒内只通知一次（#11）
DEDUP_WINDOW = 2.0


class NotifyGate:
    """原生通知的最后一道闸（#6/#11）：开关 + 勿扰 + 2 秒去重。

    - settings['notify'] 为 False 时整体关闭（桌宠菜单开关）；
    - changed=False（同状态重复写文件）不通知，避免反复弹窗；
    - settings['dnd']（勿扰模式）不弹横幅不响铃，气泡/表情照常（渲染层与此闸无关）；
    - 去重键 = (session, state, text)：同一会话/工具/摘要 2 秒内只放行一次。
      键里含 state，attention 不会被刚弹过的 celebrate 窗口吃掉
      （#11：权限事件优先于完成通知）。
    """

    def __init__(self) -> None:
        self._key: tuple[str, str, str] | None = None
        self._at: float = 0.0

    def allow(self, state: str, text: str, session: str,
              changed: bool, settings: dict | None, now: float) -> bool:
        if not changed or state not in NOTIFY_STATES:
            return False
        if settings is not None:
            if not settings.get('notify', True):
                return False
            if settings.get('dnd'):
                return False
        key = (session, state, text)
        if key == self._key and now - self._at < DEDUP_WINDOW:
            return False
        self._key, self._at = key, now
        return True


def notify_sound(state: str) -> bool:
    """通知自带声音（#11）：只有 attention 响铃（权限提醒最要紧）；
    完成/出错的声音走状态文件里的提示音，横幅不再重复响。
    """
    return state == 'attention'


def notify_body(text: str, project: str, privacy: bool) -> str:
    """通知正文（#6）：气泡文案 + 聚焦提示；隐私模式下不带项目名。

    通知点按在脚本进程里拿不到回调（点击聚焦做不到），
    正文常备「双击桌宠回到终端」，失败路径按 issue 要求展示项目名。
    """
    head = f'{text} · {project}' if (project and not privacy) else text
    return f'{head}（双击桌宠回到终端）'


# ---------- 审批卡片（#15，specs/permission.md §5.5） ----------

CARD_TIMEOUT = 600.0  # 与 bridge gate 同步；超时由 gate 转 ask，卡片只展示剩余时间


def card_countdown_text(remaining: float) -> str:
    """剩余秒数 → mm:ss；到点显示等待回退。"""
    if remaining <= 0:
        return '已超时，回退终端…'
    m, s = divmod(int(remaining), 60)
    return f'{m:02d}:{s:02d}'


def card_default_focus(risk: str) -> str:
    """默认焦点/回车键（§5.5）：高风险默认「回退终端」，低风险默认「允许」。"""
    return 'defer' if risk == 'high' else 'allow'
