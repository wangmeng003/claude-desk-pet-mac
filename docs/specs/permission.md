# 权限提醒与审批

> 状态：阶段 1 已定；阶段 2 以 M0 spike 为条件  
> 关联：[路线图](../ROADMAP.md) · [状态协议](state.md) · [架构](../ARCHITECTURE.md)

## 0. 结论

- **阶段 1（默认交付）**：权限请求 → `attention` 状态 + 原生通知 + 声音 + 点击聚焦终端。**不阻塞、不审批**。
- **阶段 2（条件交付）**：只有 M0 spike 证明 hook 能稳定返回 allow/deny，才做**单请求卡片**。
- 任何情况下都 **fail-open**：bridge 不可用、超时、宠物挂掉、坏 JSON → 回退终端原生提示，**绝不自动 allow**。
- 阶段 2 **不做**：审批队列、全局热键、审计日志默认开启、远程审批、LLM 风险判断。

---

## 1. 目标与非目标

### 1.1 目标

1. 用户离开终端时，不会错过权限请求。
2. 用户能在不切窗口的情况下看到“谁在等、等什么”。
3. 审批路径比“回到终端找窗口”更快，但不降低安全性。
4. 任何一环失败都不阻塞 Claude。

### 1.2 非目标（阶段 2 MVP）

- 批量审批/队列。
- 全局快捷键（后续可选，高风险命令永久禁用）。
- 远程审批（Telegram/飞书等）。
- 自动 allow / 规则自动放行。
- 完整命令审计/落盘。
- LLM 判断命令是否危险。

---

## 2. 分阶段

| 阶段 | 交付 | 前置条件 | 失败时 |
|---|---|---|---|
| **P1 通知** | `attention` + 原生通知 + 声音 + 点击聚焦 | 能收到 `PermissionRequest` 或 `Notification` | 仅气泡，不阻塞 |
| **P2 卡片** | 单请求 Allow/Deny/回退终端 | M0 spike 通过 + 10 人可用性测试 | 回退 P1 |

**P2 启动门槛**

- hook 能稳定收到权限事件，且能返回 `allow` / `deny` / `ask`。
- hook 超时/崩溃时，终端原生提示仍出现，不被卡住。
- 连续 5 个请求不丢、不串会话。
- 测试中零误放行。
- 用户能在 5 秒内理解卡片并做出决策（可用性测试）。

---

## 3. M0 spike

### 3.1 要回答的问题

| # | 问题 | 影响 |
|---|---|---|
| 1 | 插件引擎是否暴露 `PermissionRequest`？字段是什么？ | 能不能做 P2 |
| 2 | 原生 hooks 的输入/输出 schema 是什么？返回码/JSON 字段？ | 客户端实现 |
| 3 | hook 能否阻塞等待用户？超时行为？ | 卡片是否可行 |
| 4 | 多个会话同时请求时，hook 是串行还是并发？ | 是否需要队列/忙时回退 |
| 5 | hook 跑在什么 shell/PATH？绝对路径是否可靠？ | 启动/依赖 |
| 6 | hook 崩溃/超时/非法输出时，Claude 是 fail-open 还是 fail-closed？ | 安全底线 |
| 7 | macOS/Windows 行为是否一致？ | 双平台 |

### 3.2 测试矩阵

| 场景 | macOS | Windows | 预期 |
|---|---|---|---|
| 允许一次 Bash | ✅ | ✅ | 返回 allow，命令执行 |
| 拒绝一次 Bash | ✅ | ✅ | 返回 deny，命令不执行 |
| 超时（不操作） | ✅ | ✅ | 回退终端/ask，不挂死 |
| 宠物未启动 | ✅ | ✅ | 终端原生提示 |
| 宠物中途被杀 | ✅ | ✅ | 终端原生提示 |
| 两个会话同时请求 | ✅ | ✅ | 不串会话；忙时 ask |
| 非法 JSON/空输入 | ✅ | ✅ | 不崩溃；ask |
| 长命令/Unicode | ✅ | ✅ | 卡片显示正常；不截断关键信息 |

### 3.3 交付物

- `docs/adr/0001-permission-hook.md`：结论、测试记录、go/no-go。
- 最小 spike 脚本（不合并到主分支，或放 `spikes/` 并标注）。
- 失败路径记录：超时、崩溃、非法输出、宠物挂掉。

### 3.4 No-go 处理

- 只做 P1：`attention` + 通知 + 聚焦。
- 关闭 P2 issue；在路线图标注“权限卡片暂不做，等 hook 能力变化”。
- 不为了做卡片去改 Claude Code 本体/注入/猴子补丁。

---

## 4. P1：通知 + 聚焦

### 4.1 流程

```text
Claude Code
  │ PermissionRequest / Notification
  ▼
hook (thin)
  │ 写 state=attention, attention=true
  ▼
pet
  ├─ 气泡：“等你确认”
  ├─ 原生通知：项目 + 工具 + 摘要
  ├─ 声音（可关）
  └─ 点击 → 聚焦终端
```

### 4.2 规则

