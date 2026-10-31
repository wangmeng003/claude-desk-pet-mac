// #12 权限客户端单测：入参映射 / 决策输出格式 / 失败路径全部收敛到无决策（spec §7）。
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRequest, decisionOutput, handle } from './permission_client.mjs';

const INPUT = {
  session_id: 'sess-1',
  prompt_id: 'prompt-1',
  cwd: '/Users/dev/demo',
  tool_name: 'Bash',
  tool_input: { command: 'rm -rf build', description: '清理构建产物' },
};

function bridgeMeta(over = {}) {
  return { v: 1, port: 49321, token: 'tok', pid: process.pid, ...over };
}

test('buildRequest 映射 hook 入参', () => {
  const req = buildRequest(INPUT, { readSettings: () => null });
  assert.equal(req.id, 'prompt-1');
  assert.equal(req.session, 'sess-1');
  assert.equal(req.tool, 'Bash');
  assert.equal(req.project, 'demo'); // cwd 的 basename
  assert.equal(req.summary, '清理构建产物'); // description 优先
  assert.equal(req.detail, 'rm -rf build');
  assert.equal(req.risk, 'low'); // 客户端保持薄，桥负责兜底
  assert.equal(req.v, 1);
  assert.ok(req.ts > 0);
});

test('buildRequest：无 description 用命令；无 prompt_id 用内容兜底 id', () => {
  const req = buildRequest({
    session_id: 's', tool_name: 'Bash', tool_input: { command: 'echo hi' },
  }, { readSettings: () => null });
  assert.equal(req.summary, 'echo hi');
  assert.equal(req.id, 's|Bash|echo hi');
});

test('buildRequest：截断与非法输入', () => {
  const long = 'x'.repeat(500);
  const req = buildRequest({
    session_id: 's', tool_name: 'Bash', tool_input: { command: long },
  }, { readSettings: () => null });
  assert.equal(req.summary.length, 200);
  assert.equal(req.detail.length, 500); // detail 上限 8192
  assert.equal(buildRequest(null), null);
  assert.equal(buildRequest({ tool_name: 'Bash' }), null); // 缺 session
  assert.equal(buildRequest({ session_id: 's', tool_input: {} }), null); // 缺摘要
});

test('buildRequest：Write/Edit 族用文件名兜底摘要', () => {
  const req = buildRequest({
    session_id: 's', tool_name: 'Write',
    tool_input: { file_path: '/Users/dev/demo/src/main.py', content: 'print(1)' },
  }, { readSettings: () => null });
  assert.equal(req.summary, '编辑 main.py');
  assert.equal(req.detail, '/Users/dev/demo/src/main.py'); // 完整路径进 detail（仅卡片内存）
  assert.equal(req.id, 's|Write|编辑 main.py');

  // Windows 反斜杠路径同样取到 basename
  const win = buildRequest({
    session_id: 's', tool_name: 'Edit',
    tool_input: { file_path: 'C:\\dev\\demo\\app.ts' },
  }, { readSettings: () => null });
  assert.equal(win.summary, '编辑 app.ts');

  // 既无 command 又无 file_path 的工具 → 不凑卡片，回退终端
  assert.equal(buildRequest({
    session_id: 's', tool_name: 'WebFetch', tool_input: { url: 'https://x' },
  }, { readSettings: () => null }), null);
});

test('buildRequest：隐私模式不带项目名', () => {
  const req = buildRequest(INPUT, { readSettings: () => '{"privacy": true}' });
  assert.equal(req.project, '');
});

test('decisionOutput：只有 allow/deny 是真决策', () => {
  assert.deepEqual(JSON.parse(decisionOutput({ decision: 'allow' })), {
    hookSpecificOutput: {
      hookEventName: 'PermissionRequest', decision: { behavior: 'allow' },
    },
  });
  const deny = JSON.parse(decisionOutput({ decision: 'deny', reason: 'user' }));
  assert.equal(deny.hookSpecificOutput.decision.behavior, 'deny');
  assert.ok(deny.hookSpecificOutput.decision.message.length > 0);
  assert.equal(decisionOutput({ decision: 'ask', reason: 'timeout' }), '{}');
  assert.equal(decisionOutput({ decision: 'busy' }), '{}');
  assert.equal(decisionOutput(null), '{}');
  assert.equal(decisionOutput({}), '{}');
});

test('handle：allow/deny 透传，ask/忙/超时一律无决策', async () => {
  const ok = (body) => ({ ok: true, json: async () => body });
  const deps = (resp) => ({
    readBridgeFile: () => JSON.stringify(bridgeMeta()),
    readSettings: () => null,
    fetch: async () => ok(resp),
  });
  assert.equal(await handle(INPUT, deps({ decision: 'allow' })),
    decisionOutput({ decision: 'allow' }));
  assert.equal(await handle(INPUT, deps({ decision: 'deny' })), decisionOutput({ decision: 'deny' }));
  assert.equal(await handle(INPUT, deps({ decision: 'ask', reason: 'busy' })), '{}');
  assert.equal(await handle(INPUT, deps({ decision: 'ask', reason: 'timeout' })), '{}');
});

test('handle：bridge.json 缺失/坏 JSON/pid 死 → 立即无决策（不发起 HTTP）', async () => {
  let called = 0;
  const deps = (raw) => ({
    readBridgeFile: () => raw,
    readSettings: () => null,
    fetch: async () => { called += 1; return { ok: true, json: async () => ({ decision: 'allow' }) }; },
  });
  assert.equal(await handle(INPUT, deps(null)), '{}');
  assert.equal(await handle(INPUT, deps('{oops')), '{}');
  assert.equal(await handle(INPUT, deps(JSON.stringify(bridgeMeta({ pid: 4194304 })))), '{}');
  assert.equal(await handle(INPUT, deps(JSON.stringify(bridgeMeta({ pid: -1 })))), '{}');
  assert.equal(called, 0);
});

test('handle：HTTP 失败/非 2xx/坏响应 → 无决策', async () => {
  const base = { readBridgeFile: () => JSON.stringify(bridgeMeta()), readSettings: () => null };
  assert.equal(await handle(INPUT, { ...base, fetch: async () => { throw new Error('ECONNREFUSED'); } }), '{}');
  assert.equal(await handle(INPUT, { ...base, fetch: async () => ({ ok: false, status: 401 }) }), '{}');
  assert.equal(await handle(INPUT, { ...base, fetch: async () => ({ ok: true, json: async () => { throw new Error('bad body'); } }) }), '{}');
});

test('handle：请求体带上 Bearer token 与 JSON 头（对拍捕获）', async () => {
  let captured = null;
  const deps = {
    readBridgeFile: () => JSON.stringify(bridgeMeta({ token: 'sec-ret' })),
    readSettings: () => null,
    fetch: async (url, init) => {
      captured = { url, init };
      return { ok: true, json: async () => ({ decision: 'ask' }) };
    },
  };
  await handle(INPUT, deps);
  assert.equal(captured.url, 'http://127.0.0.1:49321/v1/permission');
  assert.equal(captured.init.headers.Authorization, 'Bearer sec-ret');
  assert.equal(captured.init.headers['Content-Type'], 'application/json');
  const sent = JSON.parse(captured.init.body);
  assert.equal(sent.id, 'prompt-1');
  assert.ok(!JSON.stringify(sent).includes('sec-ret'));
});
