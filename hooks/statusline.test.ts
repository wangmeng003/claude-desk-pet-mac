// statusline 纯格式化的测试：数量缩写、缓存命中率、statsText 骨架。
import { test } from 'node:test'
import { strictEqual } from 'node:assert'
import type { EngineInterface, SessionUsage } from 'claude-code'
import type { SessionContext } from './context.ts'
import { fmt, hitRate, statsText } from './statusline.ts'
import { EMPTY } from './accounting.ts'

test('fmt：千/百万缩写与个位原样', () => {
  strictEqual(fmt(0), '0')
  strictEqual(fmt(999), '999')
  strictEqual(fmt(1000), '1.0k')
  strictEqual(fmt(15300), '15.3k')
  strictEqual(fmt(1_000_000), '1.0M')
  strictEqual(fmt(2_340_000), '2.3M')
})

test('hitRate：零输入显示破折号，否则四舍五入取整', () => {
  strictEqual(hitRate(EMPTY), '—')
  strictEqual(hitRate({ input: 100, output: 0, cacheRead: 300, cacheWrite: 100 }), '60%')
  strictEqual(hitRate({ input: 3, output: 0, cacheRead: 1, cacheWrite: 0 }), '25%')
})

const ctx: SessionContext = {
  runDir: '', petFile: '', project: 'demo', cwd: '/w/demo', sessionKey: 'session:s1', toolErrors: 0,
}

function make$(usage: SessionUsage) {
  const store = new Map<string, unknown>()
  return {
    store: { get: async (k: string) => store.get(k), set: async (k: string, v: unknown) => { store.set(k, v) } },
    session: { usage: async () => usage },
  } as unknown as EngineInterface
}

test('statsText：无项目记录/无额度时的行骨架', async () => {
  const $ = make$({ cost: { usd: 0.5 }, context: { percent: 42 }, rateLimits: [] })
  const text = await statsText(ctx, $)
  const lines = text.split('\n')
  strictEqual(lines.length, 3)
  strictEqual(lines[0].includes('本会话：输入'), true)
  strictEqual(lines[0].includes('$0.50'), true)
  strictEqual(lines[1], '本项目：还没有记录')
  strictEqual(lines[2], '（项目累计从装上这个 mod 后开始算）')
})

test('statsText：有项目记录时带会话数与项目累计', async () => {
  const $ = make$({ context: {}, rateLimits: [{ kind: 'five_hour', percentUsed: 31 }] })
  await $.store.set('project:/w/demo', { input: 0, output: 0, cacheRead: 700, cacheWrite: 0, costUsd: 9.4, sessions: 6 })
  const lines = (await statsText(ctx, $)).split('\n')
  strictEqual(lines.length, 4)
  strictEqual(lines[1].includes('本项目（demo，6 个会话）'), true)
  strictEqual(lines[1].includes('$9.40'), true)
  strictEqual(lines[2], '额度 5 小时：已用 31%')
})