- **不阻塞**：P1 不等待用户，不返回决策；Claude 继续走原生权限流程。
- **去重**：同一 `session + tool + summary` 2 秒内只通知一次。
- **内容**：只显示项目名、工具名、脱敏摘要（basename/命令类别）；不显示完整命令、密钥、URL 参数。
- **勿扰**：只保留气泡/角标，不弹横幅、不响铃；用户手动查看。
- **聚焦失败**：通知里显示项目路径 + “请手动切换”；不反复弹窗。
- **权限请求优先**：同一时刻有完成通知和权限通知，权限优先。

### 4.3 验收

- 触发 Bash 权限请求，桌面出现通知/气泡；点击能聚焦终端。
- 连续 5 个请求，不丢、不刷屏。
- 宠物未启动/被杀，Claude 原生提示正常。
- 勿扰模式下无横幅/声音，但气泡仍在。
- macOS/Windows 均可用。

---

## 5. P2：单请求卡片

### 5.1 流程

```text
Claude Code
  │ PermissionRequest hook
  ▼
permission_client
  │ POST http://127.0.0.1:<port>/v1/permission
  │ Authorization: Bearer <token>
  ▼
pet bridge
  │ 状态机：pending → user decision
  ▼
用户：Allow / Deny / 回退终端
  │
  ▼
HTTP response: {"decision":"allow"|"deny"|"ask"}
  │
  ▼
permission_client → Claude Code
  ├─ allow/deny：按决策继续
  └─ ask/超时/桥不可用：终端原生提示
```

### 5.2 bridge 文件

`~/.claude/desk-pet/bridge.json`，权限 `0600`：

```json
{
  "v": 1,
  "port": 49321,
  "token": "random-per-run-token",
  "pid": 12345,
  "started_at": 1760000000.0
}
```

- 只绑 `127.0.0.1`；随机端口；每次运行重新生成 token。
- pet 启动时写，退出时删除；文件不存在/过期 → 客户端立即 `ask`。
- token 不写日志；不通过环境变量传给子进程。

### 5.3 API

#### `POST /v1/permission`

请求：

```json
{
  "v": 1,
  "id": "uuid",
  "session": "abc123",
  "tool": "Bash",
  "project": "claude-desk-pet",
  "summary": "rm -rf build",
  "detail": "rm -rf build",
  "risk": "high",
  "ts": 1760000005.2
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `v` | 是 | 契约版本 |
| `id` | 是 | 请求 id；用于去重/日志 |
| `session` | 是 | 会话 id |
| `tool` | 是 | 工具名 |
| `project` | 否 | 项目名；隐私模式可空 |
| `summary` | 是 | 卡片摘要；≤ 200 字符 |
| `detail` | 否 | 完整命令/参数；仅本机内存，不落盘、不写日志、不联网；卡片可展开 |
| `risk` | 是 | `low` / `medium` / `high` |
| `ts` | 是 | Unix 秒 |

> `summary` 是脱敏/截断后的摘要；`detail` 只在本机内存和卡片中存在，用户关闭卡片后丢弃。状态文件和日志永远不写 `detail`。

响应：

```json
{"decision": "allow", "reason": "user"}
```

| 字段 | 说明 |
|---|---|
| `decision` | `allow` / `deny` / `ask` |
| `reason` | 可选：`user` / `timeout` / `busy` / `error` |

状态码：

| 码 | 含义 | 客户端处理 |
|---|---|---|
| 200 | 有决策 | 按 `decision` |
| 400 | 坏请求 | `ask` |
| 401 | token 错 | `ask` |
| 409 | 忙/重复 | `ask` |
| 500 | 内部错误 | `ask` |
| 超时 | 无响应 | `ask` |

#### `GET /v1/health`

```json
{"ok": true, "v": 1, "pid": 12345}
```

用于客户端快速判断 bridge 是否可用；不返回敏感信息。与 `/v1/permission` 一样要求 `Authorization: Bearer <token>`。

### 5.4 状态机

```text
idle → pending → allowed
              ├→ denied
              ├→ ask (timeout/busy/error)
              └→ ask (pet exit/connection lost)
