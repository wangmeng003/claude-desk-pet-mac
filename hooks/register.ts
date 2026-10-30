// register：只注册事件/命令并创建 SessionContext，逻辑都在各职责模块里。
// 行为与拆分前的单文件 register.ts 一致（M1 Step 3，见 ARCHITECTURE §6）。
import type { Register } from 'claude-code'
import { initContext, type SessionContext } from './context.ts'
import { READING, describe } from './state.ts'
import { pet } from './state_writer.ts'
import { account, ensureSessionRecord } from './accounting.ts'
import { refreshStatus } from './statusline.ts'
import { launchPet } from './launcher.ts'
import { petCommand, tokenStats } from './commands.ts'

export const register: Register = on => {
  // 每会话一个；session.start 里创建（mod 重载时随闭包重建）
  let ctx: SessionContext | undefined

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    ctx = await initContext($, e)
    await ensureSessionRecord(ctx, $)

    // 命令注册失败（比如 mod 重载后重名）不能连带桌宠起不来
    try {
      await $.command.register({ name: 'token-stats', description: '查看本会话和本项目累计的 token 用量、缓存命中率' })
      await $.command.register({ name: 'pet', description: '重新召唤桌宠悬浮窗（macOS 可用 /pet setup 重新准备环境）' })
    } catch (err) {
      $.ui.log(`命令注册失败：${String(err)}`, { to: 'debug' })
    }

    await pet(ctx, $, 'waiting', '我来啦～')
    void launchPet($, ctx.runDir)
    void refreshStatus(ctx, $).catch(() => {})
    return started
  })

  on('turn.start', async ($, e, next) => {
    if (ctx && e.agentId === undefined) {
      ctx.toolErrors = 0
      await pet(ctx, $, 'thinking', '思考中')
    }
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    // 桌宠这边的错误绝不能拦住工具，也不能在工具已经放行之后再抛：
    // 一旦在 next(e) 之后抛错，兜底的 catch 会再跑一次 next(e)，
    // 等于把工具（比如 Bash 命令）执行两遍。
    const isMain = e.agentId === undefined
    if (isMain && ctx) {
      try {
        const input = e as unknown as Record<string, unknown>
        await pet(ctx, $, READING.has(e.tool) ? 'reading' : 'tool', describe(e.tool, input))
      } catch (err) {
        $.ui.log(`桌宠状态更新失败：${String(err)}`, { to: 'debug' })
      }
    }

    const ran = await next(e)

    if (isMain && ctx) {
      try {
        if (ran.deny === undefined && ran.isError === true) {
          ctx.toolErrors += 1
          // 连续出错 3 次：石化彩蛋
          if (ctx.toolErrors >= 3) await pet(ctx, $, 'stone', '石化了…')
          else await pet(ctx, $, 'error', '出错了…')
        } else {
          ctx.toolErrors = 0
          await pet(ctx, $, 'thinking', '思考中')
        }
      } catch (err) {
        $.ui.log(`桌宠状态更新失败：${String(err)}`, { to: 'debug' })
      }
    }
    return ran
  }).catch(($, e, next) => next(e)) // 桌宠这边出任何错，都照常放行工具调用

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (!ctx) return done
    try {
      await account(ctx, $, e.usage)
      await refreshStatus(ctx, $)
    } catch (err) {
      $.ui.log(`用量统计失败：${String(err)}`, { to: 'debug' })
    }

    if (e.agentId !== undefined) return done

    if (e.reason === 'aborted') {
      await pet(ctx, $, 'aborted', '被打断了…')
    } else if (e.reason === 'error' || e.reason === 'refusal') {
      await pet(ctx, $, 'error', '出错了，来看看？', 'error')
    } else if (e.durationMs > 180_000) {
      // 干了 3 分钟以上的大活：撒花
      await pet(ctx, $, 'celebrate', '搞定啦！轮到你～', 'done')
    } else {
      await pet(ctx, $, 'waiting', '轮到你啦！', 'done')
    }
    return done
  })

  on('command.run', { command: 'token-stats' }, async ($, e, next) => ctx ? tokenStats(ctx, $) : next(e))

  on('command.run', { command: 'pet' }, async ($, e, next) => ctx ? petCommand(ctx, $, e) : next(e))
}
