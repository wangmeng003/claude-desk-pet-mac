# /pet doctor 的诊断主体（#7）：hooks 用 python 跑本脚本，把 stdout 回显给用户。
# 引擎没有文件读取 API，所有检查都在这里做；输出成纯文本，路径脱敏（HOME → ~）。
# 用法：python doctor.py <运行目录> <插件根目录> <单实例端口>
# 退出码：0 = 没有 [err]，1 = 有 [err]（hooks 据此提醒）。
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import lock  # noqa: E402  (pet/ 进 sys.path 后才能导入)

LOG_NAMES = ('pet-error.log', 'mod-launch.log', 'setup.log', 'launch.log')
TAIL_LINES = 2
TAIL_CHARS = 120

ok_n = warn_n = err_n = 0


def line(level, label, detail=''):
    global ok_n, warn_n, err_n
    if level == 'ok':
        ok_n += 1
    elif level == 'warn':
        warn_n += 1
    else:
        err_n += 1
    print(f'[{level}] {label}：{detail}' if detail else f'[{level}] {label}')


def redact(text):
    """路径脱敏：HOME → ~，用户名不出现在可直接粘贴的输出里。"""
    home = os.path.expanduser('~')
    return text.replace(home, '~') if home not in ('/', '') else text


def check_env(run_dir, plugin_root):
    line('ok', '平台', f'{sys.platform} / Python {sys.version.split()[0]}')
    try:
        with open(os.path.join(plugin_root, '.claude-plugin', 'plugin.json'),
                  encoding='utf-8') as f:
            version = json.load(f).get('version', '?')
        line('ok', '插件版本', str(version))
    except (OSError, ValueError):
        line('warn', '插件版本', f'读不到 {redact(plugin_root)}/.claude-plugin/plugin.json')

    # 状态目录：存在 + 可写（探针文件写完就删）
    writable = '不可写（状态文件写不进去，桌宠收不到状态）'
    probe = os.path.join(run_dir, '.doctor-probe')
    try:
        os.makedirs(run_dir, exist_ok=True)
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('x')
        os.remove(probe)
        writable = '可写'
    except OSError as err:
        line('err', '运行目录', f'{redact(run_dir)} {writable}：{err}')
        return False  # 后面的检查都依赖这个目录
    line('ok', '运行目录', f'{redact(run_dir)} {writable}')
    return True


def check_sessions(run_dir):
    sessions = os.path.join(run_dir, 'sessions')
    try:
        names = [n for n in os.listdir(sessions) if n.endswith('.json')]
    except OSError:
        line('warn', '状态目录', f'{redact(sessions)} 不存在或读不了（hooks 还没写过状态）')
        return
    latest = sorted(names,
                    key=lambda n: os.path.getmtime(os.path.join(sessions, n)),
                    reverse=True)[:3]
    if not latest:
        line('warn', '状态目录', f'{redact(sessions)} 里没有状态文件（hooks 未生效或会话刚建）')
        return
    now = time.time()
    details = []
    for name in latest:
        path = os.path.join(sessions, name)
        age = int(now - os.path.getmtime(path))
        state = '?'
        try:
            with open(path, encoding='utf-8') as f:
                state = json.load(f).get('state', '?')
        except (OSError, ValueError):
            state = '坏文件'
        details.append(f'{name[:-5]}（{age}s 前，state={state}）')
    line('ok', '状态目录', f'{len(names)} 个会话文件，最新：' + '、'.join(details))


def check_venv(run_dir):
    if sys.platform != 'darwin':
        # Windows：桌宠和 doctor 用同一个 PATH python，直接在当前解释器里查依赖
        missing = [name for name in ('PIL', 'tkinter')
                   if _import_fails(name)]
        if missing:
            line('err', '运行环境', f'{"/".join(missing)} 导入失败（安装 Pillow 后重试，tkinter 随官方 Python 自带）')
        else:
            line('ok', '运行环境', f'Pillow + tkinter 可导入（{sys.executable}）')
        return
    python = os.path.join(run_dir, 'venv', 'bin', 'python')
    if not os.path.exists(python):
        line('err', 'venv', f'{redact(python)} 不存在（运行 /pet setup 重建）')
        return
    try:
        ran = subprocess.run([python, '-c', 'import PIL, objc'],
                             capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        line('err', 'venv', f'{redact(python)} 跑不起来（运行 /pet setup 重建）')
        return
    if ran.returncode == 0:
        line('ok', 'venv', f'Pillow + pyobjc 可导入（{redact(python)}）')
    else:
        detail = ran.stderr.decode('utf-8', 'replace').strip().splitlines()
        line('err', 'venv', f'依赖导入失败（运行 /pet setup 重建）：{detail[-1] if detail else "?"}')


def _import_fails(name):
    try:
        __import__(name)
        return False
    except ImportError:
        return True


def check_lock(run_dir, port):
    data = lock.read_lock(lock.lock_path(run_dir))
    if data is None:
        line('warn', '单实例', '没有锁文件（桌宠没在跑，或异常退出过）')
        return
    pid = data.get('pid')
    alive = lock.valid_pid(pid) and lock.pid_alive(pid)
    age = int(time.time() - (data.get('ts') or 0))
    line('ok' if alive else 'warn', '单实例',
         f'PID {pid}（{"活着" if alive else "已退出"}，{age}s 前写的锁）')
    probe = socket.socket()
    probe.settimeout(0.5)
    try:
        probe.connect(('127.0.0.1', port))
        line('ok', '单实例', f'端口 {port} 可连（探活正常）')
    except OSError:
        line('err' if alive else 'warn', '单实例',
             f'端口 {port} 连不上（{"锁 PID 活着但端口不通，可能被 PET_PORT 改过" if alive else "桌宠不在跑，Claude 下个事件会自动拉起"}）')
    finally:
        probe.close()


def tail(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = [l.rstrip() for l in f if l.strip()]
    except OSError:
        return []
    return [redact(l)[:TAIL_CHARS] for l in lines[-TAIL_LINES:]]


def check_logs(run_dir):
    logs = []
    for name in LOG_NAMES:
        path = os.path.join(run_dir, name)
        if not os.path.exists(path):
            continue
        age = int(time.time() - os.path.getmtime(path))
        size = os.path.getsize(path)
        logs.append((name, age, size))
    if not logs:
        line('ok', '日志', '没有错误日志（干净）')
        return
    detail = '、'.join(f'{n}（{a}s 前，{s}B）' for n, a, s in logs)
    level = 'warn' if any(n in ('pet-error.log', 'mod-launch.log') for n, _, _ in logs) else 'ok'
    line(level, '日志', f'{redact(run_dir)}/ 下有：{detail}')
    for name in ('pet-error.log', 'mod-launch.log'):
        rows = tail(os.path.join(run_dir, name))
        if rows:
            print(f'--- {name} 末尾 ---')
            for row in rows:
                print(f'  {row}')


def main():
    if len(sys.argv) < 4:
        sys.exit('用法：python doctor.py <运行目录> <插件根目录> <单实例端口>')
    run_dir, plugin_root, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    if not check_env(run_dir, plugin_root):
        print(f'结论：{ok_n} 项正常，{warn_n} 项警告，{err_n} 项错误')
        sys.exit(1)
    check_sessions(run_dir)
    check_venv(run_dir)
    check_lock(run_dir, port)
    check_logs(run_dir)
    print(f'结论：{ok_n} 项正常，{warn_n} 项警告，{err_n} 项错误')
    sys.exit(1 if err_n else 0)


if __name__ == '__main__':
    main()
