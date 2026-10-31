# platform/mac：提示音与原生通知。
# 通知走 osascript（display notification）：脚本进程稳定可用、免权限 API；
# UNUserNotificationCenter 需要真实 bundle 身份，裸 python 进程拿不到稳定的点按回调，
# 留到 M2 #11（attention）再评估。Dock 弹跳对本应用无意义（accessory 无 Dock 图标）。
from __future__ import annotations

import subprocess


def play_sound(path: str) -> None:
    try:
        subprocess.Popen(['afplay', path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _quote(text: str) -> str:
    """AppleScript 字符串字面量：双引号转义。"""
    return text.replace('\\', '\\\\').replace('"', '\\"')


def notify(title: str, body: str, sound: bool = False) -> None:
    """原生通知（Notification Center）。失败静默——通知是加分项，不是命脉。

    sound=True 时横幅自带铃声（#11：attention 用系统音 Glass）。
    """
    try:
        script = (f'display notification "{_quote(body)}" '
                  f'with title "{_quote(title)}"')
        if sound:
            script += ' sound name "Glass"'
        subprocess.Popen(['osascript', '-e', script], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
