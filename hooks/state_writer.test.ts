// state_writer：写出的状态文件内容（跟状态协议 v1 §2 的 schema 对齐）。
import { test } from 'node:test'
import { strictEqual, ok, deepStrictEqual } from 'node:assert'
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import { pet } from './state_writer.ts'

const ctx: SessionContext = {
  runDir: '/run', petFile: '/run/sessions/s1.json',
  project: 'demo', cwd: '/w/demo', sessionKey: 'session:s1', toolErrors: 0, petCheckedAt: 0,
}

function make$(now: number, opts: { privacy?: string } = {}) {
  const written: Record<string, string> = {}
  const runs: string[][] = []
  const $ = {
    clock: { now: async () => now },
    fs: { write: async (p: string, c: string) => { written[p] = c } },
    env: { get: async (_k: string) => undefined },
    process: {
      run: async (argv: string[]) => {
        runs.push(argv)
        return { exitCode: 0, stdout: opts.privacy ?? '0', stderr: '' }
      },
    },
  } as unknown as EngineInterface
  return { $, written, runs }
}

test('pet：v1 schema 必填字段（v/session/agent/state/text/project/ts）', async () => {
  const { $, written } = make$(1793375735466)
  await pet(ctx, $, 'waiting', '我来啦～', { attention: false, sound: 'done' })
  const data = JSON.parse(written['/run/sessions/s1.json'])
  strictEqual(data.v, 1)
  strictEqual(data.session, 's1')        // sessionKey 去掉前缀
  strictEqual(data.agent, 'claude-code')
  strictEqual(data.state, 'waiting')
  strictEqual(data.text, '我来啦～')
  strictEqual(data.project, 'demo')
  strictEqual(data.sound, 'done')
  strictEqual(data.attention, false)
  // 字段集合不多不少（协议 §2；可选键给了才写）
  deepStrictEqual(Object.keys(data).sort(),
    ['agent', 'attention', 'project', 'session', 'sound', 'state', 'text', 'ts', 'v'])
})

test('pet：可选键（sound/attention）没给就不写', async () => {
  const { $, written } = make$(1793375735466)
  await pet(ctx, $, 'tool', '在改 x.ts')
  const data = JSON.parse(written['/run/sessions/s1.json'])
  strictEqual('sound' in data, false)
  strictEqual('attention' in data, false)
})

test('pet：ts 用 Unix 秒（协议 §2），不是毫秒', async () => {
  const { $, written } = make$(1793375735466)
  await pet(ctx, $, 'waiting', 'x')
  const data = JSON.parse(written['/run/sessions/s1.json'])
  // Unix 秒约 1.79e9；毫秒是 1.79e12，差 1000 倍。
  // 写成毫秒的话，以后按 ts 算 TTL 会把它当成「未来时间戳」直接丢掉。
  ok(data.ts > 1e9 && data.ts < 1e10, `ts 不是 Unix 秒：${data.ts}`)
  strictEqual(Math.round(data.ts * 1000), 1793375735466)
})

test('pet：时钟本来就给秒时不要再除一次', async () => {
  const { $, written } = make$(1793375735)
  await pet(ctx, $, 'waiting', 'x')
  const data = JSON.parse(written['/run/sessions/s1.json'])
  strictEqual(data.ts, 1793375735)
})

test('pet：写文件失败不能把异常抛出去（不能影响 Claude 干活）', async () => {
  const $ = {
    clock: { now: async () => 1 },
    fs: { write: async () => { throw new Error('disk full') } },
    env: { get: async (_k: string) => undefined },
    process: { run: async () => ({ exitCode: 0, stdout: '0', stderr: '' }) },
  } as unknown as EngineInterface
  await pet(ctx, $, 'waiting', 'x')  // 不能抛
})

// ---------- 隐私模式（#8）----------
// 共享的 ctx 会被前面的测试写进 privacyCheckedAt，隐私用例各自拿干净副本
const privacyCtx = () => ({ ...ctx, privacyCheckedAt: 0, privacy: undefined })

test('pet：隐私模式下 tool/reading 换通用文案，project 置空', async () => {
  const { $, written } = make$(1793375735466, { privacy: '1' })
  await pet(privacyCtx(), $, 'tool', '在改 pet_mac.py')
  const data = JSON.parse(written['/run/sessions/s1.json'])
  strictEqual(data.text, '在干活…')
  strictEqual(data.project, '')
})

test('pet：隐私模式下固定话术状态（waiting 等）文案原样保留', async () => {
  const { $, written } = make$(1793375735466, { privacy: '1' })
  await pet(privacyCtx(), $, 'waiting', '我来啦～')
  const data = JSON.parse(written['/run/sessions/s1.json'])
  strictEqual(data.text, '我来啦～')   // 固定话术本来就不带名字
  strictEqual(data.project, '')
})

test('pet：隐私开关 60s 缓存——同一分钟内的写入不再起 python 重读', async () => {
  // 探活（ensurePetAlive）也走 process.run：先把 petCheckedAt 抬高，桩里就只剩读开关的 run
  const c = { ...ctx, petCheckedAt: 1793375735_000, privacyCheckedAt: 0 }
  const first = make$(1793375735_000)
  await pet(c, first.$, 'tool', 'x')
  await pet(c, first.$, 'tool', 'y')
  strictEqual(first.runs.length, 1)  // 第一次写入读了一次开关，60s 内的第二次直接用缓存

  const later = make$(1793375735_000 + 61_000)
  await pet(c, later.$, 'tool', 'z')
  strictEqual(later.runs.length, 1)  // 过了 60s 才重读
})

test('pet：设置读不出来（python 不在）按隐私关处理，状态照写', async () => {
  const written: Record<string, string> = {}
  const $ = {
    clock: { now: async () => 1793375735 },
    fs: { write: async (p: string, c: string) => { written[p] = c } },
    env: { get: async (_k: string) => undefined },
    process: { run: async () => { throw new Error('no python') } },
  } as unknown as EngineInterface
  await pet(privacyCtx(), $, 'tool', '在改 x.ts')
  const data = JSON.parse(written['/run/sessions/s1.json'])
  strictEqual(data.text, '在改 x.ts')  // 没读开关就当关闭，照常写
  strictEqual(data.project, 'demo')
})
