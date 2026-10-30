# 0001. PermissionRequest hook 可行性与 P2 审批架构

- 状态：接受
- 日期：2026-10-30
- 相关：[权限提醒与审批](../specs/permission.md) · [里程碑](../MILESTONES.md) M0 · [spike 脚本](../../spikes/permission-hook/)

## 背景

M0 的 go/no-go 问题：Claude Code 的 hook 机制能不能稳定地接收权限请求并返回 allow/deny，且任何失败都不阻塞终端、零误放行。这决定 P2「单请求卡片」做不做（[permission.md](../specs/permission.md) §3、§9）。

验证环境：Claude Code 2.1.312（本机 macOS arm64 原生安装），2026-10-30，隔离目录 `/tmp/desk-pet-spike` + `claude -p` 非交互模式。脚本与配置归档在 `spikes/permission-hook/`。

## 决策

1. **GO：P2 可做。** 审批链路按 [permission.md](../specs/permission.md) §5 既定架构实施：原生 `PermissionRequest` hook（settings 配置）→ 本机 HTTP bridge → 单请求卡片。
2. **审批只能走原生 hook。** 插件引擎（mods）事件清单为 `session.start / session.end / turn.start / turn.complete / tool.call / command.run / notification`，**没有权限事件**。P1 的 attention 触发可以用插件引擎 `notification` 事件；P2 审批必须注册原生 hook。
3. **客户端入参契约以实测为准**（见下表），覆盖 specs/permission.md §5.3 的设计假设。
4. **组合规则写入部署约束**：同一事件多个 hook 时，**第一个返回决策的 hook 获胜**（实测 `[allow, deny]` → 放行；`[deny, allow]` → 拦截）。desk-pet 无 bridge 时必须输出无决策的空 JSON，不得抢别人的决策位；反过来，用户机器上已有返回决策的 hook 时 desk-pet 卡片会失效——这是可接受的部署约束，写进 README。

## 实测记录

### 入参 schema（Q1/Q2/Q5：事件、字段、运行环境）

```json
{
  "session_id": "uuid",
  "transcript_path": "/Users/<name>/.claude/projects/-private-tmp-…/<session>.jsonl",
  "cwd": "/private/tmp/desk-pet-spike",
  "prompt_id": "uuid",
  "permission_mode": "default",
  "effort": { "level": "high" },
  "hook_event_name": "PermissionRequest",
  "tool_name": "Bash",
  "tool_input": { "command": "…", "description": "…" },
  "permission_suggestions": [
    { "type": "addDirectories", "directories": ["/tmp/desk-pet-spike"], "destination": "session" }
  ]
}
```

- 输出契约：`{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}` 或 `{"behavior":"deny","message":"…"}`。
- 运行环境（Q5）：`/bin/bash` 执行；**继承完整用户 PATH**（非裸 env）；`PWD` = 会话 cwd 的物理路径（macOS 上 `/tmp` → `/private/tmp`）；`TERM=dumb`。
- 对**所有工具**触发（matcher 可省略，实测 Write 也触发）；`matcher: "Bash"` 精确匹配工具名。

### 行为矩阵（Q3/Q4/Q6：阻塞、超时、失败路径）

| # | 场景 | 结果 | 关键证据 |
|---|---|---|---|
| 1 | allow | ✅ 放行，print 模式下无人工干预直接执行 | 标记文件写入，总耗时 15.6s |
| 2 | deny | ✅ 拦截，`message` 原样传给模型 | 标记未写入，输出含自定义消息 |
| 3 | 空决策 `{}` | ✅ 回退终端原生流程 | 标记未写入，CLI 退出码 0 |
| 4 | 非法 JSON | ✅ 回退 | 同上，不崩溃 |
| 5 | exit 1 崩溃 | ✅ 回退 | 同上 |
| 6 | exit 2 | ✅ 阻塞工具调用 | 标记未写入；stderr 反馈未出现在 print 模式最终输出（交互模式待补测） |
| 7 | 超时（timeout:5，hook sleep 60） | ✅ 5040ms 杀掉，回退 ask | debug 日志 `timed out after 5000ms (5040ms)` |
| 8 | 双会话并发 | ✅ 独立进程、决策各自生效、无串会话 | 两个 marker 均写入，pid/ppid 不同 |
| 9 | 多 hook 决策组合 | 第一个返回决策的获胜 | `[allow,deny]`→放行；`[deny,allow]`→拦截 |
| 10 | 与全局 hook 叠加 | ✅ 用户全局无决策 hook（返回 `{}`）不干扰项目级决策 | 本机 `~/.claude/settings.json` 已有 cc-status/orca 两个 PermissionRequest hook |

