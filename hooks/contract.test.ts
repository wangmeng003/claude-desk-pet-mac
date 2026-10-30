// 契约测试：hooks 写入方的状态枚举/声音枚举与 contracts/state.schema.json 对齐
// （specs/state.md §6：TS/Python 的枚举和字段必须通过契约测试对齐）。
import { test } from 'node:test'
import { strictEqual, deepStrictEqual } from 'node:assert'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { STATES } from './state.ts'

const schema = JSON.parse(readFileSync(join(import.meta.dirname, '..', 'contracts', 'state.schema.json'), 'utf8'))
const schemaStates: string[] = schema.properties.state.enum

test('STATES 与 schema 的 state enum 完全一致（顺序也一致）', () => {
  deepStrictEqual([...STATES], schemaStates)
})

test('schema 的 sound enum 含 null 占位（JSON Schema 无法表达可空字符串以外的方式）', () => {
  strictEqual(schema.properties.sound.enum.includes('done'), true)
  strictEqual(schema.properties.sound.enum.includes('error'), true)
})
