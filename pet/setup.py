#!/usr/bin/env python3
# 准备 macOS 桌宠的 Python 环境：venv + Pillow + pyobjc-framework-Cocoa
# 用法：python3 setup.py [运行目录] [--force]
# 退出码：0 环境就绪；1 准备失败；2 上次失败不到 1 小时，先跳过重试
import os
import shutil
import subprocess
import sys
import time

DEFAULT_RUN_DIR = os.path.join(os.path.expanduser('~'), '.claude', 'desk-pet')
_args = [a for a in sys.argv[1:] if not a.startswith('--')]
RUN_DIR = _args[0] if _args else DEFAULT_RUN_DIR
FORCE = '--force' in sys.argv
VENV = os.path.join(RUN_DIR, 'venv')
PYTHON = os.path.join(VENV, 'bin', 'python')
LOG = os.path.join(RUN_DIR, 'setup.log')
FAILED = os.path.join(RUN_DIR, 'setup-failed')
RETRY_AFTER = 3600  # 失败后一小时内不重复尝试，/pet setup 可强制重试


def log(message):
    try:
        os.makedirs(RUN_DIR, exist_ok=True)
        if os.path.exists(LOG) and os.path.getsize(LOG) > 200_000:
            os.replace(LOG, LOG + '.1')
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}\n')
    except Exception:
        pass


def quiet(argv, timeout):
    """只返回退出码，不写日志（用于探测解释器和依赖）。"""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).returncode
    except Exception:
        return 1


def run(argv, timeout):
    log('$ ' + ' '.join(argv))
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f'超时（{timeout}s）')
        return 1
    except OSError as err:
        log(f'无法执行：{err}')
        return 1
    out = (proc.stdout or '').strip()
    err = (proc.stderr or '').strip()
    if out:
        log(out[-4000:])
    if err:
        log(err[-4000:])
    return proc.returncode


def version_of(path):
    try:
        proc = subprocess.run(
            [path, '-c', 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")'],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            major, minor = proc.stdout.strip().split('.')[:2]
            return (int(major), int(minor))
    except Exception:
        pass
    return (0, 0)


def find_python():
    """优先用 3.10+（pyobjc 有现成 wheel），没有就用系统 python3。"""
    override = os.environ.get('PET_SETUP_PYTHON')
    if override:
        return override
    candidates = [
        'python3.12', 'python3.13', 'python3.11', 'python3.10',
        'python3', '/usr/bin/python3',
    ]
    seen = set()
    fallback = sys.executable
    fallback_ver = version_of(fallback)
    for name in candidates:
        path = name if name.startswith('/') else shutil.which(name)
        if not path:
            continue
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        ver = version_of(path)
        if ver >= (3, 9):
            return path
        if ver > fallback_ver:
            fallback, fallback_ver = path, ver
    return fallback


def deps_ok():
    if not os.path.exists(PYTHON):
        return False
    return quiet([PYTHON, '-c', 'import PIL, objc'], 30) == 0


def install_deps():
    version = version_of(PYTHON)
    if version < (3, 9):
        log(f'需要 Python 3.9+，当前 {version[0]}.{version[1]}')
        return 1

    # Python 3.9 没有 pyobjc 12 的 wheel，用 11.1（有 cp39 universal2 wheel）
    pyobjc = 'pyobjc-framework-Cocoa==11.1' if version < (3, 10) else 'pyobjc-framework-Cocoa'
    argv = [
        PYTHON, '-m', 'pip', 'install',
        '--disable-pip-version-check', '--no-input', '--only-binary', ':all:',
        '--retries', '2', '--timeout', '30',
        'pillow', pyobjc,
    ]
    code = run(argv, 600)
    if code != 0 and version >= (3, 10):
        log('最新版 pyobjc 没有可用 wheel，改试 11.1')
        argv[-1] = 'pyobjc-framework-Cocoa==11.1'
        code = run(argv, 600)
    return code


def mark_failed():
    try:
        with open(FAILED, 'w', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
    except Exception:
        pass


def clear_failed():
    try:
        os.remove(FAILED)
    except OSError:
        pass


def main():
    os.makedirs(RUN_DIR, exist_ok=True)
    log(f'检查桌宠环境：python={sys.executable} venv={VENV}')

    if deps_ok():
        clear_failed()
        log('环境已就绪')
        return 0

    if not FORCE and os.path.exists(FAILED):
        try:
            age = time.time() - os.path.getmtime(FAILED)
        except OSError:
            age = RETRY_AFTER
        if age < RETRY_AFTER:
            log(f'上次准备失败 {int(age)} 秒前，先跳过；/pet setup 可强制重试')
            return 2

    if not os.path.exists(PYTHON):
        base = find_python()
        log(f'创建 venv：{base}（{version_of(base)[0]}.{version_of(base)[1]}）')
        if run([base, '-m', 'venv', VENV], 120) != 0:
            log('创建 venv 失败')
            mark_failed()
            return 1

    log(f'安装依赖：{version_of(PYTHON)[0]}.{version_of(PYTHON)[1]}')
    if install_deps() != 0 or not deps_ok():
        log('依赖安装失败')
        mark_failed()
        return 1

    clear_failed()
    log('环境就绪')
    return 0


if __name__ == '__main__':
    sys.exit(main())
