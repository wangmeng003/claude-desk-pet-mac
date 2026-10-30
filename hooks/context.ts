// 每会话一个 context：把原来 register.ts 的模块级可变变量（runDir/petFile/...）收拢成显式传参。
// session.start 时创建；mod 重载会重新执行 register，闭包里的 ctx 随之重建。
import type { EngineInterface } from 'claude-code'
import { baseName } from './state.ts'

export type SessionContext = {
  runDir: string
  petFile: string
  project: string
  cwd: string
  sessionKey: string
  toolErrors: number
  petCheckedAt: number  // 上次探活时间戳（ms），ensurePetAlive 节流用
  privacy?: boolean       // 隐私模式（#8）：不写项目名/文件名。桌宠菜单改 settings.json，这里 60s 缓存重读
  privacyCheckedAt?: number
}

export async function initContext($: EngineInterface, e: { cwd: string }): Promise<SessionContext> {
  const home = ((await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? '').replace(/\\/g, '/')
  // 运行目录放在 ~/.claude/desk-pet，不放进 mod 文件夹（避免触发热重载）
  const runDir = `${home}/.claude/desk-pet`
  if (!home) {
    // HOME/USERPROFILE 都没有：路径会退到 '/.claude/desk-pet'（写不进去就静默失败）。
    // 不用相对路径：那样会在用户的项目目录里凭空造出 .claude/desk-pet。
    $.ui.log('桌宠：拿不到 HOME/USERPROFILE，状态文件可能写不进去', { to: 'debug' })
  }
  const sessionId = await $.session.id()
  return {
    runDir,
    petFile: `${runDir}/sessions/${sessionId}.json`,
    project: baseName(e.cwd),
    cwd: e.cwd,
    sessionKey: `session:${sessionId}`,
    toolErrors: 0,
    petCheckedAt: 0,
  }
}