### Q6 安全底线（静态 + 实证）

- **零误放行的实证**：上表 3/4/5/7 四种失败路径全部回退 ask，没有任何一条产生 allow。
- CLI 内部对失败路径的统一处理：`timeout / exit / malformed / spawn_failed` → `permissionBehavior:"ask"`，二进制中不存在失败→allow 的路径。
- allow 会被忽略的已知场景（静态查证，来自 CLI 告警字符串）：家族名匹配（如只匹配 `Bash` 家族而非具体工具）、CCR 云浏览器工具、Projects 会话的 WebFetch/WebSearch、声明为 code-running 的 MCP 工具、Cowork 云会话的 setMode。全部回退 ask，无副作用。
- **模型重试**：超时回退后模型可能再次发起同一工具调用（实测一次回退后出现第二次 hook 调用）。bridge 客户端必须幂等：`id` 去重、忙时 409、重复决策安全。
- 已知修复史（2.1.x 变更日志字符串）：Windows 上 PowerShell hook exit 2 不阻塞、Git for Windows 缺失时 PreToolUse/PermissionRequest 错误 fail-open——Windows 是重点回归面。

## 备选方案

- **只做 P1（放弃卡片）**：spike 已通过，不成立；保留为 kill criteria 的回退位。
- **PreToolUse + `permissionDecision`**：语义不同——PreToolUse 在工具执行前触发，决策字段为 `allow/deny/ask/defer`，且 allow 仅限"本会话已决定可跑"的场景；PermissionRequest 才是"正在问用户"的事件。P1 attention 也不该用它（会干扰其他工具的正常流）。
- **插件引擎拦截 `tool.call`**：引擎只给观察/记账能力，无权限决策事件；且 register.ts 现有的 `tool.call` 中间件不能安全地表达审批。
- **补丁/注入 Claude Code**：明确违反 [ROADMAP](../ROADMAP.md) §9 边界，不考虑。

## 后果

**好处**

- P2  unblock：少切窗口的审批卡片可以按 §5 设计直接开工。
- 契约定稿：入参字段、超时语义、失败路径、组合规则全部有实测依据，M1/M2 issue 可直接引用本文档。

**代价与风险**

- hook 配置是**全局顺序敏感的**：desk-pet 安装/卸载必须正确插入和移除自己的 hook 项；卸载残留会破坏别人的审批（若残留项返回固定决策）。
- 超时杀掉的是 hook 进程：客户端脚本内不能做不可中断的等待；HTTP 等待要分片可被杀（或接受被杀=回退 ask，这正好符合 fail-open 语义，实现更简单——被杀即 ask）。
- 模型重试带来重复请求：bridge 必须幂等（specs 已要求，实测证实必要）。
- `cwd` 是物理路径：bridge 若做项目匹配需先规范化（realpath）。

**Windows 未验证**：本机无 Windows。2.1.312 的 Windows hook 修复史说明该面 historically 不稳定，M2 开始前必须在 Windows 上重跑矩阵。

**待补测**（不阻塞 P2 启动，进入 M2 测试计划）：exit 2 反馈在交互模式的呈现；`permission_mode` 非 default（acceptEdits/bypassPermissions）时 hook 是否仍触发；长命令/Unicode 入参边界；`--permission-prompts none` 场景。

## 验证

- 本文矩阵在 Claude Code 2.1.312 上全部实测通过；复跑方式见 `spikes/permission-hook/README.md`。
- 重新评估触发条件：Claude Code 大版本升级（hook 行为无兼容性承诺）、出现任何误放行报告、Windows 实测与本文结论冲突。
