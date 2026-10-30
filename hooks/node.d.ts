// 临时类型 shim：单测用 node:test / node:assert / node:fs / node:path，
// tsc 环境没有 @types/node。只声明用到的最小表面；接入 @types/node 后删除本文件。
declare module 'node:test' {
  export function test(name: string, fn: () => void | Promise<void>): void
}

declare module 'node:assert' {
  export function strictEqual(actual: unknown, expected: unknown, message?: string): void
  export function deepStrictEqual(actual: unknown, expected: unknown, message?: string): void
  export function ok(value: unknown, message?: string): void
}

declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string
}

declare module 'node:path' {
  export function join(...parts: string[]): string
}

// 本文件是脚本型 d.ts（无顶层 import/export），这里的接口声明直接进全局
interface ImportMeta {
  readonly dirname: string
}
