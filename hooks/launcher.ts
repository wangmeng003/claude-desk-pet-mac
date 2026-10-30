// launcher：桌宠运行时解析（Windows 直跑 / macOS 插件 venv）、启动与健康检查。
import type { EngineInterface } from 'claude-code'

// venv 建在**运行目录**里（setup.py 按 runDir 建 ${runDir}/venv），
// 检查和启动必须用同一个路径——写死 ~/.claude/desk-pet 的话，
// 换运行目录就会拿错解释器（要么找不到，要么跑到没装 pyobjc 的 python）。
export const venvPython = (runDir: string) => `${runDir}/venv/bin/python`

// macOS 的桌宠跑在插件自己的 venv 里；先确认 Pillow 和 pyobjc 都能导入
async function macVenvReady($: EngineInterface, python: string) {
  try {
    const ran = await $.process.run([python, '-c', 'import PIL, objc'], { timeoutMs: 30_000 })
    return ran.exitCode === 0
  } catch {
    return false
  }
}

// 首次运行自动建 venv、装依赖；失败时在状态栏/通知栏留一句提示
export async function ensureMacVenv($: EngineInterface, runDir: string, force = false) {
  if (!runDir) return false
  const python = venvPython(runDir)
  if (!force && (await macVenvReady($, python))) return true

  try {
    await $.ui.status('🐾 第一次运行，正在准备桌宠环境（约 1 分钟）…')
    const argv = ['/usr/bin/env', 'python3', `${$.plugin.root}/pet/setup.py`, runDir]
    if (force) argv.push('--force')
    const ran = await $.process.run(argv, { timeoutMs: 600_000 })
    if (ran.exitCode === 0 && (await macVenvReady($, python))) return true
    if (ran.exitCode === 2) {
      await $.ui.status('🐾 上次环境准备失败，运行 /pet setup 重试')
      return false
    }
    await $.fs.write(
      `${runDir}/mod-launch.log`,
      `桌宠环境准备失败 exit=${ran.exitCode}\n${ran.stdout}\n${ran.stderr}`,
    ).catch(() => {})
    $.ui.log(`桌宠环境准备失败：exit=${ran.exitCode}\n${ran.stdout}\n${ran.stderr}`, { to: 'debug' })
  } catch (err) {
    $.ui.log(`桌宠环境准备失败：${String(err)}`, { to: 'debug' })
  }
  await $.ui.status('🐾 桌宠环境准备失败：运行 /pet setup 重试，或查看 ~/.claude/desk-pet/setup.log')
  $.ui.toast('桌宠环境准备失败，运行 /pet setup 重试')
  return false
}

export async function launchPet($: EngineInterface, runDir: string): Promise<boolean> {
  if (!runDir) return false
  try {
    let ran: { exitCode: number; stdout: string; stderr: string }
    if (await $.env.get('SystemRoot')) {
      // Windows：引擎不按 PATH 找程序，交给 cmd.exe 去找 python
      // （cmd.exe 的路径必须用反斜杠，用正斜杠时 cmd 会把 /Windows 当成开关）
      ran = await $.process.run(
        ['C:\\Windows\\System32\\cmd.exe','/d', '/c', 'python', `${$.plugin.root}/pet/launch.py`, `${$.plugin.root}/pet/pet.pyw`, runDir],
        { timeoutMs: 15000 },
      )
    } else {
      // macOS：先准备 venv，再用 venv 里的 python 启动桌宠
      if (!(await ensureMacVenv($, runDir))) return false
      ran = await $.process.run(
        [venvPython(runDir), `${$.plugin.root}/pet/launch.py`, `${$.plugin.root}/pet/pet_mac.py`, runDir],
        { timeoutMs: 15000 },
      )
    }
    if (ran.exitCode !== 0) {
      await $.fs.write(`${runDir}/mod-launch.log`, `exit=${ran.exitCode}\n${ran.stdout}\n${ran.stderr}`)
      return false
    }
    return true
  } catch (err) {
    $.ui.log(`桌宠启动失败：${String(err)}`, { to: 'debug' })
    await $.fs.write(`${runDir}/mod-launch.log`, `启动 python 失败：${String(err)}`).catch(() => {})
    return false
  }
}
