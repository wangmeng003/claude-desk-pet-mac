# #13 权限审批桥 HTTP server（specs/permission.md §5.2/§5.3）。
# 只绑 127.0.0.1、随机端口、per-run token；renderer 不 import 这里，只经 on_request 收 VM。
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bridge import permission as bridge_permission
from bridge import risk as bridge_risk
from core.models import PermissionRequestViewModel

MAX_BODY = 64 * 1024
RISK_ORDER = {'low': 0, 'medium': 1, 'high': 2}
BRIDGE_JSON = 'bridge.json'


def parse_request(body: object) -> PermissionRequestViewModel | None:
    """按 §5.3 校验请求体；不合法 → None（回 400）。risk 取 max(客户端上报, 本地规则)。"""
    try:
        return _parse(body)
    except ValueError:
        return None


def _parse(body: object) -> PermissionRequestViewModel:
    if not isinstance(body, dict):
        raise ValueError('not an object')
    v = body.get('v')
    if isinstance(v, bool) or v != 1:
        raise ValueError('v')
    ts = body.get('ts')
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        raise ValueError('ts')
    rid = _need(body, 'id', 128)
    session = _need(body, 'session', 128)
    tool = _need(body, 'tool', 64)
    summary = _need(body, 'summary', 200)
    detail = _opt(body, 'detail', 8192)
    project = _opt(body, 'project', 200)
    reported = body.get('risk')
    if reported not in RISK_ORDER:
        raise ValueError('risk')
    computed = bridge_risk.assess(tool, summary, detail)
    risk = max(reported, computed, key=lambda r: RISK_ORDER[r])
    return PermissionRequestViewModel(
        id=rid, session=session, tool=tool, project=project,
        summary=summary, detail=detail, risk=risk, ts=float(ts))


def _need(body: dict, key: str, max_len: int) -> str:
    v = body.get(key)
    if not isinstance(v, str) or not v or len(v) > max_len:
        raise ValueError(key)
    return v


def _opt(body: dict, key: str, max_len: int) -> str:
    if key not in body:
        return ''
    return _need(body, key, max_len)


class _Server(ThreadingHTTPServer):
    daemon_threads = True   # 残留的等待线程不拖住进程退出
    block_on_close = False  # fail_all 已把 pending 转走，join 不必等它们

    def __init__(self, bridge: BridgeServer) -> None:
        super().__init__(('127.0.0.1', 0), _Handler)
        self.bridge = bridge


class _Handler(BaseHTTPRequestHandler):
    # 桥实例挂在 self.server.bridge 上（_Server 构造时注入）

    @property
    def _bridge(self) -> BridgeServer:
        s = self.server
        assert isinstance(s, _Server)
        return s.bridge

    def log_message(self, fmt, *args):  # 不写任何日志（token/命令都不落盘）
        pass

    # ---------- 基础防线 ----------
    def _origin_ok(self) -> bool:
        # CSRF：网页发起的 localhost 请求必带 Origin；本工具的客户端从不带
        return not self.headers.get('Origin')

    def _authed(self) -> bool:
        got = self.headers.get('Authorization') or ''
        want = f'Bearer {self._bridge.token}'
        return hmac.compare_digest(got.encode(), want.encode())

    def _reply(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _reject(self, code: int, reason: str) -> None:
        self.close_connection = True  # 不读 body，直接断
        self._reply(code, {'decision': 'ask', 'reason': reason})

    # ---------- 路由 ----------
    def do_GET(self):
        if self.path != '/v1/health':
            self._reject(404, 'error')
            return
        if not self._origin_ok():
            self._reject(403, 'error')
        elif not self._authed():
            self._reply(401, {'decision': 'ask', 'reason': 'error'})
        else:
            self._reply(200, {'ok': True, 'v': 1, 'pid': os.getpid()})

    def do_POST(self):
        if self.path != '/v1/permission':
            self._reject(404, 'error')
            return
        if not self._origin_ok():
            self._reject(403, 'error')
            return
        if not self._authed():
            self._reply(401, {'decision': 'ask', 'reason': 'error'})
            return
        try:
            length = int(self.headers.get('Content-Length') or '')
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._reject(400, 'error')
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self._reject(400, 'error')
            return
        vm = parse_request(body)
        if vm is None:
            self._reject(400, 'error')
            return
        if not self._bridge.gate.begin(vm.id):
            self._reply(409, {'decision': 'ask', 'reason': 'busy'})  # 忙/重复 id
            return
        try:
            self._bridge.on_request(vm)
        except Exception:
            self._bridge.gate.decide(vm.id, 'ask', 'error')
            self._reply(500, {'decision': 'ask', 'reason': 'error'})
            return
        decision, reason = self._bridge.gate.wait(vm.id)
        settled = self._bridge.on_settled
        if settled is not None:
            try:
                settled(vm.id, decision, reason)  # 让宠物在超时/退出时关掉卡片
            except Exception:
                pass
        self._reply(200, {'decision': decision, 'reason': reason})


class BridgeServer:
    """pet 进程内起桥：start() 写 bridge.json，stop() 删之并把 pending 转 ask。"""

    def __init__(self, run_dir: str,
                 on_request: Callable[[PermissionRequestViewModel], object],
                 timeout: float = 600.0,
                 on_settled: Callable[[str, str, str], object] | None = None) -> None:
        self.gate = bridge_permission.PermissionGate(timeout=timeout)
        self.token = secrets.token_urlsafe(32)
        self.on_request = on_request  # renderer 入口：收 PermissionRequestViewModel
        self.on_settled = on_settled  # wait 结束（含超时/fail_all）后的通知，异常吞掉
        self._server = _Server(self)
        self.port = self._server.server_address[1]
        self._path = os.path.join(run_dir, BRIDGE_JSON)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        meta = {'v': 1, 'port': self.port, 'token': self.token,
                'pid': os.getpid(), 'started_at': time.time()}
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(meta, f)
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True, name='pet-bridge')
        self._thread.start()

    def decide(self, rid: str, decision: str, reason: str = 'user') -> bool:
        return self.gate.decide(rid, decision, reason)

    def stop(self) -> None:
        self.gate.fail_all('error')
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        try:
            os.remove(self._path)
        except OSError:
            pass