```

- **同一时间只处理一个请求**；忙时立即返回 `ask`，不排队。
- **超时**：bridge 等待 600 秒；客户端 HTTP 超时 610 秒；超时返回 `ask`。
- **重复 id**：返回 `409`；不重复弹卡。
- **宠物退出**：所有 pending 立即 `ask`；客户端回退终端。
- **用户关闭卡片**：视为 `ask`，不视为 deny。
- **高风险**：默认焦点在“回退终端”；禁用全局快捷键（`Esc` 仍可回退）；Allow 需二次确认。

### 5.5 卡片 UI

- 标题：`Claude 需要你确认`
- 内容：项目、工具、摘要、风险徽标。
- 展开：完整命令/参数（仅本地显示，不写日志）。
- 按钮：`允许` / `拒绝` / `回退终端`。
- 倒计时：剩余秒数；超时自动回退。
- 高风险：红色徽标 + “这是破坏性操作” + 二次确认。
- 键盘：`Esc` = 回退终端；`Enter` 默认焦点在“回退终端”（高风险）或“允许”（低风险，可选）。
- 无全局热键（P2 MVP）。

### 5.6 风险规则

只做**提示**，不做自动拒绝/自动允许。

| 级别 | 例子 | UI 行为 |
|---|---|---|
| `high` | `rm -rf`、`sudo`、`curl ... \| sh`、`chmod 777`、写 `.ssh`/`.env`/密钥、`git push --force` | 红色警告；默认回退终端；二次确认；禁用全局快捷键 |
| `medium` | 写项目外路径、`git reset --hard`、安装全局包、网络下载 | 黄色提示；正常按钮 |
| `low` | 读文件、搜索、项目内编辑 | 无额外提示 |

规则实现为纯函数，输入 `tool + summary/detail`，输出 `risk`；可单测、可配置、可关闭。**不用 LLM。**

---

## 6. 安全与威胁模型

| 威胁 | 影响 | 缓解 |
|---|---|---|
| 本机其他用户/进程伪造请求 | 诱导用户 allow | 只绑 `127.0.0.1`；per-run token；`bridge.json` `0600`；同用户威胁模型明确写入文档 |
| token 泄漏 | 本地伪造 | 每次运行随机；不写日志；不传子进程；退出删除 |
| 浏览器 CSRF | 网页调用 localhost | 要求 `Authorization` + `Content-Type: application/json`；拒绝 `Origin` 非空/非本地；不设 CORS |
| 重放 | 重复审批 | `id` 去重；一次性 pending；时间戳校验 |
| 请求体攻击 | 内存/解析崩溃 | body ≤ 64KB；JSON 深度/字段长度限制；超限 400 |
| 命令注入 UI | 卡片渲染异常 | 只作文本渲染；不执行/不解析 HTML；截断显示 |
| 通知泄漏 | 锁屏/录屏暴露命令 | 通知只显示项目/工具/摘要；完整命令只在卡片展开 |
| 宠物挂掉 | 阻塞 Claude | 客户端超时 + `ask`；bridge 不存在立即 `ask` |
| 误点 Allow | 危险操作 | 高风险二次确认；默认回退；无全局热键；审计可选 |

**明确边界**

- 不防御同用户恶意进程（它能读 `bridge.json`）；这是本地工具的可接受威胁模型，文档写清。
- 不暴露到局域网；不做远程 API。
- 不自动 allow；`allow` 只能由用户点击产生。

---

## 7. 客户端实现要求

- 位置：`hooks/permission_client.*`（语言按 hook 机制定：插件引擎用 TS，原生 hook 可用 Python）。
- 职责：读 hook 输入 → 校验 → POST bridge → 解析响应 → 返回 Claude Code 期望的格式。
- 超时：HTTP 610 秒；连接超时 1 秒；读超时按剩余时间。
- 失败：任何异常 → `ask`；记录 debug 日志（不含完整命令）。
- 绝对路径：hook 跑在非登录 shell，启动脚本/解释器用绝对路径；PATH 只作兜底。
- 版本适配：按 Claude Code 版本/字段做兼容；不认识 → `ask`。
- 不缓存 allow；每次请求都问用户。

---

## 8. 测试

### 8.1 单元

- 风险规则：high/medium/low 边界；Unicode/长命令；空输入。
- 状态机：pending → allowed/denied/ask；重复 id；忙时。
- 去重：同 session/tool/summary 2 秒内只通知一次。

### 8.2 契约/集成

- bridge 鉴权：无 token/错 token → 401 → 客户端 `ask`。
- 超时：bridge 不回 → 客户端 `ask`；不挂死。
- 忙时：第二个请求 → 409 → `ask`。
- 宠物被杀：pending → `ask`；终端原生提示。
- 非法 JSON/超大 body → 400；不崩溃。
- 两个会话并发：不串 session；各自回退。
- 高风险：二次确认；默认回退；快捷键禁用。

### 8.3 手动

- macOS/Windows 各触发 5 次权限请求。
- 锁屏/勿扰/多显示器下的通知行为。
- 点击通知聚焦终端；聚焦失败提示。
- 长命令展开/滚动/复制。

---

## 9. Kill criteria

- spike 失败/行为不稳定 → 只做 P1。
- 任何误放行 → 停止 P2，重新设计。
- 卡片让用户更慢/更困惑（可用性测试 < 80% 能在 5 秒内理解）→ 回退 P1。
- 维护成本过高（hook 版本频繁变化）→ 只保留通知，不承诺审批。

---

## 10. 开放问题

| 问题 | 何时解决 |
|---|---|
| 插件引擎 vs 原生 hooks 的权限事件差异 | M0 spike |
| Windows 终端聚焦 API 可靠性 | M1 |
| 完整命令是否应显示/如何脱敏 | P2 设计前 |
| 高风险命令清单是否可配置 | P2 后 |
| 是否支持全局热键 | P2 后再评估；高风险永久禁用 |
| 远程审批 | v1.x Explore |
