// accounting：本会话/本项目的 token 与花费记账。
// 输入 DTO 是引擎的 Usage，输出落在 $.store（session:*/project:* 两个键）。
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'

// 累计的 token 用量（四类分开记，命中率 = 缓存读取 / 全部输入）
export type Totals = {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
}

// 引擎 turn.complete 给的用量
export type Usage = {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

// 本会话的记账：totals 是累计用量，lastCost 是上次记账时的会话花费（美元），用来算项目累计的增量
export type SessionRecord = { totals: Totals; lastCost: number }
export type ProjectTotals = Totals & { costUsd: number; sessions: number }

export const EMPTY: Totals = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }

const projectKey = (cwd: string) => `project:${cwd}`

export async function readSession(ctx: SessionContext, $: EngineInterface): Promise<SessionRecord> {
  const rec = (await $.store.get(ctx.sessionKey)) as SessionRecord | undefined
  // 拷贝一份：EMPTY 是模块级共享对象，直接返回引用的话谁改了它全局都被改
  return rec ?? { totals: { ...EMPTY }, lastCost: 0 }
}

// 新会话在项目累计里记一次（sessionKey 已存在说明是重载 mod，不重复计数）
export async function ensureSessionRecord(ctx: SessionContext, $: EngineInterface) {
  if ((await $.store.get(ctx.sessionKey)) !== undefined) return
  // 存副本：EMPTY 是模块级共享对象，直接存引用的话谁改了它全局都被改
  await $.store.set(ctx.sessionKey, { totals: { ...EMPTY }, lastCost: 0 })
  // 项目记录一定要建出来：新项目之前只在这里加 1，
  // 记录建不出来的话这一轮没跑成 account，项目会话数就永远少算一个。
  const key = projectKey(ctx.cwd)
  const p = (await $.store.get(key)) as ProjectTotals | undefined
  await $.store.set(key, {
    ...EMPTY,
    ...p,
    costUsd: p?.costUsd ?? 0,
    sessions: (p?.sessions ?? 0) + 1,
  })
}

// 把本轮用量记进会话累计和项目累计（项目累计跨会话保存）
export async function account(ctx: SessionContext, $: EngineInterface, u: Usage | undefined) {
  const { totals: t, lastCost } = await readSession(ctx, $)
  const add: Totals = u
    ? { input: u.input_tokens, output: u.output_tokens, cacheRead: u.cache_read_input_tokens, cacheWrite: u.cache_creation_input_tokens }
    : EMPTY
  const usage = await $.session.usage()
  const cost = usage.cost?.usd ?? 0
  const record: SessionRecord = {
    totals: {
      input: t.input + add.input,
      output: t.output + add.output,
      cacheRead: t.cacheRead + add.cacheRead,
      cacheWrite: t.cacheWrite + add.cacheWrite,
    },
    lastCost: cost,
  }
  await $.store.set(ctx.sessionKey, record)

  const p = ((await $.store.get(projectKey(ctx.cwd))) as ProjectTotals | undefined)
    ?? { ...EMPTY, costUsd: 0, sessions: 0 }
  await $.store.set(projectKey(ctx.cwd), {
    input: p.input + add.input,
    output: p.output + add.output,
    cacheRead: p.cacheRead + add.cacheRead,
    cacheWrite: p.cacheWrite + add.cacheWrite,
    costUsd: p.costUsd + Math.max(0, cost - lastCost),
    sessions: p.sessions,
  })
}
