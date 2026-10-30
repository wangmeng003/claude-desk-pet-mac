# 状态协议 v1

> 状态：草案 · 2026-10-30  
> 适用：插件（写入方）↔ 桌宠（读取方）  
> 关联：[路线图](../ROADMAP.md) · [架构](../ARCHITECTURE.md)

## 0. 目标

用**一个小到不会变质的契约**，让桌宠知道：

- 现在是什么状态；
- 气泡该说什么；
- 是否需要用户注意；
- 这条状态属于哪个会话/项目；
- 什么时候可以丢弃。

**非目标**：token 记账、模型信息、上下文百分比、完整命令、prompt 内容、XP、看板数据。这些留在插件 store 或独立模块，不进状态协议。

---

## 1. 文件与生命周期

### 1.1 位置

```text
~/.claude/desk-pet/
  sessions/
    <session_id>.json
```

- 一个会话一个文件；写入方按 `session_id` 更新。
- 目录 `0700`，文件 `0600`。
- 原子写：同目录临时文件 + `os.replace`；失败重试 2 次。
- 读取方扫描 `sessions/*.json`，不依赖文件 mtime 做业务判断（mtime 只用于“是否变化”）。

### 1.2 过期（TTL）

不写心跳文件。按 `state` 推导 TTL：

| 状态 | TTL | 说明 |
|---|---|---|
| `thinking` / `tool` / `reading` | 30 分钟 | 超时视为卡住/崩溃，不再展示 |
| `waiting` / `attention` / `error` | 24 小时 | 需要用户处理，保留久一点 |
| `celebrate` | 5 分钟 | 一次性庆祝 |
| `idle` | 5 分钟 | 空闲/会话结束；之后自然消失 |

- `now - ts > ttl` → 过期，不再参与聚合；下次扫描可删除。
- `ts` 在未来超过 5 分钟 → 视为坏数据，跳过并记录 debug 日志。
- `SessionEnd` 写 `idle` + “晚安～”；5 分钟后自然消失。

### 1.3 损坏容忍

读取方必须容忍：

- 缺字段、未知字段；
- 半截 JSON；
- 旧格式（无 `v`）；
- 未知 `state`（回退 `idle` 并记录 debug）；
- 超大文件（建议 > 64KB 跳过）。

坏文件不能导致 pet 崩溃或阻塞其他会话。

---

## 2. Schema

