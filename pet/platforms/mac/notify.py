# platform/mac：提示音。M1 后续的原生通知/Dock 弹跳也归这里（见 MILESTONES M2 阶段 1）。
from __future__ import annotations

import subprocess


def play_sound(path: str) -> None:
    try:
        subprocess.Popen(['afplay', path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
