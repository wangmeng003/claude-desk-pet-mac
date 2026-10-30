# core.lock 单元测试（#5）：端口互斥、锁文件读写、PID 判活、探活可用。
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from core import lock


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def dead_pid():
    p = subprocess.Popen([sys.executable, '-c', ''])
    p.wait()
    return p.pid


# ---------- 端口解析 ----------

def test_port_from_env_default():
    assert lock.port_from_env({}) == lock.DEFAULT_PORT
    assert lock.port_from_env({'PET_PORT': ''}) == lock.DEFAULT_PORT


def test_port_from_env_valid():
    assert lock.port_from_env({'PET_PORT': '47400'}) == 47400


def test_port_from_env_invalid():
    for bad in ('abc', '0', '-1', '70000', '1.5'):
        assert lock.port_from_env({'PET_PORT': bad}) == lock.DEFAULT_PORT, bad


# ---------- 锁文件 ----------

def test_lock_roundtrip(tmp_path):
    path = lock.lock_path(str(tmp_path))
    lock.write_lock(path, 1234, 47321)
    data = lock.read_lock(path)
    assert data['pid'] == 1234
    assert data['port'] == 47321
    assert data['ts'] <= time.time()


def test_read_lock_tolerates_missing_and_garbage(tmp_path):
    path = Path(lock.lock_path(str(tmp_path)))
    assert lock.read_lock(path) is None  # 缺失
    path.write_text('not json', encoding='utf-8')
    assert lock.read_lock(path) is None  # 坏 JSON
    path.write_text('[1, 2]', encoding='utf-8')
    assert lock.read_lock(path) is None  # 不是对象


# ---------- PID 判活 ----------

def test_pid_alive_self_and_invalid():
    assert lock.pid_alive(os.getpid()) is True
    assert lock.pid_alive(0) is False
    assert lock.pid_alive(-5) is False
    assert lock.pid_alive(None) is False
    assert lock.pid_alive(True) is False  # bool 是 int 子类，单独挡掉


def test_pid_alive_dead_process():
    assert lock.pid_alive(dead_pid()) is False


# ---------- acquire：端口互斥的三种结果 ----------

def test_acquire_free_port_writes_lock(tmp_path):
    port = free_port()
    kind, info = lock.acquire(str(tmp_path), port)
    assert kind == 'acquired'
    data = lock.read_lock(lock.lock_path(str(tmp_path)))
    assert data['pid'] == os.getpid()
    assert data['port'] == port
    info.close()


def test_acquire_probe_connect_succeeds(tmp_path):
    # 回归（#4 遗留 bug）：只 bind 不 listen 时 connect 恒被拒，
    # hooks 探活会把活着的桌宠当死的，进入 10s 拉起循环
    port = free_port()
    kind, info = lock.acquire(str(tmp_path), port)
    assert kind == 'acquired'
    for _ in range(6):  # 多次连接（超过 listen 积压）都要成功：accept 线程在收
        c = socket.create_connection(('127.0.0.1', port), timeout=1)
        c.close()
    info.close()


def test_acquire_second_instance_reports_another_pet(tmp_path):
    port = free_port()
    kind, _ = lock.acquire(str(tmp_path), port)
    assert kind == 'acquired'
    kind2, info2 = lock.acquire(str(tmp_path), port)  # 锁文件 PID = 本测试进程，活着
    assert kind2 == 'another-pet'
    assert info2['pid'] == os.getpid()


def test_acquire_stale_lock_cleaned_as_port_taken(tmp_path):
    # 端口被占但锁文件 PID 已死（崩溃残留）：识别为端口被占，顺手清掉残留锁
    port = free_port()
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(('127.0.0.1', port))
    holder.listen(1)
    lock.write_lock(lock.lock_path(str(tmp_path)), dead_pid(), port)
    kind, info = lock.acquire(str(tmp_path), port)
    assert kind == 'port-taken'
    assert info['port'] == port
    assert lock.read_lock(lock.lock_path(str(tmp_path))) is None  # 残留锁被清
    holder.close()


def test_reacquire_immediately_after_exit(tmp_path):
    # 探活连接由服务端先关 → TIME_WAIT 落在桌宠端口；桌宠退出后要能立刻重绑
    # （SO_REUSEADDR），否则被探活过的端口 ~30s 内起不来第二只
    port = free_port()
    kind, server = lock.acquire(str(tmp_path), port)
    assert kind == 'acquired'
    c = socket.create_connection(('127.0.0.1', port), timeout=1)
    time.sleep(0.2)  # 让 accept 线程先收到并先关，TIME_WAIT 确定落在本端口
    c.close()
    server.close()
    kind2, server2 = lock.acquire(str(tmp_path), port)
    assert kind2 == 'acquired', 'TIME_WAIT 期间应可重新绑定'
    server2.close()


def test_acquire_port_taken_without_lock(tmp_path):
    # 端口被别的程序占了（无锁文件）：明确报端口，不误报成另一只桌宠
    port = free_port()
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(('127.0.0.1', port))
    holder.listen(1)
    kind, info = lock.acquire(str(tmp_path), port)
    assert kind == 'port-taken'
    assert info['port'] == port
    holder.close()


def test_acquire_garbage_pid_in_lock_treated_as_no_lock(tmp_path):
    port = free_port()
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(('127.0.0.1', port))
    holder.listen(1)
    Path(lock.lock_path(str(tmp_path))).write_text(
        json.dumps({'pid': 'not-a-number', 'port': port}), encoding='utf-8')
    kind, _ = lock.acquire(str(tmp_path), port)
    assert kind == 'port-taken'
    holder.close()
