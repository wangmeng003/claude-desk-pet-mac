# #13 审批状态机：idle → pending → allowed/denied/ask（specs/permission.md §5.4）。
# 同一时刻一个请求；忙时由 server 层立即 409；宠物退出时 fail_all 把 pending 转 ask。
# 线程安全：HTTP handler 线程 wait，UI 线程 decide。
from __future__ import annotations

import threading
import time

DECISIONS = frozenset({'allow', 'deny', 'ask'})
DEFAULT_TIMEOUT = 600.0  # bridge 等用户 600s；客户端 HTTP 超时 610s（spec §5.4）
_DONE_CAP = 4096  # 已答复 id 集合的容量（防无界增长；请求频率是人手级别，够用）


class PermissionGate:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT,
                 clock=time.monotonic) -> None:
        self._timeout = timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._pending_id: str | None = None
        self._decision: tuple[str, str] | None = None  # (decision, reason)
        self._done_ids: set[str] = set()

    def begin(self, rid: str) -> bool:
        """占住状态机；已忙或该 id 答复过 → False（server 回 409，重复不弹卡）。"""
        with self._lock:
            if self._pending_id is not None or self._decision is not None \
                    or rid in self._done_ids:
                return False
            self._pending_id = rid
            self._event.clear()
            return True

    def decide(self, rid: str, decision: str, reason: str = 'user') -> bool:
        """用户/超时/错误给出决策；不作用于别的 id（会话不串）。"""
        if decision not in DECISIONS:
            return False
        with self._lock:
            if self._pending_id != rid or self._decision is not None:
                return False
            self._decision = (decision, reason)
            self._event.set()
            return True

    def wait(self, rid: str) -> tuple[str, str]:
        """阻塞到决策或超时；只有 pending 中的 rid 能等。"""
        deadline = self._clock() + self._timeout
        while True:
            with self._lock:
                if self._pending_id != rid:
                    return ('ask', 'busy')  # begin 之后不该发生，防御
                if self._decision is not None:
                    out = self._decision
                    self._finish(rid)
                    return out
                left = deadline - self._clock()
            if left <= 0 or not self._event.wait(left):
                with self._lock:
                    if self._pending_id == rid and self._decision is None:
                        self._finish(rid)
                        return ('ask', 'timeout')
                    # 决策恰好赶在超时判定前写入：下一轮循环取走

    def fail_all(self, reason: str = 'error') -> None:
        """宠物退出/桥关闭：pending 立即转 ask，等在 wait 上的 handler 拿到响应。"""
        with self._lock:
            if self._pending_id is not None and self._decision is None:
                self._decision = ('ask', reason)
                self._event.set()

    def _finish(self, rid: str) -> None:
        self._pending_id = None
        self._decision = None
        self._event.clear()
        self._done_ids.add(rid)
        if len(self._done_ids) > _DONE_CAP:
            self._done_ids.clear()
