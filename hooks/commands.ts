// commands：/pet、/pet setup、/pet doctor、/pet theme、/token-stats 的用例。返回 { text } 给引擎回显。
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import { statsText } from './statusline.ts'
import { ensureMacVenv, launchPet } from './launcher.ts'
import { pet } from './state_writer.ts'
import { doctorText } from './doctor.ts'

export async function tokenStats(ctx: SessionContext, $: EngineInterface) {
  return { text: await statsText(ctx, $) }
}

// theme：/pet theme 子命令（M4，specs/theme.md §4）。校验/安装/切换主体在
// pet/theme_cli.py（纯 stdlib，系统 python 即可跑），这里只组装参数、回显 stdout。
const THEME_USAGE = `用法：/pet theme <子命令>
  /pet theme list                    列出已安装的主题
  /pet theme install <路径|zip>      安装主题包（加 --force 覆盖已装的）
  /pet theme use <id|builtin>        切换主题（builtin = 内置皮肤）
  /pet theme remove <id>             删除主题（使用中的要先切走）
  /pet theme info <id>               主题详情`

async function themeText($: EngineInterface, runDir: string, cliArgs: string[]): Promise<string> {
  const script = `${$.plugin.root}/pet/theme_cli.py`
  const argv = (await $.env.get('SystemRoot'))
    ? ['C:\\Windows\\System32\\cmd.exe', '/d', '/c', 'python', script, ...cliArgs, runDir]
    : ['/usr/bin/env', 'python3', script, ...cliArgs, runDir]
  try {
    // 安装含 zip 解压与校验，给宽一点
    const ran = await $.process.run(argv, { timeoutMs: 120_000 })
    return ran.stdout.trim() || `theme 命令没有输出（exit=${ran.exitCode}）。python 不在 PATH 里？`
  } catch (err) {
    return `theme 命令跑不起来：${String(err)}（python 不在 PATH 里？）`
  }
}

export async function petTheme(ctx: SessionContext, $: EngineInterface, args: string) {
  const parts = args.trim().split(/\s+/).filter(Boolean)
  const sub = parts.shift() ?? ''
  if (!sub || sub === 'help') return { text: THEME_USAGE }
  if (!['list', 'install', 'use', 'remove', 'info'].includes(sub)) {
    return { text: `不认识的子命令：${sub}\n\n${THEME_USAGE}` }
  }
  const cliArgs = [sub]
  if (sub === 'install') {
    // 路径可能带空格：除 --force 外的剩余参数拼回一个目标
    const force = parts.includes('--force')
    const target = parts.filter((a) => a !== '--force').join(' ')
    if (!target) {
      return { text: '要装哪个主题包？例如：/pet theme install ~/Downloads/my-pet\n\n' + THEME_USAGE }
    }
    cliArgs.push(target)
    if (force) cliArgs.push('--force')
  } else if (sub !== 'list') {
    const id = parts.join(' ')
    if (!id) return { text: `用法：/pet theme ${sub} <id|builtin>\n\n` + THEME_USAGE }
    cliArgs.push(id)
  }
  return { text: await themeText($, ctx.runDir, cliArgs) }
}

export async function petCommand(ctx: SessionContext, $: EngineInterface, e: unknown) {
  const args = typeof (e as { args?: unknown }).args === 'string'
    ? (e as { args: string }).args.trim()
    : ''

  if (args === 'doctor') {
    return { text: await doctorText($, ctx.runDir) }
  }

  if (args === 'theme' || args.startsWith('theme ')) {
    return petTheme(ctx, $, args.slice('theme'.length))
  }

  if (args === 'setup') {
    if (await $.env.get('SystemRoot')) {
      return { text: 'Windows 不需要额外准备环境，直接 /pet 就能召唤桌宠。' }
    }
    if (!(await ensureMacVenv($, ctx.runDir, true))) {
      return { text: '环境准备失败。详情见 ~/.claude/desk-pet/setup.log；也可以按 README 手动创建 venv。' }
    }
    if (!(await launchPet($, ctx.runDir))) {
      return { text: '环境已就绪，但桌宠启动失败。详情见 ~/.claude/desk-pet/mod-launch.log。' }
    }
    await pet(ctx, $, 'waiting', '我在这儿～', { attention: false })
    return { text: '桌宠环境已就绪，桌宠已召唤。' }
  }

  if (!(await launchPet($, ctx.runDir))) {
    return {
      text: '桌宠没起来。macOS 第一次运行需要准备环境，运行 /pet setup 重试；详情见 ~/.claude/desk-pet/setup.log。',
    }
  }
  await pet(ctx, $, 'waiting', '我在这儿～', { attention: false })
  return { text: '桌宠已召唤（如果它本来就开着，就不会再开第二个）。' }
}
