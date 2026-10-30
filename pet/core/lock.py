# core：单实例锁（#5）。只允许依赖 stdlib。
# 端口才是互斥量：bind 原子成败，谁绑到谁活。锁文件只记录 pid/port，
# 用来在冲突时给出明确提示（另一只桌宠 PID / 端口被谁占）与诊断。
import json
import os
import socket
import sys
import threading
import time

DEFAULT_PORT = 47321
LOCK_NAME = 'pet.lock'


def port_from_env(env=None) -> int:
    """PET_PORT 环境变量换端口；没设/不是 1..65535 用默认。"""
    raw = (os.environ if env is None else env).get('PET_PORT', '')
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def lock_path(run_dir) -> str:
    return os.path.join(run_dir, LOCK_NAME)


def valid_pid(pid) -> bool:
    return isinstance(pid, int) and not isinstance(pid, bool) and pid > 0


def pid_alive(pid) -> bool:
    if not valid_pid(pid):
        return False
    if sys.platform == 'win32':
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程在，只是不属于我们
    except OSError:
        return False
    return True


def read_lock(path):
    """读锁文件；缺失/坏 JSON/不是对象都返回 None（调用方按无锁处理）。"""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_lock(path, pid, port):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'pid': pid, 'port': port, 'ts': int(time.time())}, f)
    os.replace(tmp, path)


def remove_lock(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _accept_loop(server):
    while True:
        try:
            conn, _ = server.accept()
        except OSError:
            return  # 套接字被关（进程退出中）
        try:
            conn.close()
        except OSError:
            pass


def acquire(run_dir, port):
    """绑端口 + 写锁文件。返回 (kind, info)：

    - ('acquired', server_socket)：锁到手，socket 要一直持有（GC 会关掉它）；
      listen + 后台线程收连接，hooks 的探活（connect 成功 = 活着）才成立
      ——只 bind 不 listen 时 connect 恒被拒，探活会把活着的桌宠当成死的。
    - ('another-pet', {'pid': …})：锁文件里 PID 还活着，说明已有桌宠在跑。
    - ('port-taken', {'port': …})：端口被占但没有活的桌宠（其他程序占着，
      或另一只桌宠用了别的运行目录）。崩溃残留的锁文件顺手清掉。
    """
    path = lock_path(run_dir)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != 'win32':
        # 探活连接由服务端先关，TIME_WAIT 落在本端口；不设 REUSEADDR 的话
        # 桌宠退出后 ~30s 内重新 bind 恒失败（探活过的端口起不来）。
        # Windows 默认就允许 TIME_WAIT 期间重绑（且 REUSEADDR 语义不同），不动。
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('127.0.0.1', port))
    except OSError:
        server.close()
        data = read_lock(path)
        pid = data.get('pid') if data else None
        if valid_pid(pid) and pid_alive(pid):
            return 'another-pet', {'pid': pid}
        if data:
            remove_lock(path)
        return 'port-taken', {'port': port}
    server.listen(4)
    threading.Thread(target=_accept_loop, args=(server,), daemon=True).start()
    try:
        write_lock(path, os.getpid(), port)
    except OSError:
        pass  # 端口已经拿到手；锁文件写不进去只影响提示质量，不影响互斥
    return 'acquired', server
