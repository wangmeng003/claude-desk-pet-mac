// 临时类型 shim：单测用 node:test / node:assert，tsc 环境没有 @types/node。
// 只声明用到的最小表面；接入 @types/node 后删除本文件。
declare module 'node:test' {
  export function test(name: string, fn: () => void | Promise<void>): void
}

declare module 'node:assert' {
  export function strictEqual(actual: unknown, expected: unknown, message?: string): void
}
