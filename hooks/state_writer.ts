// state_writer：写状态协议 v1（specs/state.md §2）的状态文件给悬浮窗读。
// sound 让悬浮窗播放提示音（引擎在 Windows 上没有播放器）；attention 由写入方
// 显式设置、覆盖状态默认值，读取方不要猜。出错也不能影响 Claude 干活。
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import type { PetState } from './state.ts'
import { ensurePetAlive } from './launcher.ts'

export async function pet(
  ctx: SessionContext,
  $: EngineInterface,
  state: PetState,
  text: string,
  opts: { sound?: 'done' | 'error'; attention?: boolean } = {},
) {
  if (!ctx.petFile) return
  try {
    // ts 用 Unix 秒（状态协议 §2）；引擎给的时钟是毫秒，这里换算。
    // 不换算的话以后按 ts 算 TTL 会把文件当成「未来时间戳」直接丢掉。
    const raw = await $.clock.now()
    const ts = raw > 1e11 ? raw / 1000 : raw
    const payload: Record<string, unknown> = {
      v: 1,
      session: ctx.sessionKey.replace(/^session:/, ''),
      agent: 'claude-code',
      state,
      text,
      project: ctx.project,
      ts,
    }
    if (opts.sound !== undefined) payload.sound = opts.sound
    if (opts.attention !== undefined) payload.attention = opts.attention
    await $.fs.write(ctx.petFile, JSON.stringify(payload))
    // 探活放在写成功之后：被杀的桌宠由下一个事件自动拉起（#4），失败静默不影响 Claude
    void ensurePetAlive(ctx, $, ts * 1000).catch(() => {})
  } catch {}
}
