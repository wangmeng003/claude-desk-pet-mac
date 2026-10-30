// doctor 用例测试（#7）：argv 组装、stdout 透传、跑不起来时的兜底文案。
import { test } from 'node:test'
import { strictEqual } from 'node:assert'
import type { EngineInterface } from 'claude-code'
import { doctorText } from './doctor.ts'

function make$(opts: { stdout?: string; exit?: number; throw?: boolean; env?: Record<string, string> } = {}) {
  const runs: string[][] = []
  const $ = {
    env: { get: async (k: string) => (opts.env ?? {})[k] },
    process: {
      run: async (argv: string[]) => {
        runs.push(argv)
        if (opts.throw) throw new Error('spawn failed')
        return { exitCode: opts.exit ?? 0, stdout: opts.stdout ?? '', stderr: '' }
      },
    },
    plugin: { root: '/plugin' },
  } as unknown as EngineInterface
  return { $, runs }
}

test('doctorText：argv 带上 doctor.py / runDir / 插件根 / 端口，stdout 原样回显', async () => {
  const { $, runs } = make$({ stdout: '[ok] 平台：darwin\n结论：1 项正常' })
  const text = await doctorText($, '/run')
  strictEqual(text, '[ok] 平台：darwin\n结论：1 项正常')
  const argv = runs[0].join(' ')
  strictEqual(argv.includes('/pet/doctor.py'), true)
  strictEqual(argv.includes('/run'), true)
  strictEqual(argv.includes('/plugin'), true)
  strictEqual(argv.includes('47321'), true)  // 默认端口
})

test('doctorText：PET_PORT 传给诊断脚本', async () => {
  const { $, runs } = make$({ stdout: 'x', env: { PET_PORT: '47400' } })
  await doctorText($, '/run')
  strictEqual(runs[0].join(' ').includes('47400'), true)
})

test('doctorText：脚本无输出时的兜底提示', async () => {
  const { $ } = make$({ stdout: '', exit: 9009 })  // Windows 找不到 python 的典型退出码
  const text = await doctorText($, '/run')
  strictEqual(text.includes('exit=9009'), true)
  strictEqual(text.includes('python 不在 PATH'), true)
})

test('doctorText：process.run 抛异常不炸命令', async () => {
  const { $ } = make$({ throw: true })
  const text = await doctorText($, '/run')
  strictEqual(text.includes('诊断脚本跑不起来'), true)
})