```json
{
  "v": 1,
  "session": "abc123",
  "agent": "claude-code",
  "state": "tool",
  "text": "在改 register.ts",
  "project": "claude-desk-pet",
  "ts": 1760000005.2,
  "sound": null,
  "attention": false
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `v` | int | 是 | — | 协议版本，当前 `1`；旧格式无此字段时按 `1` 读 |
| `session` | string | 是 | — | Claude Code 会话 id；旧格式缺失时用文件名补 |
| `agent` | string | 否 | `claude-code` | 未来多 Agent 用；当前固定 |
| `state` | enum | 是 | — | 见 §3 |
| `text` | string | 否 | `""` | 气泡文案；≤ 60 字符；不含 prompt/完整命令 |
| `project` | string | 否 | `""` | 项目名（basename）；隐私模式可空 |
| `ts` | float | 是 | — | Unix 秒；写入方时钟 |
| `sound` | string/null | 否 | `null` | `done` / `error` / `null` |
| `attention` | bool | 否 | `false` | 是否需要用户操作；缺省由 state 推导 |

**明确不写**

- `cwd` 完整路径；
- prompt / 回复正文；
- 完整命令 / 密钥 / URL 参数；
- token / model / context（留在插件 store）；
- 文件 mtime、pid、端口等运行时信息。

> 需要调试时，用 `/pet doctor` 和日志，不靠状态文件。

---

## 3. 状态

只保留 8 个核心状态。新状态必须同时有动画/文案/测试，否则不许加。

| 状态 | 含义 | 默认 attention | 默认 TTL | 立绘回退 |
|---|---|---|---|---|
| `idle` | 没有活跃工作 | 否 | 5m | `smile` |
| `thinking` | 模型思考中 | 否 | 30m | `smile-closed` |
| `tool` | 正在跑工具/改文件 | 否 | 30m | `typing` |
| `reading` | 读文件/搜索/上网 | 否 | 30m | `notes` |
| `waiting` | 轮到你说话 | 是 | 24h | `knock` |
| `attention` | 需要你看一下（通知/elicitation/权限提醒） | 是 | 24h | `knock` |
| `celebrate` | 长任务完成 | 否 | 5m | `confetti` |
| `error` | 出错/失败 | 是 | 24h | `panic` |

**兼容旧行为**

- `aborted` → 映射到 `error`，文案“被打断了…”。
- `stone`（连续 3 次错误石化）是**渲染层彩蛋**，不是协议状态；渲染层看到连续 `error` 自行触发。
- `sleeping` 不是协议状态；`waiting` 超过 10 分钟由渲染层显示 `idle`/发呆。
- `permission` 不是协议状态；权限提醒用 `attention`，审批走 [权限契约](permission.md)。

**优先级**（数值越大越优先）

| 状态 | priority |
|---|---|
| `attention` | 90 |
| `error` | 80 |
| `waiting` | 70 |
| `celebrate` | 50 |
| `tool` / `reading` | 40 |
| `thinking` | 30 |
| `idle` | 0 |

---

## 4. 事件映射

### 4.1 核心 8 事件

| 事件 | 状态 | attention | 气泡示例 | 备注 |
|---|---|---|---|---|
| `SessionStart` | `waiting` | `false` | 我来啦～ | 启动 pet、写会话文件；只是打招呼，不算“需要你” |
| `UserPromptSubmit` | `thinking` | `false` | 思考中 | 新一轮开始；清空连续错误计数 |
| `PreToolUse` | `tool` / `reading` | `false` | 在改 x.ts / 在读 x.ts | 按工具名分流 |
| `PostToolUse` | `thinking` | `false` | 思考中 | 工具成功返回 |
| `PostToolUseFailure` | `error` | `true` | 出错了… | 连续 3 次由渲染层触发石化彩蛋 |
| `Stop` | `waiting` / `celebrate` | `true` / `false` | 轮到你啦！ | 正常结束；> 3 分钟大活用 `celebrate` |
| `Notification` | `attention` | `true` | 需要你看一下 | 非阻塞；权限提醒也走这里 |
| `SessionEnd` | `idle` | `false` | 晚安～ | TTL 5 分钟 |

> `attention` 字段由写入方显式设置，覆盖状态默认值；不要依赖读取方猜。`SessionStart` 的 `waiting` 只是问候，`attention=false`，否则会把“刚打开”算成 missed needs-input。

### 4.2 可选事件（只改文案，不加状态）

| 事件 | 处理 |
|---|---|
| `PermissionRequest` | v1 写 `attention` + 通知；v2 走 bridge（见权限 spec） |
| `Elicitation` | `attention`，文案“Claude 在问你” |
| `StopFailure` | `error`，文案“出错了，来看看？” |
| `SubagentStart` | 保持当前状态，文案“派小助手开工” |
| `SubagentStop` | 保持当前状态，文案“小助手回来了” |
| `PreCompact` | 保持当前状态，文案“在整理上下文” |
| `PostCompact` | 保持当前状态，文案“整理好了” |

> 不为 `Subagent`/`Compact` 新增状态或立绘；用文案表达，避免“状态很多但用户看不懂”。

### 4.3 工具 → 状态/文案

| 工具 | 状态 | 文案 |
|---|---|---|
| `Bash` / `PowerShell` | `tool` | 在跑命令… |
| `Edit` / `Write` | `tool` | 在改 `<basename>` / 在改文件… |
| `Read` | `reading` | 在读 `<basename>` / 在翻文件… |
| `Grep` / `Glob` | `reading` | 在找东西… |
| `WebFetch` / `WebSearch` | `reading` | 在上网查… |
| `Agent` | 当前状态 | 派小助手干活中 |
| `mcp__*` | `tool` | 在用 `<server>` |
| 其他 | `tool` | 在用 `<tool>` |

**文案规则**

- 只显示 basename；不显示完整路径。
- 命令类不显示参数/完整命令；统一“在跑命令…”。
- 最长 60 字符；超出截断加 `…`。
- 隐私模式：项目名显示“项目”，文件名显示“文件”。

---

## 5. 多会话聚合

### 5.1 扫描

```python
def live_sessions(now):
    for path in glob("sessions/*.json"):
        data = read_json(path)
        if not valid(data): continue
        if expired(data, now): continue
        yield Session.from_dict(data)
