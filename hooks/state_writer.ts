// state_writer：写状态协议 v1（specs/state.md §2）的状态文件给悬浮窗读。
// sound 让悬浮窗播放提示音（引擎在 Windows 上没有播放器）；attention 由写入方
// 显式设置、覆盖状态默认值，读取方不要猜。出错也不能影响 Claude 干活。
import type { EngineInterface } from 'claude-code'
import type { SessionContext } from './context.ts'
import type { PetState } from './state.ts'
import { ensurePetAlive } from './launcher.ts'

// 隐私模式（#8）下动态文案的替身：tool/reading 的文案带文件名，其他状态都是固定话术
const PRIVACY_TEXT: Partial<Record<PetState, string>> = {
  tool: '在干活…',
  reading: '在看资料…',
}
const PRIVACY_RECHECK_MS = 60_000

// 读桌宠设置里的 privacy 开关。引擎没有文件读取 API，借 python 读 settings.json
// （读不到/坏 JSON/python 缺失都按「关」处理，不影响 Claude 干活）。
async function settingsPrivacy($: EngineInterface, runDir: string): Promise<boolean> {
  const script = [
    'import json,sys',
    'try:',
    " print(1 if json.load(open(sys.argv[1])).get('privacy') else 0)",
    'except (OSError, ValueError):',
    ' print(0)',
  ].join('\n')
  const path = `${runDir}/settings.json`
  const argv = (await $.env.get('SystemRoot'))
    ? ['C:\\Windows\\System32\\cmd.exe', '/d', '/c', 'python', '-c', script, path]
    : ['/usr/bin/env', 'python3', '-c', script, path]
  try {
    const ran = await $.process.run(argv, { timeoutMs: 5_000 })
    return ran.stdout.trim() === '1'
  } catch {
    return false
  }
}

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
    // 隐私开关 60s 缓存重读：桌宠菜单切换后一分钟内生效，不用每个工具调用都起 python。
    // 读取失败按「关」处理，绝不能因为读开关把状态写入整个吞掉。
    if (ts * 1000 - (ctx.privacyCheckedAt ?? 0) > PRIVACY_RECHECK_MS) {
      ctx.privacyCheckedAt = ts * 1000
      try {
        ctx.privacy = await settingsPrivacy($, ctx.runDir)
      } catch {
        ctx.privacy = false
      }
    }
    const payload: Record<string, unknown> = {
      v: 1,
      session: ctx.sessionKey.replace(/^session:/, ''),
      agent: 'claude-code',
      state,
      text: (ctx.privacy && PRIVACY_TEXT[state]) || text,
      project: ctx.privacy ? '' : ctx.project,
      ts,
    }
    if (opts.sound !== undefined) payload.sound = opts.sound
    if (opts.attention !== undefined) payload.attention = opts.attention
    await $.fs.write(ctx.petFile, JSON.stringify(payload))
    // 探活放在写成功之后：被杀的桌宠由下一个事件自动拉起（#4），失败静默不影响 Claude
    void ensurePetAlive(ctx, $, ts * 1000).catch(() => {})
  } catch {}
}
