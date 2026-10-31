# #14 风险规则：tool + summary/detail → high/medium/low（specs/permission.md §5.6）。
# 纯函数、不用 LLM、只做提示不自动拒绝/允许；规则表可整体替换（RiskRules），关闭开关在卡片层。
from __future__ import annotations

import re

HIGH = 'high'
MEDIUM = 'medium'
LOW = 'low'

WRITE_TOOLS = frozenset({'Write', 'Edit'})

# 命令文本规则：命中即 high（在 medium 之前判）。
# rm 需同时带 r 和 f 标志（rm -rf / rm -fr）；curl|sh 覆盖 ba/z/da sh 前缀。
_HIGH = (
    re.compile(r'\bsudo\b'),
    re.compile(r'\brm\b(?=(?:[^|;&\n])*?-[A-Za-z]*r)(?=(?:[^|;&\n])*?-[A-Za-z]*f)'),
    re.compile(r'(?:curl|wget)\b[^|;&\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b'),
    re.compile(r'\bchmod\s+(?:-R\s+)?777\b'),
    re.compile(r'\bgit\s+push\b[^|;&\n]*(?:--force\b|-f\b)'),
    # 凭据面：碰到 ssh/密钥文件即是 high（读写都值得红牌）
    re.compile(r'\.ssh/|\bid_rsa\b|\bid_ed25519\b|\bauthorized_keys\b|\.pem\b'),
)

# .env 单列：spec 写的是「写 .env」，纯读不标破坏性。
_ENV = re.compile(r'(?:^|[\s/&])\.env\b')
_WRITE_HINT = re.compile(r'>|\bcp\b|\bmv\b|\btee\b|\brm\b|\bchmod\b|\bchown\b|\binstall\b')

_MEDIUM = (
    re.compile(r'\bgit\s+reset\b[^|;&\n]*--hard\b'),
    re.compile(r'\b(?:npm|pnpm)\b[^|;&\n]*\s(?:-g|--global)\b|\byarn\s+global\b'),
    re.compile(r'\bpip3?\s+install\b'),
    re.compile(r'\bbrew\s+(?:install|uninstall)\b'),
    re.compile(r'\b(?:curl|wget)\b'),  # 剩下的 curl/wget = 普通网络下载
)

# 项目外路径（Write/Edit 的目标以 / ~ .. 开头）→ medium
_OUTSIDE = re.compile(r'^\s*(?:/|~|\.\.)')


class RiskRules:
    """规则表。默认按 spec §5.6；测试/配置可整体替换（传入自己的 pattern 元组）。"""

    def __init__(self, high=_HIGH, medium=_MEDIUM) -> None:
        self.high = high
        self.medium = medium


DEFAULT = RiskRules()


def _env_write(tool: str, text: str) -> bool:
    """spec 写的是「写 .env」：Write/Edit 工具或命令带写操作符才算，纯读不算。"""
    if not _ENV.search(text):
        return False
    return tool in WRITE_TOOLS or bool(_WRITE_HINT.search(text))


def _outside_project(tool: str, summary: str, detail: str) -> bool:
    if tool not in WRITE_TOOLS:
        return False
    return bool(_OUTSIDE.match(detail) or _OUTSIDE.match(summary))


def assess(tool: str, summary: str, detail: str = '', rules: RiskRules | None = None) -> str:
    """输入 tool + 摘要/详情，输出风险档位。任何输入都不抛异常。"""
    r = rules or DEFAULT
    text = f'{summary}\n{detail}'
    try:
        for pat in r.high:
            if pat.search(text):
                return HIGH
        if _env_write(tool, text):
            return HIGH
        for pat in r.medium:
            if pat.search(text):
                return MEDIUM
        if _outside_project(tool, summary, detail):
            return MEDIUM
    except TypeError:  # 非 str 输入按空文本处理（客户端契约外，防御而已）
        pass
    return LOW
