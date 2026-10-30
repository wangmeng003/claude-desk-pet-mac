# doctor.py 的诊断输出测试（#7）：跑真脚本（子进程），对临时运行目录各断言关键行。
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / 'pet' / 'doctor.py'
PORT = '47790'  # 测试专用端口，避开真实桌宠


def run_doctor(run_dir, port=PORT):
    return subprocess.run(
        [sys.executable, str(DOCTOR), str(run_dir), str(REPO), port],
        capture_output=True, text=True, timeout=90)


def test_healthy_dir_reports_env_sessions_logs(tmp_path):
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    (sessions / 's1.json').write_text(json.dumps(
        {'v': 1, 'session': 's1', 'state': 'thinking', 'text': 'x',
         'project': 'demo', 'ts': time.time()}), encoding='utf-8')
    (tmp_path / 'pet-error.log').write_text(
        f'第一行\n第二行\n旧的一行\n'
        f'{time.strftime("%Y-%m-%d %H:%M:%S")} 单实例锁：已经有一只桌宠在跑啦（PID 1）\n',
        encoding='utf-8')
    r = run_doctor(tmp_path)
    assert '[ok] 平台：' in r.stdout
    assert '[ok] 插件版本：' in r.stdout          # 读了仓库里真实的 plugin.json
    assert '[ok] 运行目录：' in r.stdout
    assert 's1（' in r.stdout and 'state=thinking' in r.stdout
    assert '[warn] 日志：' in r.stdout            # 有 pet-error.log
    assert '已经有一只桌宠在跑啦' in r.stdout      # 末尾 tail 带出最后一行
    assert '第一行' not in r.stdout and '第二行' not in r.stdout  # 只取末尾 2 行
    assert '旧的一行' in r.stdout
    assert '结论：' in r.stdout


def test_missing_everything_is_warn_not_crash(tmp_path):
    r = run_doctor(tmp_path)  # sessions 不存在、没有锁、没有日志
    assert '不存在或读不了' in r.stdout
    assert '[warn] 单实例' in r.stdout            # 没有锁文件 → 桌宠没在跑
    assert '[ok] 日志：没有错误日志' in r.stdout


def test_corrupt_state_file_marked(tmp_path):
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    (sessions / 'bad.json').write_text('{not json', encoding='utf-8')
    r = run_doctor(tmp_path)
    assert 'state=坏文件' in r.stdout


def test_lock_with_dead_pid_and_dead_port(tmp_path):
    p = subprocess.Popen([sys.executable, '-c', ''])
    p.wait()
    (tmp_path / 'pet.lock').write_text(
        json.dumps({'pid': p.pid, 'port': int(PORT), 'ts': time.time()}), encoding='utf-8')
    r = run_doctor(tmp_path)
    assert f'PID {p.pid}（已退出' in r.stdout
    # 锁 PID 已死 + 端口连不上 → 提示自动拉起，不是 err
    assert 'Claude 下个事件会自动拉起' in r.stdout
    assert '[err] 单实例' not in r.stdout


@pytest.mark.skipif(sys.platform == 'win32', reason='chmod 只读目录在 Windows 上不生效')
def test_unwritable_run_dir_is_err_and_short_circuits(tmp_path):
    ro = tmp_path / 'ro'
    ro.mkdir()
    ro.chmod(0o555)
    r = run_doctor(ro / 'desk-pet')
    assert r.returncode == 1
    assert '[err] 运行目录：' in r.stdout
    assert '结论：' in r.stdout
    assert '状态目录' not in r.stdout            # 目录不可写时不再往下查
    ro.chmod(0o755)  # 收尾，方便 tmp_path 清理


def test_ansi_codepage_stdout_does_not_crash(tmp_path):
    # 回归（Windows CI 实锤）：默认 ANSI 代码页编不了中文，doctor 死在第一行 print。
    # 用 PYTHONIOENCODING=cp1252 模拟，doctor 应自我 reconfigure 成 UTF-8 照常输出。
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    (sessions / 's1.json').write_text('{"state": "idle"}', encoding='utf-8')
    env = dict(os.environ, PYTHONIOENCODING='cp1252')
    r = subprocess.run(
        [sys.executable, str(DOCTOR), str(tmp_path), str(REPO), PORT],
        capture_output=True, text=True, timeout=90, env=env)
    assert '[ok] 平台：' in r.stdout
    assert '结论：' in r.stdout


def test_home_paths_are_redacted(tmp_path, monkeypatch):
    fake_home = tmp_path / 'home'
    fake_home.mkdir()
    monkeypatch.setenv('HOME', str(fake_home))  # doctor 的 redact 用 expanduser('~')
    sessions = fake_home / '.claude' / 'desk-pet' / 'sessions'
    sessions.mkdir(parents=True)
    (sessions / 's9.json').write_text('{"state": "idle"}', encoding='utf-8')
    env = dict(os.environ, HOME=str(fake_home))
    r = subprocess.run(
        [sys.executable, str(DOCTOR), str(sessions.parent), str(REPO), PORT],
        capture_output=True, text=True, timeout=90, env=env)
    assert str(fake_home) not in r.stdout
    assert '~/.claude/desk-pet' in r.stdout
