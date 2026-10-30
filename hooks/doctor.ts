// doctor：/pet doctor 的用例（#7）。引擎没有文件读取 API，
// 诊断主体在 pet/doctor.py 里跑，stdout 原样回显（可直接粘贴到 issue）。
import type { EngineInterface } from 'claude-code'
import { petPort } from './launcher.ts'

export async function doctorText($: EngineInterface, runDir: string): Promise<string> {
  const port = await petPort($)
  const script = `${$.plugin.root}/pet/doctor.py`
  const argv = (await $.env.get('SystemRoot'))
    ? ['C:\\Windows\\System32\\cmd.exe', '/d', '/c', 'python', script, runDir, $.plugin.root, `${port}`]
    : ['/usr/bin/env', 'python3', script, runDir, $.plugin.root, `${port}`]
  try {
    const ran = await $.process.run(argv, { timeoutMs: 90_000 })
    const body = ran.stdout.trim()
    if (body) return body
    return `诊断脚本没有输出（exit=${ran.exitCode}）。python 不在 PATH 里？`
  } catch (err) {
    return `诊断脚本跑不起来：${String(err)}（python 不在 PATH 里？）`
  }
}
