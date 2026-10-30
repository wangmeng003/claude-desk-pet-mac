// launcher：运行时解析。venv 路径必须跟着运行目录走，不能写死 ~/.claude/desk-pet。
import { test } from 'node:test'
import { strictEqual } from 'node:assert'
import type { EngineInterface } from 'claude-code'
import { ensureMacVenv, launchPet, venvPython } from './launcher.ts'

function make$(opts: { windows?: boolean } = {}) {
  const calls: string[][] = []
  const $ = {
    env: {
      get: async (n: string) => {
        if (opts.windows) return n === 'SystemRoot' ? 'C:\\Windows' : undefined
        return n === 'HOME' ? '/home/me' : undefined
      },
    },
    process: {
      run: async (argv: string[]) => {
        calls.push(argv)
        return { exitCode: 0, stdout: '', stderr: '' }
      },
    },
    fs: { write: async () => {} },
    ui: { status: async () => {}, log: () => {}, toast: () => {} },
    plugin: { root: '/plugin' },
  } as unknown as EngineInterface
  return { $, calls }
}

test('venvPython：venv 路径跟着运行目录走', () => {
  strictEqual(venvPython('/custom/run'), '/custom/run/venv/bin/python')
  strictEqual(venvPython('/home/me/.claude/desk-pet'), '/home/me/.claude/desk-pet/venv/bin/python')
})

test('ensureMacVenv：检查的是运行目录里的 venv', async () => {
  const { $, calls } = make$()
  await ensureMacVenv($, '/custom/run')
  strictEqual(calls[0][0], '/custom/run/venv/bin/python')
  strictEqual(calls[0][1], '-c')
})

test('launchPet：用运行目录里的 venv python 启动桌宠', async () => {
  const { $, calls } = make$()
  const ok = await launchPet($, '/custom/run')
  strictEqual(ok, true)
  const last = calls[calls.length - 1]
  strictEqual(last[0], '/custom/run/venv/bin/python')
  strictEqual(last[1], '/plugin/pet/launch.py')
  strictEqual(last[2], '/plugin/pet/pet_mac.py')
  strictEqual(last[3], '/custom/run')
})

test('launchPet：Windows 走 cmd.exe，参数用反斜杠', async () => {
  const { $, calls } = make$({ windows: true })
  const ok = await launchPet($, 'C:/run')
  strictEqual(ok, true)
  strictEqual(calls[0][0], 'C:\\Windows\\System32\\cmd.exe')
  strictEqual(calls[0][6], 'C:/run')
})
