# platform/mac：Claude 进程检测、前台判断、聚焦。唯一接触 NSWorkspace + pgrep/ps 的地方。
from __future__ import annotations

import os
import subprocess
import time

from AppKit import NSWorkspace


def claude_pids() -> set[int]:
    """正在跑的 claude 进程 pid 列表；查不到就当作还在跑。"""
    try:
        out = subprocess.run(['pgrep', '-f', r'(^|/)claude( |$)|node.*claude'],
                             capture_output=True, text=True, timeout=10).stdout
        mine = {os.getpid(), os.getppid()}
        return {int(p) for p in out.split() if p.isdigit() and int(p) not in mine}
    except Exception:
        return {0}


def ppid(pid: int) -> int | None:
    try:
        out = subprocess.run(['ps', '-o', 'ppid=', '-p', str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) if out.isdigit() else None
    except Exception:
        return None


def claude_app_pids() -> set[int]:
    """包着 claude 进程的 App（终端/iTerm/编辑器）的 pid 集合。"""
    ws = NSWorkspace.sharedWorkspace()
    app_pids = {a.processIdentifier() for a in ws.runningApplications() if a.processIdentifier() > 0}
    result = set()
    for pid in claude_pids():
        seen = set()
        while pid > 1 and pid not in seen:
            seen.add(pid)
            if pid in app_pids:
                result.add(pid)
                break
            pid = ppid(pid) or 0
    return result


def bring_claude_front() -> bool:
    """双击/菜单「去处理」：把跑着 claude 的那个 App 叫到前台。

    返回是否找到并激活了窗口——失败时调用方在气泡里给出项目路径（#11）。
    """
    ws = NSWorkspace.sharedWorkspace()
    for a in ws.runningApplications():
        if a.processIdentifier() in claude_app_pids():
            a.activateWithOptions_(1 << 1)  # ignoreOtherApps
            return True
    return False


class ForegroundWatch:
    """claude_app_pids 30s 刷新一次，避免每个 focus tick 都跑 pgrep/ps。"""

    def __init__(self) -> None:
        self.app_pids: set[int] = set()
        self.app_pids_at = 0.0

    def claude_is_foreground(self) -> bool:
        now = time.time()
        if now - self.app_pids_at > 30:
            self.app_pids, self.app_pids_at = claude_app_pids(), now
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        return bool(front) and front.processIdentifier() in self.app_pids
