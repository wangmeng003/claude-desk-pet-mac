// accounting 记账逻辑的测试：会话/项目累计、花费增量。
import { test } from 'node:test'
import { strictEqual } from 'node:assert'
import type { EngineInterface, SessionUsage } from 'claude-code'
import type { SessionContext } from './context.ts'
import { account, ensureSessionRecord, readSession } from './accounting.ts'

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
