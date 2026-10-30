// state_writer：写状态文件给悬浮窗读。sound 让悬浮窗播放提示音（引擎在 Windows 上没有播放器）。
// 出错也不能影响 Claude 干活。M1 后续的原子写/损坏容忍（#8）在这里落地。
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import type { PetState } from './state.ts'

export async function pet(
  ctx: SessionContext,
  $: EngineInterface,
  state: PetState,
  text: string,
  sound?: 'done' | 'error',
) {
  if (!ctx.petFile) return
  try {
    const ts = await $.clock.now()
    await $.fs.write(ctx.petFile, JSON.stringify({ state, text, project: ctx.project, ts, sound }))
  } catch {}
}
