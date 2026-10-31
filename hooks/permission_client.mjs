// #12 权限客户端：原生 PermissionRequest hook → bridge（specs/permission.md §5.1/§7，ADR-0001）。
// 约束：任何异常 → 无决策空 JSON（回退终端原生提示，不占其他 hook 的决策位）；
// 绝不自动 allow；不缓存 allow；被超时杀掉 = 回退（进程死即 fail-open）。
// 零依赖 .mjs：Claude Code 自带 node，双平台同一条命令。
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

const HOME = process.env.HOME || process.env.USERPROFILE || '';
const RUN_DIR = `${HOME}/.claude/desk-pet`;
const BRIDGE_JSON = `${RUN_DIR}/bridge.json`;
const SETTINGS_JSON = `${RUN_DIR}/settings.json`;
const HTTP_TIMEOUT_MS = 610_000; // bridge 等 600s，客户端留 10s 余量（spec §5.4）
const NO_DECISION = '{}';

function clip(s, n) {
  return s.length <= n ? s : s.slice(0, n);
}

export function buildRequest(input, deps = {}) {
  // hook 入参（ADR-0001 实测 schema）→ bridge 请求体。凑不齐关键字段 → null。
  if (!input || typeof input !== 'object') return null;
  const session = typeof input.session_id === 'string' ? input.session_id : '';
  const tool = typeof input.tool_name === 'string' ? input.tool_name : '';
  const ti = input.tool_input && typeof input.tool_input === 'object' ? input.tool_input : {};
  const command = typeof ti.command === 'string' ? ti.command : '';
  const filePath = typeof ti.file_path === 'string' ? ti.file_path : '';
  // Write/Edit 族没有 command：用文件名兜底摘要（分隔符兼容双平台路径）
  const fileBase = filePath ? filePath.split(/[\\/]/).pop() : '';
  const summary = clip(typeof ti.description === 'string' && ti.description
    ? ti.description : (command || (fileBase ? `编辑 ${fileBase}` : '')), 200);
  if (!session || !tool || !summary) return null;
  const detail = clip(command || filePath || JSON.stringify(ti), 8192);
  const id = (typeof input.prompt_id === 'string' && input.prompt_id)
    || `${session}|${tool}|${summary}`; // 无 prompt_id 时用内容兜底，模型重试可撞上桥的去重
  return {
    v: 1, id, session, tool,
    project: projectOf(input, deps),
    summary, detail,
    risk: 'low', // 桥取 max(上报, 本地规则)，客户端保持薄
    ts: Date.now() / 1000,
  };
}

function projectOf(input, deps) {
  // 隐私模式（pet 的 settings.json）开启时不带项目名，与状态文件同口径
  const readSettings = deps.readSettings || (() => null);
  try {
    const s = JSON.parse(readSettings() || '{}');
    if (s && s.privacy) return '';
  } catch { /* 读不到/坏 JSON 按非隐私处理 */ }
  const cwd = typeof input.cwd === 'string' ? input.cwd : '';
  return cwd ? clip(basename(cwd), 200) : '';
}

export function decisionOutput(resp) {
  // bridge 响应 → Claude Code 期望的输出（ADR-0001 实测格式）。
  // 只有 allow/deny 是真决策；ask/busy/timeout 一律 {}（回退终端原生提示，不占决策位）。
  if (!resp || typeof resp !== 'object') return NO_DECISION;
  if (resp.decision === 'allow') {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PermissionRequest',
        decision: { behavior: 'allow' },
      },
    });
  }
  if (resp.decision === 'deny') {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PermissionRequest',
        decision: { behavior: 'deny', message: '用户在桌宠审批卡片上拒绝了这个操作' },
      },
    });
  }
  return NO_DECISION;
}

export async function handle(input, deps = {}) {
  // 返回应打印到 stdout 的字符串。所有失败路径都收敛到 NO_DECISION。
  const req = buildRequest(input, deps);
  if (!req) return NO_DECISION;
  const meta = readBridge(deps.readBridgeFile);
  if (!meta) return NO_DECISION; // bridge.json 缺失/坏/pid 不在 → 立即回退（spec §5.2）
  const fetchImpl = deps.fetch || fetch;
  try {
    const r = await fetchImpl(`http://127.0.0.1:${meta.port}/v1/permission`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${meta.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(req),
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    });
    if (!r.ok) return NO_DECISION;
    return decisionOutput(await r.json());
  } catch (e) {
    // debug 日志只记错误类别，不落命令内容（spec §7）
    console.error(`desk-pet permission client: ${e && e.name ? e.name : 'error'}`);
    return NO_DECISION;
  }
}

function readBridge(readBridgeFile) {
  // bridge.json：v=1、token、port、pid 活着才可信（spec §5.2）
  const raw = readBridgeFile || (() => {
    try { return readFileSync(BRIDGE_JSON, 'utf8'); } catch { return null; }
  });
  let meta = null;
  try { meta = JSON.parse(raw() || 'null'); } catch { return null; }
  if (!meta || meta.v !== 1 || !meta.token || !Number.isInteger(meta.port)) return null;
  if (!Number.isInteger(meta.pid) || meta.pid <= 0) return null;
  try { process.kill(meta.pid, 0); } catch { return null; } // 查不到/查不动都当不在
  return meta;
}

// ---------- CLI ----------
async function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { buf += c; });
    process.stdin.on('end', () => resolve(buf));
    process.stdin.on('error', reject);
  });
}

export async function main() {
  let input = null;
  try { input = JSON.parse(await readStdin()); } catch { /* 坏 JSON/空输入 → 无决策 */ }
  process.stdout.write(await handle(input));
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  await main();
}
