// accounting 记账逻辑的测试：会话/项目累计、花费增量。
import { test } from 'node:test'
import { strictEqual } from 'node:assert'
import type { EngineInterface, SessionUsage } from 'claude-code'
import type { SessionContext } from './context.ts'
import { account, ensureSessionRecord, projectKey, readSession } from './accounting.ts'

// 最小引擎桩：store 用内存 Map，usage 固定可设
function make$(usage: SessionUsage = { context: {}, rateLimits: [] }) {
  const store = new Map<string, unknown>()
  return {
    store: {
      get: async (k: string) => store.get(k),
      set: async (k: string, v: unknown) => { store.set(k, v) },
    },
    session: { usage: async () => usage },
    _store: store,
  } as unknown as EngineInterface & { _store: Map<string, unknown> }
}

const ctx = (sessionKey = 'session:s1', cwd = '/w/demo'): SessionContext => ({
  runDir: '/tmp/desk-pet', petFile: '', project: 'demo', cwd, sessionKey, toolErrors: 0, petCheckedAt: 0,
})

const U = (i: number, o: number, r: number, w: number) => ({
  input_tokens: i, output_tokens: o, cache_read_input_tokens: r, cache_creation_input_tokens: w,
})

test('ensureSessionRecord：首次建档并把项目会话数 +1，重载不重复计数', async () => {
  const $ = make$()
  $.store.set('project:/w/demo', { input: 10, output: 0, cacheRead: 0, cacheWrite: 0, costUsd: 1, sessions: 2 })
  await ensureSessionRecord(ctx(), $)
  await ensureSessionRecord(ctx(), $) // mod 重载：sessionKey 已存在
  const p = (await $.store.get('project:/w/demo')) as { sessions: number }
  strictEqual(p.sessions, 3)
  strictEqual((await readSession(ctx(), $)).totals.input, 0)
})

test('account：四类 token 累加进会话与项目累计', async () => {
  const $ = make$()
  await ensureSessionRecord(ctx(), $)
  await account(ctx(), $, U(100, 50, 400, 200))
  await account(ctx(), $, U(1, 2, 3, 4))
  const s = await readSession(ctx(), $)
  strictEqual(s.totals.input, 101)
  strictEqual(s.totals.output, 52)
  strictEqual(s.totals.cacheRead, 403)
  strictEqual(s.totals.cacheWrite, 204)
  const p = (await $.store.get('project:/w/demo')) as { input: number; cacheRead: number }
  strictEqual(p.input, 101)
  strictEqual(p.cacheRead, 403)
})

test('account：项目花费按会话花费增量累计，花费下降不倒扣', async () => {
  const $ = make$({ cost: { usd: 1.5 }, context: {}, rateLimits: [] })
  await ensureSessionRecord(ctx(), $)
  await account(ctx(), $, U(1, 1, 0, 0)) // lastCost 0 → 1.5，记 1.5
  const p1 = (await $.store.get('project:/w/demo')) as { costUsd: number }
  strictEqual(p1.costUsd, 1.5)

  // 会话花费回落（如部分轮次被修正）：增量按 0 记
  const $2 = make$({ cost: { usd: 1.2 }, context: {}, rateLimits: [] })
  await $2.store.set('session:s1', { totals: { input: 1, output: 1, cacheRead: 0, cacheWrite: 0 }, lastCost: 1.5 })
  await account(ctx(), $2, U(1, 1, 0, 0))
  const p2 = (await $2.store.get('project:/w/demo')) as { costUsd: number }
  strictEqual(p2.costUsd, 0)
})

test('account：usage 缺失时四类记 0、lastCost 仍刷新', async () => {
  const $ = make$({ cost: { usd: 2 }, context: {}, rateLimits: [] })
  await ensureSessionRecord(ctx(), $)
  await account(ctx(), $, U(5, 5, 5, 5))
  await account(ctx(), $, undefined)
  const s = await readSession(ctx(), $)
  strictEqual(s.totals.input, 5)
  strictEqual(s.lastCost, 2)
})

