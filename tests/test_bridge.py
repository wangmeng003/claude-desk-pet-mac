# #13 bridge 契约测试：鉴权/校验/忙时/超时/退出/bridge.json（specs/permission.md §5.2-5.4）。
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from bridge import server as bridge_server


def _post(srv, body, token=None, headers=None, path='/v1/permission'):
    tok = srv.token if token is None else token
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(
        f'http://127.0.0.1:{srv.port}{path}', data=data, method='POST',
        headers={'Authorization': f'Bearer {tok}',
                 'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def _get(srv, path='/v1/health', token=None):
    tok = srv.token if token is None else token
    req = urllib.request.Request(
        f'http://127.0.0.1:{srv.port}{path}',
        headers={'Authorization': f'Bearer {tok}'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def _req(rid='r1', **over):
    body = {'v': 1, 'id': rid, 'session': 's1', 'tool': 'Bash',
            'project': 'demo', 'summary': 'rm -rf build', 'detail': 'rm -rf build',
            'risk': 'low', 'ts': time.time()}
    body.update(over)
    return body


@pytest.fixture
def srv(tmp_path):
    s = bridge_server.BridgeServer(run_dir=str(tmp_path),
                                   on_request=lambda vm: None, timeout=600.0)
    s.start()
    yield s
    s.stop()


def _decide_later(srv, rid, decision, delay=0.05):
    def run():
        time.sleep(delay)
        srv.decide(rid, decision)
    threading.Thread(target=run, daemon=True).start()


# ---------- 鉴权与基础 ----------

def test_health_ok_with_token(srv):
    code, body = _get(srv)
    assert code == 200 and body['ok'] is True and body['v'] == 1
    assert body['pid'] == os.getpid()


def test_auth_required(srv):
    assert _get(srv, token='wrong')[0] == 401
    req = urllib.request.Request(f'http://127.0.0.1:{srv.port}/v1/health')
    try:
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError('should 401')
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_unknown_path_404(srv):
    assert _get(srv, path='/nope')[0] == 404


def test_browser_origin_rejected(srv):
    code, _ = _post(srv, _req(), headers={'Origin': 'http://evil.example'})
    assert code == 403


# ---------- /v1/permission 主流程 ----------

def test_allow_roundtrip_and_viewmodel(tmp_path):
    seen = []
    s = bridge_server.BridgeServer(run_dir=str(tmp_path), on_request=seen.append,
                                   timeout=600.0)
    s.start()
    try:
        _decide_later(s, 'r1', 'allow')
        code, body = _post(s, _req('r1'))
        assert code == 200 and body == {'decision': 'allow', 'reason': 'user'}
        vm = seen[0]
        assert (vm.id, vm.session, vm.tool, vm.summary) == ('r1', 's1', 'Bash', 'rm -rf build')
        assert vm.detail == 'rm -rf build'
        assert vm.risk == 'high'  # bridge 自己算的 rm -rf 兜住了客户端报的 low
    finally:
        s.stop()


def test_deny_roundtrip(srv):
    _decide_later(srv, 'r2', 'deny')
    code, body = _post(srv, _req('r2'))
    assert code == 200 and body == {'decision': 'deny', 'reason': 'user'}


def test_busy_returns_409_immediately(srv):
    result = {}

    def slow():
        result['first'] = _post(srv, _req('a1'))
    t = threading.Thread(target=slow, daemon=True)
    t.start()
    time.sleep(0.3)  # 第一个进入 pending
    code, body = _post(srv, _req('b2'))
    assert code == 409 and body['decision'] == 'ask' and body['reason'] == 'busy'
    srv.decide('a1', 'deny')
    t.join(10)
    assert result['first'][1]['decision'] == 'deny'


def test_duplicate_id_409_after_decision(srv):
    _decide_later(srv, 'd1', 'allow')
    assert _post(srv, _req('d1'))[0] == 200
    code, body = _post(srv, _req('d1'))
    assert code == 409


def test_bad_json_400(srv):
    assert _post(srv, b'{oops')[0] == 400
    assert _post(srv, b'[]')[0] == 400


@pytest.mark.parametrize('over', [
    {'v': 2}, {'id': ''}, {'session': ''}, {'tool': ''}, {'summary': ''},
    {'risk': 'extreme'}, {'risk': None}, {'ts': 'now'},
    {'summary': 'x' * 201},
])
def test_field_validation_400(srv, over):
    assert _post(srv, _req(**over))[0] == 400


def test_body_over_64kb_400(srv):
    big = _req(detail='x' * (70 * 1024))
    code, _ = _post(srv, big)
    assert code == 400


def test_timeout_returns_ask(tmp_path):
    s = bridge_server.BridgeServer(run_dir=str(tmp_path), on_request=lambda vm: None,
                                   timeout=0.2)
    s.start()
    try:
        t0 = time.monotonic()
        code, body = _post(s, _req('t1'))
        assert code == 200 and body['decision'] == 'ask' and body['reason'] == 'timeout'
        assert time.monotonic() - t0 < 5
    finally:
        s.stop()


def test_stop_fails_pending_as_ask_and_removes_bridge_json(srv):
    result = {}

    def pending():
        result['r'] = _post(srv, _req('p1'))
    t = threading.Thread(target=pending, daemon=True)
    t.start()
    time.sleep(0.3)
    srv.stop()
    t.join(10)
    assert result['r'][1] == {'decision': 'ask', 'reason': 'error'}


# ---------- bridge.json ----------

def test_bridge_json_content_and_cleanup(tmp_path):
    s = bridge_server.BridgeServer(run_dir=str(tmp_path), on_request=lambda vm: None,
                                   timeout=600.0)
    s.start()
    path = os.path.join(str(tmp_path), 'bridge.json')
    try:
        with open(path, encoding='utf-8') as f:
            meta = json.load(f)
        assert meta['v'] == 1 and meta['port'] == s.port and meta['pid'] == os.getpid()
        assert meta['token'] == s.token and meta['started_at'] > 0
        if sys.platform != 'win32':  # Windows 上 chmod 只影响只读位
            assert os.stat(path).st_mode & 0o777 == 0o600
    finally:
        s.stop()
    assert not os.path.exists(path)


def test_callback_exception_fail_open(srv):
    def boom(vm):
        raise RuntimeError('renderer 崩了')
    srv.on_request = boom
    code, body = _post(srv, _req('x1'))
    assert code == 500 and body['decision'] == 'ask' and body['reason'] == 'error'


def test_sessions_do_not_cross(srv):
    # s1 的请求 pending 中，s2 的请求忙时 409；s1 的决策只影响 s1
    result = {}

    def first():
        result['s1'] = _post(srv, _req('id1', session='s1'))
    t = threading.Thread(target=first, daemon=True)
    t.start()
    time.sleep(0.3)
    code, body = _post(srv, _req('id2', session='s2'))
    assert code == 409
    assert srv.decide('id2', 'allow') is False  # 不在 pending，决策不生效
    srv.decide('id1', 'allow')
    t.join(10)
    assert result['s1'][1]['decision'] == 'allow'
