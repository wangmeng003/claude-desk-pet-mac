# core：会话目录的读取辅助。只允许依赖 models/state_reader + stdlib。
# 多会话聚合（M3 #20）见 aggregate.py：collect+pick 取代了旧的 read_latest。
import glob
import os
import time

from . import state_reader


def has_live_session(sessions_dir, now: float | None = None) -> bool:
    """有没有活跃会话（#4 生命周期）：任一脚本按 ts+TTL 判定为活跃即可。

    读取方不再靠 pgrep/tasklist 判断 Claude 活没活着；坏文件跳过。
    """
    now = time.time() if now is None else now
    for p in glob.glob(os.path.join(sessions_dir, '*.json')):
        try:
            data = state_reader.read_state_file(p)
            if data is not None and state_reader.is_live_data(data, now):
                return True
        except Exception:
            continue
    return False
