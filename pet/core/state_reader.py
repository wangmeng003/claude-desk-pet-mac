# core：状态文件的读取、解析、校验、TTL。只允许依赖 models + stdlib + fs。
import json
import os
import time

from . import models

EXPIRE_AFTER = 2 * 86400  # 状态文件保留两天，scan 时顺手清掉更旧的


def file_mtime(path):
    """文件 mtime；不存在/已消失返回 None（调用方决定怎么容忍）。"""
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def is_expired(mtime: float, now: float | None = None) -> bool:
    return (time.time() if now is None else now) - mtime > EXPIRE_AFTER


def remove_quietly(path) -> bool:
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def read_state_file(path) -> dict | None:
    """读一个状态文件；坏 JSON / 不是对象 / 读不到都返回 None（读方容忍）。"""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_settings(path) -> dict:
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(path, settings: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False)
    except Exception:
        pass


def known_state(state) -> bool:
    return state in models.SPRITES
