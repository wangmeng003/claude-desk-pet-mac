// launcher 健康检查与自动重启的测试（#4）：探活解释、节流、被杀后拉起。
import { test } from 'node:test'
import { strictEqual } from 'node:assert'
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import { ensurePetAlive, launchPet, petAlive } from './launcher.ts'

// 最小引擎桩：env 无 SystemRoot（走 macOS 分支），process.run 的结果可编排
function make$(probeExit: number | 'throw') {
  return makeEnv$({}, probeExit)
}

// 可指定环境变量的引擎桩（PET_PORT / SystemRoot，#5）
function makeEnv$(env: Record<string, string>, probeExit: number | 'throw') {
  const runs: string[][] = []
  return {
    $: {
      env: { get: async (k: string) => env[k] },
      process: {
        run: async (argv: string[]) => {
          runs.push(argv)
          if (probeExit === 'throw') throw new Error('probe timeout')
          return { exitCode: probeExit, stdout: '', stderr: '' }
        },
      },
      ui: { log: async () => {}, status: async () => {}, toast: async () => {} },
      fs: { write: async () => {} },
      plugin: { root: '/plugin' },
    } as unknown as EngineInterface,
    runs,
  }
}

const ctx = (petCheckedAt = 0): SessionContext => ({
  runDir: '/tmp/desk-pet', petFile: '', project: 'demo', cwd: '/w/demo',
  sessionKey: 'session:s1', toolErrors: 0, petCheckedAt,
})

test('petAlive：探测 exit 0 = 活着，非 0/抛异常 = 不在', async () => {
  strictEqual(await petAlive(make$(0).$), true)
  strictEqual(await petAlive(make$(1).$), false)
  strictEqual(await petAlive(make$('throw').$), false)
})

test('ensurePetAlive：活着时只探测不启动', async () => {
  const { $, runs } = make$(0)
  await ensurePetAlive(ctx(), $, 100_000)
  strictEqual(runs.length, 1) // 只有探活，没有 launch
})

test('ensurePetAlive：10s 节流窗口内不再探测', async () => {
  const { $, runs } = make$(0)
  const c = ctx()
  await ensurePetAlive(c, $, 100_000)
  await ensurePetAlive(c, $, 105_000) // 5s < 10s，跳过
  strictEqual(runs.length, 1)
  strictEqual(c.petCheckedAt, 100_000)
})

test('ensurePetAlive：探活失败（被杀）→ 重新 launchPet', async () => {
  const { $, runs } = make$(1)
  const c = ctx()
  await ensurePetAlive(c, $, 100_000)
  // 第 1 次 run 是探活；之后 launchPet 会再 run（macOS 先 venv 检查再启动）
  const probe = runs[0].join(' ')
  strictEqual(probe.includes('47321'), true)
  strictEqual(runs.length > 1, true)
})

test('petAlive：PET_PORT 环境变量换探活端口（#5）', async () => {
  const { $, runs } = makeEnv$({ PET_PORT: '47400' }, 0)
  strictEqual(await petAlive($), true)
  const probe = runs[0].join(' ')
  strictEqual(probe.includes('47400'), true)
  strictEqual(probe.includes('47321'), false)
})

test('petAlive：PET_PORT 是垃圾值时用默认端口', async () => {
  const { $, runs } = makeEnv$({ PET_PORT: 'not-a-port' }, 0)
  await petAlive($)
  strictEqual(runs[0].join(' ').includes('47321'), true)
})

test('launchPet：自动拉起带 --quiet（单实例冲突只写日志，不弹对话框）', async () => {
  // Windows 分支：不触发 macOS 的 venv 检查，launch.py 一次 run 走完
  const { $, runs } = makeEnv$({ SystemRoot: 'C:\\Windows' }, 0)
  strictEqual(await launchPet($, '/run'), true)
  const launch = runs[0].join(' ')
  strictEqual(launch.includes('launch.py'), true)
  strictEqual(launch.includes('--quiet'), true)
})
