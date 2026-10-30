// state 纯映射的锁定测试（从 register.ts 原样搬出，行为不变）。
import { test } from 'node:test'
import { strictEqual } from 'node:assert'
import { baseName, clip, describe, READING } from './state.ts'

test('baseName 取路径最后一段（正斜杠/反斜杠/尾斜杠）', () => {
  strictEqual(baseName('/a/b/c.ts'), 'c.ts')
  strictEqual(baseName('C:\\a\\b\\c.ts'), 'c.ts')
  strictEqual(baseName('dir/'), 'dir')
  strictEqual(baseName('c.ts'), 'c.ts')
})

test('describe：命令与文件类工具的文案', () => {
  strictEqual(describe('Bash', {}), '在跑命令…')
  strictEqual(describe('PowerShell', {}), '在跑命令…')
  strictEqual(describe('Edit', { file_path: '/x/pet_mac.py' }), '在改 pet_mac.py')
  strictEqual(describe('Write', {}), '在改文件…')
  strictEqual(describe('Read', { file_path: '/x/a.md' }), '在读 a.md')
  strictEqual(describe('Read', {}), '在翻文件…')
})

test('describe：查找/上网/子代理/其余工具', () => {
  strictEqual(describe('Grep', {}), '在找东西…')
  strictEqual(describe('Glob', {}), '在找东西…')
  strictEqual(describe('WebSearch', {}), '在上网查…')
  strictEqual(describe('WebFetch', {}), '在上网查…')
  strictEqual(describe('Agent', {}), '派小助手干活中')
  strictEqual(describe('mcp__zai__analyze', {}), '在用 analyze')
  strictEqual(describe('TodoWrite', {}), '在用 TodoWrite')
})

test('READING：读资料类工具集合', () => {
  strictEqual(READING.has('Read'), true)
  strictEqual(READING.has('WebFetch'), true)
  strictEqual(READING.has('Bash'), false)
})

test('clip：超过 60 字符的文案截断加省略号', () => {
  strictEqual(clip('短'), '短')
  strictEqual(clip('a'.repeat(60)).length, 60)
  strictEqual(clip('a'.repeat(61)).length, 60)
  strictEqual(clip('a'.repeat(61)).endsWith('…'), true)
})

test('describe：超长文件名/工具名也要截断', () => {
  strictEqual(describe('Read', { file_path: `/x/${'f'.repeat(200)}.md` }).length, 60)
  strictEqual(describe('mcp__' + 'x'.repeat(200), {}).length, 60)
})

test('隐私底线（#8）：文案只含文件名，绝不写完整路径/命令/prompt', () => {
  // 绝对路径只留最后一段
  strictEqual(describe('Edit', { file_path: '/Users/someone/secret/x.ts' }), '在改 x.ts')
  strictEqual(describe('Write', { file_path: 'C:\\Users\\someone\\y.md' }), '在改 y.md')
  // 命令内容、prompt 一概不进文案
  strictEqual(describe('Bash', { command: 'rm -rf ~/.ssh' }), '在跑命令…')
  strictEqual(describe('TodoWrite', { prompt: '帮我看看 ~/.env 里的 KEY' }), '在用 TodoWrite')
})
