// state：工具名 → 桌宠状态/气泡文案的纯映射。无副作用，可单测。

// 桌宠的状态（悬浮窗程序按这个名字换表情）
export type PetState = 'thinking' | 'tool' | 'reading' | 'waiting' | 'celebrate' | 'error' | 'aborted' | 'stone'

// 读资料类工具 → 记笔记表情；其余 → 敲键盘
export const READING = new Set(['Read', 'Grep', 'Glob', 'WebFetch', 'WebSearch', 'NotebookRead'])

export const baseName = (p: string) => p.split(/[\\/]/).filter(Boolean).pop() ?? p

// 气泡文案最长 60 字符（状态协议 §4.3），超了截断加省略号
export const MAX_TEXT = 60
export const clip = (s: string) => (s.length > MAX_TEXT ? `${s.slice(0, MAX_TEXT - 1)}…` : s)

// 工具名 → 气泡里的一句话
export const describe = (tool: string, input: Record<string, unknown>) => {
  const file = typeof input.file_path === 'string' ? baseName(input.file_path) : ''
  if (tool === 'Bash' || tool === 'PowerShell') return '在跑命令…'
  if (tool === 'Edit' || tool === 'Write') return clip(file ? `在改 ${file}` : '在改文件…')
  if (tool === 'Read') return clip(file ? `在读 ${file}` : '在翻文件…')
  if (tool === 'Grep' || tool === 'Glob') return '在找东西…'
  if (tool === 'WebSearch' || tool === 'WebFetch') return '在上网查…'
  if (tool === 'Agent') return '派小助手干活中'
  if (tool.startsWith('mcp__')) return clip(`在用 ${tool.split('__').pop()}`)
  return clip(`在用 ${tool}`)
}
