// commands：/pet、/pet setup、/token-stats 的用例。返回 { text } 给引擎回显。
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import { statsText } from './statusline.ts'
import { ensureMacVenv, launchPet } from './launcher.ts'
import { pet } from './state_writer.ts'

export async function tokenStats(ctx: SessionContext, $: EngineInterface) {
  return { text: await statsText(ctx, $) }
}

export async function petCommand(ctx: SessionContext, $: EngineInterface, e: unknown) {
  const args = typeof (e as { args?: unknown }).args === 'string'
    ? (e as { args: string }).args.trim()
    : ''

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