test('ensureSessionRecord：新项目也要建出项目记录（会话数从 1 开始）', async () => {
  const $ = make$()
  await ensureSessionRecord(ctx(), $)
  const p = (await $.store.get('project:/w/demo')) as { sessions: number; costUsd: number }
  strictEqual(p.sessions, 1)
  strictEqual(p.costUsd, 0)
})

test('ensureSessionRecord：老记录里没有 sessions 字段时不要变 NaN', async () => {
  const $ = make$()
  await $.store.set('project:/w/demo', { input: 1, output: 0, cacheRead: 0, cacheWrite: 0, costUsd: 2 })
  await ensureSessionRecord(ctx(), $)
  const p = (await $.store.get('project:/w/demo')) as { sessions: number }
  strictEqual(p.sessions, 1)
})

test('projectKey：Windows 路径大小写/分隔符不敏感，mac 路径保持大小写敏感', () => {
  strictEqual(projectKey('C:\\Repo'), projectKey('c:/repo'))
  strictEqual(projectKey('C:/Repo'), 'project:c:/repo')
  strictEqual(projectKey('D:\\Work\\Demo'), 'project:d:/work/demo')
  // mac/Linux 文件系统大小写敏感：不同路径就是不同项目
  if (projectKey('/w/Demo') === projectKey('/w/demo')) throw new Error('mac 路径不应被 lowercase 合并')
})

test('升级迁移：老版本的原样 cwd key 搬到归一化 key，不丢累计', async () => {
  const $ = make$()
  const oldRec = { input: 10, output: 5, cacheRead: 20, cacheWrite: 0, costUsd: 1.25, sessions: 2 }
  // 老版本按当时 cwd 原样存（反斜杠、大写盘符）；今天同一项目 cwd 字符串不变
  await $.store.set('project:C:\\repo', oldRec)
  await ensureSessionRecord(ctx('session:s9', 'C:\\repo'), $)
  const migrated = (await $.store.get('project:c:/repo')) as typeof oldRec
  strictEqual(migrated.input, 10)
  strictEqual(migrated.costUsd, 1.25)
  strictEqual(migrated.sessions, 3)  // 建档时 +1
})

test('升级迁移：新 key 已有记录时不被旧 key 覆盖（混用期各自累计，相加会重复）', async () => {
  const $ = make$()
  await $.store.set('project:C:\\repo', { input: 10, output: 0, cacheRead: 0, cacheWrite: 0, costUsd: 0, sessions: 1 })
  await $.store.set('project:c:/repo', { input: 3, output: 0, cacheRead: 0, cacheWrite: 0, costUsd: 0, sessions: 1 })
  await ensureSessionRecord(ctx('session:s9', 'C:\\repo'), $)
  const kept = (await $.store.get('project:c:/repo')) as { input: number; sessions: number }
  strictEqual(kept.input, 3)
  strictEqual(kept.sessions, 2)  // 只 +1，不叠旧记录
})

test('升级迁移：热重载升级（sessionKey 已存在）也要迁移老项目 key', async () => {
  const $ = make$()
  const oldRec = { input: 7, output: 0, cacheRead: 0, cacheWrite: 0, costUsd: 0.5, sessions: 1 }
  await $.store.set('project:C:\\repo', oldRec)
  // 会话早已建档（升级前），session.start 早退路径
  await $.store.set('session:s9', { totals: { input: 1, output: 0, cacheRead: 0, cacheWrite: 0 }, lastCost: 0 })
  await ensureSessionRecord(ctx('session:s9', 'C:\\repo'), $)
  const migrated = (await $.store.get('project:c:/repo')) as typeof oldRec
  strictEqual(migrated.input, 7)
  strictEqual(migrated.sessions, 1)  // 已建档会话不再 +1
})