```

- 不按 mtime 选主会话；mtime 只用于“文件是否变化”。
- 过期文件可删除；删除失败只记 debug。
- 同一 session 多写入方：最后写入胜出；不合并。

### 5.2 选主会话

```python
def pick_main(sessions):
    live = [s for s in sessions if not s.expired]
    if not live:
        return None
    return max(
        live,
        key=lambda s: (
            s.attention,          # True > False
            PRIORITY[s.state],    # 高优先级
            s.ts,                 # 新事件优先
            s.session,            # 确定性
        ),
    )
```

- 不做锁定/逐会话聚焦（M3 不做）。
- 不做复杂 tie-break；规则固定、可测试。

### 5.3 展示

- 单会话：气泡 = 主会话 `text`。
- 多会话：气泡 = 主会话 `text` + ` · N 个会话`；有需要处理的再加 ` · M 个等你`。
- 菜单：按 `(attention, priority, ts)` 排序；每项显示 `project`、状态、已运行时长。
- 点击菜单项：切换主会话；尝试聚焦对应终端，失败则显示项目路径。

**示例**

```text
在改 register.ts · 3 个会话 · 2 个等你
```

---

## 6. 兼容与迁移

- **旧格式**（无 `v`）：

```json
{"state":"tool","text":"在改 x.ts","project":"foo","ts":1760000000,"sound":null}
```

读取方按 `v=1` 处理：`agent` 默认 `claude-code`，`attention` 按状态推导，`session` 缺失时用文件名（不含 `.json`）。

- **新字段**：只能加可选字段；读取方忽略未知字段；写入方不删旧字段。
- **破坏性变更**：升 `v`；读取方至少支持当前和上一个 major；写迁移说明。
- **schema 文件**：M1 建立 `contracts/state.schema.json`；TS/Python 的枚举和字段必须通过契约测试对齐。

---

## 7. 隐私

- 不写 prompt、回复、完整命令、`cwd`、密钥、URL 参数。
- `project` 只写 basename；`text` 只写 basename/短文案。
- 隐私模式（设置）：`project` 置空或“项目”；文件名替换为“文件”。
- 状态文件权限 `0600`；日志不记录 `text` 全文（debug 级别也尽量避免）。
- 不联网；状态文件只在本机。

---

## 8. 示例

### 8.1 正常

```json
{
  "v": 1,
  "session": "abc123",
  "agent": "claude-code",
  "state": "tool",
  "text": "在改 register.ts",
  "project": "claude-desk-pet",
  "ts": 1760000005.2,
  "sound": null,
  "attention": false
}
```

### 8.2 需要用户

```json
{
  "v": 1,
  "session": "abc123",
  "agent": "claude-code",
  "state": "waiting",
  "text": "轮到你啦！",
  "project": "claude-desk-pet",
  "ts": 1760000010.0,
  "sound": "done",
  "attention": true
}
```

### 8.3 坏数据（跳过）

```json
{"state": "tool"}
```

缺 `ts`/`session` → 不参与聚合；记录 debug。

### 8.4 过期（跳过）

`state=tool` 且 `now - ts > 1800` → 跳过。

---

## 9. 测试清单

- [ ] 正常/旧格式/缺字段/坏 JSON/未知状态。
- [ ] TTL：thinking 30m、waiting 24h、celebrate 5m、SessionEnd 5m。
- [ ] 未来时间戳 > 5m 跳过。
- [ ] 多会话优先级：attention > error > waiting > celebrate > tool > thinking > idle。
- [ ] `SessionStart` attention=false；`Stop` waiting=true、celebrate=false。
- [ ] 同优先级按 `ts`，再按 `session` 确定性。
- [ ] 气泡计数：3 会话 2 个 attention → “3 个会话 · 2 个等你”。
- [ ] 隐私模式不输出项目名/文件名。
- [ ] 文件权限 `0600`、目录 `0700`。
- [ ] 原子写：并发写不产生半截 JSON。
