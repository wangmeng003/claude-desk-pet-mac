# core：多会话扫描、主会话（最新）选择。只允许依赖 models/state_reader + stdlib。
import glob
import os
import time

from . import state_reader


def read_latest(sessions_dir, now: float | None = None):
    """读所有会话里最新的状态；顺手清掉过期文件。

    返回 (mtime, data) 或 None。坏文件跳过——和旧实现逐行为保持一致。
    """
    best = None
    now = time.time() if now is None else now
    for p in glob.glob(os.path.join(sessions_dir, '*.json')):
        try:
            mtime = os.path.getmtime(p)
            if now - mtime > state_reader.EXPIRE_AFTER:
                os.remove(p)
                continue
            data = state_reader.read_state_file(p)
            if data is None:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, data)
        except Exception:
            continue
    return best
