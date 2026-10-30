# core：状态文件的读取、解析、校验、TTL。只允许依赖 stdlib + fs。
import json
import os
import time

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
    """读设置文件；坏 JSON / 不是对象都回退成空 dict。

    不是对象时必须回退：调用方直接拿返回值写 settings['x']，
    返回 list 会变成 TypeError 而不是「用默认值」。
    """
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(path, settings: dict) -> None:
    """原子写设置：同目录临时文件 + os.replace。

    直接 open(path,'w') 会在写一半被 kill 时留下半截 JSON，
    下次启动设置就全丢了（load_settings 只能回退成 {}）。
    """
    tmp = f'{path}.{os.getpid()}.tmp'
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        remove_quietly(tmp)  # 别把临时文件留在运行目录里


def number(value, default):
    """设置里的数值字段（坐标等）可能是 None/字符串（手改过 settings.json）。

    拿不到合法数字就用默认值，别让 min()/max() 在启动时抛 TypeError。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return value
