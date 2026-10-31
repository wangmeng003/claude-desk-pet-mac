// 插件原生 hook 声明的契约测试（hooks/hooks.json 的 "hooks" 键）：
// PermissionRequest 客户端随插件自动注册（M2 接线），结构漂移在这里拦截。
// exec form（command+args）绕过 shell：Windows 默认 PowerShell 的引号/转义面不参与（ADR-0001 Windows 风险）。
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const decl = JSON.parse(readFileSync(join(HERE, 'hooks.json'), 'utf8'));

test('mods 入口不受影响（modules 键原样保留）', () => {
  assert.deepEqual(decl.modules, ['./register.ts']);
});

test('PermissionRequest hook：exec form + CLAUDE_PLUGIN_ROOT + 无 matcher（全工具）', () => {
  assert.ok(decl.hooks && Array.isArray(decl.hooks.PermissionRequest));
  assert.equal(decl.hooks.PermissionRequest.length, 1);
  const [entry] = decl.hooks.PermissionRequest;
  assert.equal(entry.matcher, undefined); // 省略 matcher → 所有工具都触发（ADR-0001 实测）
  assert.equal(entry.hooks.length, 1);
  const hook = entry.hooks[0];
  assert.equal(hook.type, 'command');
  assert.equal(hook.command, 'node'); // exec form：可执行文件直接放 command
  assert.deepEqual(hook.args, ['${CLAUDE_PLUGIN_ROOT}/hooks/permission_client.mjs']);
});

test('超时 620s ≥ 客户端 HTTP 610s ≥ 桥决策 600s（链条不被 claude 提前杀）', () => {
  const hook = decl.hooks.PermissionRequest[0].hooks[0];
  assert.equal(typeof hook.timeout, 'number');
  assert.ok(hook.timeout >= 620, `timeout ${hook.timeout} < 620`);
});

test('args 指向的客户端脚本真实存在', () => {
  const root = dirname(HERE); // CLAUDE_PLUGIN_ROOT = 插件根 = repo 根
  for (const a of decl.hooks.PermissionRequest[0].hooks[0].args) {
    assert.ok(a.startsWith('${CLAUDE_PLUGIN_ROOT}/'), `未使用插件根占位符: ${a}`);
    const local = a.replace('${CLAUDE_PLUGIN_ROOT}', root);
    assert.ok(statSync(local).isFile(), `${local} 不存在`);
  }
});
