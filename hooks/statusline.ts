// statusline：把用量数据格式化成状态栏一行 / token-stats 命令的多行文本。纯读不写。
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import { readSession, type ProjectTotals, type Totals } from './accounting.ts'

export const fmt = (n: number) =>
  n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : `${n}`

export const hitRate = (t: Totals) => {
  const all = t.input + t.cacheRead + t.cacheWrite
  return all === 0 ? '—' : `${Math.round((t.cacheRead / all) * 100)}%`
}

export async function refreshStatus(ctx: SessionContext, $: EngineInterface) {
  const t = (await readSession(ctx, $)).totals
  const usage = await $.session.usage()
  const parts = [
    `📊 本会话 输入 ${fmt(t.input + t.cacheRead + t.cacheWrite)}`,
    `输出 ${fmt(t.output)}`,
    `缓存命中 ${hitRate(t)}`,
  ]
  if (usage.cost) parts.push(`$${usage.cost.usd.toFixed(2)}`)
  if (usage.context?.percent !== undefined) parts.push(`上下文 ${usage.context.percent}%`)
  const fiveHour = (usage.rateLimits ?? []).find(r => r.kind === 'five_hour')
  if (fiveHour) parts.push(`5h额度 ${fiveHour.percentUsed}%`)
  await $.ui.status(parts.join(' · '))
}

export async function statsText(ctx: SessionContext, $: EngineInterface) {
  const t = (await readSession(ctx, $)).totals
  const p = (await $.store.get(`project:${ctx.cwd}`)) as ProjectTotals | undefined
  const usage = await $.session.usage()
  const line = (name: string, x: Totals) =>
    `${name}：输入 ${fmt(x.input + x.cacheRead + x.cacheWrite)}（缓存读取 ${fmt(x.cacheRead)}、缓存写入 ${fmt(x.cacheWrite)}、未缓存 ${fmt(x.input)}） · 输出 ${fmt(x.output)} · 缓存命中 ${hitRate(x)}`
  const rows = [
    line('本会话', t) + (usage.cost ? ` · $${usage.cost.usd.toFixed(2)}` : ''),
    p ? line(`本项目（${ctx.project}，${p.sessions} 个会话）`, p) + ` · $${p.costUsd.toFixed(2)}` : '本项目：还没有记录',
    ...(usage.rateLimits ?? []).map(r =>
      `额度 ${r.kind === 'five_hour' ? '5 小时' : r.kind === 'seven_day' ? '7 天' : r.kind}：已用 ${r.percentUsed}%` +
      (r.resetsAt ? `，${new Date(r.resetsAt).toLocaleString('zh-CN', { hour12: false })} 重置` : ''),
    ),
    '（项目累计从装上这个 mod 后开始算）',
  ]
  return rows.join('\n')
}
