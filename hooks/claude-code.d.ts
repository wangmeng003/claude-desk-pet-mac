// 临时类型 shim：插件引擎在运行时注入 `claude-code` 模块，npm 包未导出引擎类型。
// 这里只声明 register.ts 用到的最小表面；官方类型可用后删除本文件。
declare module 'claude-code' {
  export interface RateLimit {
    kind: string
    percentUsed: number
    resetsAt?: number
  }

  export interface SessionUsage {
    cost?: { usd: number }
    context: { percent?: number }
    rateLimits: RateLimit[]
  }

  export interface RunResult {
    exitCode: number
    stdout: string
    stderr: string
  }

  export interface EngineInterface {
    store: {
      get(key: string): Promise<unknown>
      set(key: string, value: unknown): Promise<void>
    }
    clock: { now(): Promise<number> }
    fs: { write(path: string, content: string): Promise<void> }
    env: { get(name: string): Promise<string | undefined> }
    process: {
      run(argv: string[], opts?: { timeoutMs?: number }): Promise<RunResult>
    }
    ui: {
      status(text: string): Promise<void>
      log(text: string, opts?: { to?: 'debug' | 'status' }): void
      toast(text: string): void
    }
    session: {
      id(): Promise<string>
      usage(): Promise<SessionUsage>
    }
    command: {
      register(cmd: { name: string; description: string }): Promise<void>
    }
    plugin: { root: string }
  }

  export type Next = (event: unknown) => Promise<any>
  export type Handler = ($: EngineInterface, event: any, next: Next) => Promise<any>

  export interface HookRegistration {
    catch(handler: Handler): void
  }

  // 引擎传入的 registrar 本身就是可调用对象：on(event, handler) 直接注册
  export interface OnFunction {
    (
      event: 'session.start' | 'session.end' | 'turn.start' | 'tool.call' | 'turn.complete'
        | 'classic.Notification',
      handler: Handler,
    ): HookRegistration
    (event: 'command.run', filter: { command: string }, handler: Handler): void
  }

  export type Register = (on: OnFunction) => void
}
