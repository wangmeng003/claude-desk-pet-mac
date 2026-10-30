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


@dataclass(frozen=True)
class SessionState:
    """单个会话状态文件解析后的视图无关表示（normalize 的产物）。"""
    state: str
    text: str
    project: str
    sound: str | None  # None = 不播；否则是 SOUNDS 里的值
