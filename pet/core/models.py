# core：状态 DTO、枚举、常量。只允许 stdlib，不 import 平台 API。
from dataclasses import dataclass

# 状态协议 v1 的 8 个核心状态（specs/state.md §3）。
# aborted 映射到 error（旧格式兼容）、stone 是渲染层彩蛋，都不是协议状态。
PROTOCOL_STATES = ('idle', 'thinking', 'tool', 'reading', 'waiting',
                   'attention', 'celebrate', 'error')

# 状态 → 立绘（pet_mac.py / pet.pyw 与测试都从这儿拿，保证两平台一致）。
# stone 只在渲染层用（连续 error 触发的彩蛋），不出现在状态文件里。
SPRITES = {
    'thinking': 'smile-closed',
    'tool': 'typing',
    'reading': 'notes',
    'waiting': 'knock',
    'attention': 'knock',      # 协议 §3：attention 立绘回退 knock
    'celebrate': 'confetti',
    'idle': 'smile',
    'error': 'panic',
    'stone': 'stone',
}
SIZES = {'小': 140, '中': 190, '大': 250}  # 角色高度（屏幕点数 / 100% 缩放像素）
IDLE_AFTER = 10 * 60  # 等你回复超过 10 分钟就开始发呆
IDLE_TEXT = '在发呆～ zZ'

SOUNDS = ('done', 'error')  # 状态文件里合法的声音字段值

# 状态 TTL（specs/state.md §1.2）：now - ts 超过 TTL 视为该会话不再活跃。
# 生命周期（#4）用它判断桌宠何时退出；聚合展示（M3）用它过滤过期会话。
STATE_TTL = {
    'thinking': 30 * 60,
    'tool': 30 * 60,
    'reading': 30 * 60,
    'waiting': 24 * 3600,
    'attention': 24 * 3600,
    'error': 24 * 3600,
    'celebrate': 5 * 60,
    'idle': 5 * 60,
}
FUTURE_TS_TOLERANCE = 5 * 60  # ts 在未来超过 5 分钟 = 坏数据（写入方时钟异常）


@dataclass(frozen=True)
class SessionState:
    """单个会话状态文件解析后的视图无关表示（normalize 的产物）。"""
    state: str
    text: str
    project: str
    sound: str | None  # None = 不播；否则是 SOUNDS 里的值
    session: str = ''  # 会话 id（协议 v1）：原生通知的去重键用（#11）


@dataclass(frozen=True)
class PermissionRequestViewModel:
    """权限审批卡片的数据（#13）。renderer 只收这个，不 import bridge、不做网络。

    detail 只进内存和卡片：状态文件、日志、通知都不写它（specs/permission.md §5.3）。
    """
    id: str
    session: str
    tool: str
    project: str
    summary: str
    detail: str
    risk: str  # low/medium/high；bridge 取 max(客户端上报, 本地规则计算)
    ts: float
