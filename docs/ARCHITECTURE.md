# 架构与代码质量约定

> 状态：v1.0 · 最后更新：2026-11-01  
> 适用版本：v0.2.0 起  
> 关联：[路线图](ROADMAP.md) · [状态协议](specs/state.md) · [权限](specs/permission.md) · [主题](specs/theme.md)

## 0. 一句话

**核心纯函数 + 薄适配层 + 版本化契约 + 小步重构。**

功能可以长，但边界不能烂。每个新功能必须先回答“它属于哪个模块、改哪个契约、失败时谁兜底”，再写代码。

---

## 1. 设计原则

1. **依赖向内**：纯逻辑（`models` / `sessions` / `view_model`）不 import 平台、UI、网络、文件系统；`state_reader` / `settings` 是 core 的 I/O 边界，允许 stdlib 文件读写，但不允许平台/网络。平台差异在 adapter。
2. **端口/适配器**：core 定义接口（port），平台实现 adapter；测试用 fake adapter。
3. **契约优先**：状态、权限、主题、外部 Agent 四个边界；每个契约版本化、有 schema、有契约测试。
4. **薄入口**：`hooks/register.ts`、`pet_mac.py`、`pet.pyw` 只做组装和生命周期，不做业务判断。
5. **失败隔离**：边界 fail-open；core 抛领域错误；不静默吞异常。
6. **单一职责**：一个模块一个变化原因；god object 必须拆，不靠注释解释。
7. **小步重构**：strangler pattern；行为不变；重构与功能分开 PR。
8. **最简技术**：stdlib 优先；新依赖要 ADR；core 不引入 Electron/Node 常驻运行时。
9. **可诊断**：结构化日志、`/pet doctor`、错误上下文；用户能复制诊断信息。
10. **规则三**：第三次重复才抽象；两个真实适配器才做 SDK；不要为想象中的扩展写框架。

---

## 2. 目标架构

```text
Claude Code
  └─ plugin hooks (TypeScript, thin)
       ├─ EventAdapter     事件 → 领域事件
       ├─ StateWriter      领域事件 → sessions/*.json
       ├─ Accounting       token/cost 记账 → plugin store
       ├─ Launcher         RuntimeResolver → pet process
       ├─ StatusLine       状态栏文本
       └─ PermissionClient 权限 hook → bridge（可选）

Pet runtime (Python)
  ├─ StateReader       读/校验 sessions/*.json
  ├─ SessionAggregator 多会话、TTL、优先级
  ├─ ViewModel         主会话、文案、气泡、菜单数据
  ├─ Renderer          平台窗口/绘制/动画
  ├─ Notifier          原生通知/声音/Dock/任务栏
  ├─ Tray              菜单栏/托盘（macOS 先行）
  ├─ ThemeLoader       主题校验/加载
  ├─ BridgeServer      本地 HTTP（权限/状态 API）
  └─ PermissionController 权限决策 → ViewModel/Renderer

Optional / Explore
  ├─ Dashboard         读 ~/.claude JSONL，独立模块/进程
  └─ ControlCenter     独立 UI，通过 state/bridge API 读数据
```

**箭头规则**

- Renderer 不做网络。
- Bridge 不做绘制。
- Theme 不认识 XP。
- Dashboard 不被 pet 进程 import。
- ControlCenter 不 import pet 内部代码，只走 API/schema。

---

## 3. 模块边界

### 3.1 TypeScript hooks

| 模块 | 负责 | 不负责 | 允许依赖 |
|---|---|---|---|
| `hooks/register.ts` | 组合根：注册事件/命令，创建 session context | 状态映射、记账、启动细节 | 下面所有模块 + engine API |
| `hooks/state.ts` | 事件 → 状态 DTO；工具名 → 文案 | 写文件、通知、UI | 纯函数 + 类型 |
| `hooks/state_writer.ts` | 原子写 `sessions/*.json` | 决定状态 | engine fs、state 类型 |
| `hooks/accounting.ts` | token/cost 累计 | 状态、UI | engine store |
| `hooks/launcher.ts` | 运行时解析、启动、健康检查 | 渲染、权限 | engine process/env |
| `hooks/statusline.ts` | 状态栏字符串 | 状态写、启动 | accounting DTO |
| `hooks/commands.ts` | `/pet`、`/token-stats` 的用例编排 | 底层实现 | 上面模块 |
| `hooks/permission_client.*` | hook ↔ bridge 传输；失败返回 `ask` | UI 决策、风险判断 | bridge 契约 |

> `register.ts` 目前 328 行、6 个职责。M1 先拆成 `state` / `accounting` / `launcher` / `statusline` / `commands`，`register.ts` 只保留注册和 session context。

### 3.2 Python pet runtime

| 模块 | 负责 | 不负责 | 允许依赖 |
|---|---|---|---|
| `pet/core/models.py` | State DTO、枚举、错误类型 | 平台 API | 仅 stdlib |
| `pet/core/state_reader.py` | 读文件、解析、校验、TTL | 聚合、渲染 | models、fs |
| `pet/core/sessions.py` | 多会话、优先级、主会话选择 | UI、通知 | models |
| `pet/core/view_model.py` | 主会话 → 气泡/菜单/动画状态 | 平台绘制 | models、sessions |
| `pet/core/settings.py` | 默认值、迁移、校验 | UI 菜单 | models、fs |
| `pet/platforms/mac/window.py` | NSWindow/NSView、绘制、拖拽 | 状态决策 | core view model |
| `pet/platforms/mac/menu.py` | 右键菜单 | 业务逻辑 | core view model |
| `pet/platforms/mac/focus.py` | 前台检测、聚焦 Claude | 状态聚合 | 平台 API |
| `pet/platforms/mac/notify.py` | 通知、声音、Dock | 决策 | 平台 API |
| `pet/platforms/windows/*` | Tk 窗口/菜单/焦点/Toast | 同上 | core view model |
| `pet/runtime/launcher.py` | 运行时解析、单实例、启动 | UI | core settings |
| `pet/runtime/setup.py` | venv/依赖安装 | 状态、UI | stdlib |
| `pet/features/theme.py` | 主题校验/加载 | 渲染细节、XP | core models |
| `pet/bridge/server.py` | HTTP、鉴权、限流 | 绘制 | bridge 契约 |
| `pet/bridge/permission.py` | 权限状态机、超时、fail-open | 绘制/网络 | bridge 契约 |
| `pet_mac.py` / `pet.pyw` | 入口：组装、定时器、启动 | 业务逻辑 | 所有模块 |

### 3.3 依赖矩阵

| from \ to | core | platform | features | bridge | entry |
|---|---|---|---|---|---|
| **core** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **platform** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **features** | ✅ | 仅通过 port | ✅ | ❌ | ❌ |
| **bridge** | ✅ | ❌ | ❌ | ✅ | ❌ |
| **entry** | ✅ | ✅ | ✅ | ✅ | ✅ |

> CI 加一个 import boundary 检查：`pet/core` 下出现 `AppKit`、`tkinter`、`requests`、`urllib` 直接失败。

---

## 4. 契约

### 4.1 四个契约

| 契约 | 方向 | 文档 | 版本策略 |
|---|---|---|---|
| **State** | 插件 → pet | [specs/state.md](specs/state.md) | `v` 字段；只加字段不升版；破坏性变更升 major |
| **Permission** | hook ↔ bridge | [specs/permission.md](specs/permission.md) | `v` 字段；错误码稳定；超时/失败语义写死 |
| **Theme** | 主题包 → pet | [specs/theme.md](specs/theme.md) | `schema` 字段；缺省回退；只允许数据，不执行代码 |
| **Adapter** | 外部 Agent → pet | M3 之后再定义 | 先 CLI/HTTP，不提前做 SDK |

### 4.2 契约规则

- **单一事实来源**：schema 文件 + 契约测试；TS/Python 的枚举/字段必须与 schema 对齐。
- **向后兼容**：读方容忍未知字段、缺字段、半截 JSON；写方不删字段。
- **破坏性变更**：升 `v`、写迁移说明、保留旧读方至少一个 minor。
- **DTO 不泄漏**：core 内部模型不直接跨进程/跨语言；边界用显式 DTO + 映射函数。
- **错误语义**：每个契约写清“失败时调用方怎么做”；权限契约默认 `ask`，不是 `allow`。

### 4.3 状态契约的最小化

状态文件只放 pet 渲染需要的东西：

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

tokens/model/context 留在插件 store，pet 不需要。多会话、XP、看板都不能反过来污染状态协议。

---

## 5. 当前代码 → 目标映射

| 现状 | 问题 | 目标 |
|---|---|---|
| `hooks/register.ts`（328 行） | 状态、记账、venv、启动、命令、状态栏 6 个职责；模块级可变变量 | 拆成 `state` / `accounting` / `launcher` / `statusline` / `commands`；`register.ts` 组合根；每会话一个 context |
| `pet/pet_mac.py`（490 行） | `PetView` 绘制 + `Pet` 窗口/菜单/设置/状态/焦点/生命周期 | `core/*` + `platforms/mac/*`；`pet_mac.py` 只组装 |
| `pet/pet.pyw`（373 行） | 同上，与 macOS 逻辑重复 | `core/*` 复用；`platforms/windows/*` |
| `pet/setup.py`（183 行） | venv/依赖逻辑与 UI 日志耦合 | `pet/runtime/setup.py`；输出结构化结果 |
| `pet/launch.py`（40 行） | 启动逻辑简单但和 hooks 耦合 | `pet/runtime/launcher.py`；hooks 只调用接口 |
| `hooks/hooks.json` | 只有 `register.ts` | 保持入口；内部模块化 |

**兼容要求**

- 插件 manifest、`hooks.json`、README 里的路径保持不变。
- `pet_mac.py` / `pet.pyw` 保留为薄入口；老用户升级不需要改配置。
- 先抽 core，再抽 platform；不要一次性重写。

---

## 6. 增量重构顺序

每一步都是独立 PR，行为不变，测试先绿。**重构 PR 不夹带功能。**

### Step 0：characterization tests（M0–M1 开始）

- 用固定 fixture 覆盖：正常状态、旧格式、缺字段、坏 JSON、过期文件、多会话。
- 对 `sessions` → `view_model` 做 golden 测试：输入 fixture，断言主会话/气泡/菜单。
- 加 CI：`ruff`、`mypy`（增量）、`pytest`、`tsc --noEmit`。

### Step 1：抽 core（M1）

- 新建 `pet/core/models.py`、`state_reader.py`、`sessions.py`、`view_model.py`。
- `pet_mac.py` / `pet.pyw` 改为调用 core；渲染逻辑暂时留在原文件。
- 行为不变；截图/手动冒烟对比。

### Step 2：抽 platform（M1）

- `pet/platforms/mac/window.py`：`PetView` 绘制、拖拽、尺寸。
- `pet/platforms/mac/menu.py`：右键菜单。
- `pet/platforms/mac/focus.py`：前台检测/聚焦。
- `pet/platforms/mac/notify.py`：声音/通知/Dock。
- `pet_mac.py` 变成 composition root：创建 settings、core、platform、定时器。

### Step 3：拆 hooks（M1–M2）

- `state.ts`：纯映射（工具名 → state/text），可单测。
- `state_writer.ts`：原子写、权限、错误日志。
- `accounting.ts`：token/cost；输入输出 DTO。
- `launcher.ts`：runtime resolver、启动、健康检查。
- `statusline.ts`：纯格式化。
- `commands.ts`：`/pet`、`/pet setup`、`/token-stats` 用例。
- `register.ts`：只注册事件/命令，创建 `SessionContext`。

### Step 4：bridge 隔离（M2，条件）

- `pet/bridge/server.py`：HTTP、token、限流、body 限制。
- `pet/bridge/permission.py`：状态机、超时、忙时 `ask`、fail-open。
- Renderer 只接收 `PermissionRequestViewModel`；不 import bridge。
- 契约测试：鉴权、超时、并发/忙、坏 JSON、宠物挂掉。

### Step 5：theme feature（M4）

- `pet/features/theme.py`：加载/校验/映射；core 只认识 `Theme` DTO。
- Renderer 通过 `ThemeRepository` 取图；不直接读主题目录。
- 主题加载失败回退内置皮肤，不崩溃。

### Step 6：Explore 项独立（有触发条件再做）

- Dashboard 独立模块/进程，读 `~/.claude` JSONL；不 import pet runtime。
- ControlCenter 独立包/仓库，只走 state/bridge API。
- XP 作为 `features/xp.py`，只读 accounting 事件；theme 不认识 XP。

---

## 7. 代码规范

### 7.1 Python

- 目标 Python 3.9+（当前 venv/pyobjc 兼容范围）；公共 API 加类型标注，文件头 `from __future__ import annotations`。
- 模型用 `dataclass`/`Enum`；不用裸 dict 在 core 里传递。
- 路径用 `pathlib.Path`；不用字符串拼接路径。
- 禁止模块级可变全局状态；用 `SessionContext` / `PetContext` 显式传递。
- 异常：领域错误继承 `PetError`；边界捕获并记录上下文；禁止 `except: pass`（drawRect 这类平台回调必须记录 traceback）。
- 文件 ≤ 400 行、函数 ≤ 50 行、圈复杂度 ≤ 10（软上限；超限需在 PR 说明理由）。
- `core` 的纯逻辑禁止 import `AppKit`、`tkinter`、`requests`、`urllib`、`subprocess`；`state_reader`/`settings` 只允许 stdlib 文件读写。
- 日志用结构化字段；core 不 `print`；不记录 prompt/完整命令/密钥。

### 7.2 TypeScript

- `strict: true`；边界用 `unknown` + 类型守卫，不用 `any`。
- 事件映射/文案/优先级是纯函数；副作用放 adapter。
- 禁止模块级可变 session 变量；每个 session 一个 context。
- 宠物相关错误不能影响 `next(e)`；边界 catch 并 `$.ui.log`。
- 文件/函数软上限同 Python；复杂分支先抽函数。
- 枚举/字段与状态 schema 对齐；加契约测试，不靠手写注释。

### 7.3 命名与文案

- 状态名小写：`idle`、`thinking`、`tool`、`reading`、`waiting`、`attention`、`celebrate`、`error`。
- 事件名与 Claude Code 保持一致；不要自造同义事件。
- 模块名用名词；函数名用动词；布尔用 `is/has/should`。
- 文案集中管理（`locales/` 或 `copy.ts`），不在绘制代码里散落硬编码。

### 7.4 设置与迁移

- `settings.json` 带 `schema`；默认值集中在一个模块。
- 迁移前备份 `settings.json.bak.<timestamp>`；迁移失败回退旧文件。
- 新设置必须有默认值、UI 开关、文档说明；不能只靠环境变量。
- 环境变量只用于测试/开发覆盖，正式行为走设置。

---

## 8. 测试策略

### 8.1 金字塔

| 层 | 测什么 | 工具 | 频率 |
|---|---|---|---|
| 单元 | 状态解析、聚合、优先级、TTL、view model、风险规则、主题校验 | `pytest` / Vitest | 每次 PR |
| 契约 | state schema、bridge 请求/响应、theme pack、TS/Python 枚举一致性 | schema + fixture | 每次 PR |
| 集成 | 假 hook → 状态文件 → view model；假权限客户端 → bridge → 决策 | `pytest` | 每次 PR |
| 平台冒烟 | macOS `--shot`、Windows 启动、通知 | CI matrix / 手动 | 每版本 |
| 手动 QA | 多显示器、DPI、睡眠唤醒、锁屏、深浅色 | 清单 | 每版本 |

### 8.2 关键 fixture

```text
tests/fixtures/state/
  normal.json
  legacy.json          # 无 v 字段
  missing-fields.json
  malformed.json
  expired.json
  multi-session/
    working.json
    waiting.json
    error.json
tests/fixtures/themes/
  valid-petdex/
  missing-state/
  bad-license/
  path-traversal/
```

### 8.3 原则

- 测 view model，不测像素；截图只做冒烟，不做脆弱快照。
- 坏数据必须覆盖：缺字段、半截 JSON、未来时间戳、超大文件、未知状态。
- core 覆盖率目标 ≥ 80%；不追求整体覆盖率数字。
- 每个 bug fix 先加回归测试，再修。
- 权限相关测试必须覆盖“宠物挂掉/超时/忙时 → 回退终端”，且断言**没有 allow**。

---

## 9. 质量门禁

### 9.1 CI

- `ruff check` + `ruff format --check`
- `mypy`（core 严格，平台层增量）
- `pytest`
- `tsc --noEmit`
- schema/契约测试
- import boundary 检查（core 禁止平台/网络 import）
- 文件大小/复杂度检查（超限 warning，PR 说明）
- macOS + Windows 冒烟（至少启动 + `--shot`/窗口创建）

### 9.2 PR

- 小步：一个 PR 一个关注点；重构 vs 功能分开。
- 描述：问题、改动、测试、风险、回滚、截图/录屏。
- 架构清单：
  - 涉及哪个模块？是否改边界/契约？
  - 失败路径是什么？谁兜底？
  - 是否接触 prompt/命令/路径？隐私影响？
  - 性能预算是否退化？
  - 是否需要 ADR/迁移/文档？
- 权限/隐私相关改动：至少一次自审清单 + 一次他人 review（没有他人时，隔天自审）。

### 9.3 Definition of Done

1. 结果/验收标准可验证。
2. 模块边界正确；没有把逻辑塞进入口/renderer。
3. 契约变更：schema + 迁移 + 契约测试。
4. 失败路径：宠物挂掉/网络失败/坏数据/超时。
5. 隐私/许可证检查。
6. 单测/契约/平台冒烟。
7. 文档/CHANGELOG。
8. 性能预算。
9. 回滚方案。
10. 没有未记录的 TODO/临时开关。

---

## 10. ADR

**位置**：`docs/adr/NNNN-title.md`（M0 建立目录）。

**模板**

```markdown
# NNNN. 标题

- 状态：提议 / 接受 / 废弃 / 被 NNNN 取代
- 日期：YYYY-MM-DD
- 相关：链接

## 背景
要解决什么问题？约束是什么？

## 决策
我们决定做什么？

## 备选方案
考虑过什么？为什么没选？

## 后果
好处、代价、风险、迁移方式。

## 验证
怎么知道这个决策是对的？何时重新评估？
```

**必须写 ADR 的情况**

- 新增运行时依赖/框架。
- 新增或破坏性修改契约/字段。
- 新增进程、端口、后台服务。
- 权限/隐私/安全模型变更。
- 平台分叉（macOS/Windows 行为不一致）。
- 打包/签名/自动更新方案。
- 数据格式/存储位置变更。

ADR 一旦接受不修改；用新 ADR 取代。

---

## 11. 依赖策略

- Python core 只用 stdlib；`Pillow`/`pyobjc` 只出现在 platforms/feature。
- TS hooks 只用 engine API + stdlib/Node 内建；不引入 UI/状态库。
- 新依赖检查：许可证、体积、维护活跃度、安全记录、失败回退、是否可 pin。
- 锁定版本；升级走 PR + 回归测试；不自动合并依赖升级。
- 不 vendoring；必须 vendoring 时记录到 `THIRD_PARTY_NOTICES.md`。
- 可选依赖（主题、看板）不得成为核心启动的硬依赖。

---

## 12. 性能预算

| 指标 | 目标 |
|---|---|
| 闲置 CPU | < 1% |
| 活跃 CPU | < 3% |
| 内存 | < 120MB |
| 启动到首帧 | < 2s |
| 权限 p95 | < 200ms（不含用户思考） |
| 状态轮询 | 250ms |
| 渲染 | 闲置 15fps，活跃 30fps |
| 状态文件数 | 100 个会话内不卡顿 |

- 性能回归阻塞发布；用 Activity Monitor / `ps` / 启动计时记录基线。
- 大文件/大主题不一次性读入内存；JSONL 增量解析。
- 闲置降帧；不可见时停止动画。

---

## 13. 演进规则

- **不提前做 SDK**：至少 2 个真实外部适配器，再抽象 adapter contract。
- **不提前做插件系统**：先 JSON 规则；沙箱化插件是 v2 Explore。
- **不微服务化**：一个 pet 进程 + 可选 bridge；dashboard/control center 才独立。
- **核心不引入 Electron**：工作台可选 Tauri；核心保持 Python/原生。
- **入口稳定**：`pet_mac.py`、`pet.pyw`、`hooks/register.ts` 路径不变；废弃先警告一个 minor。
- **Feature flag**：高风险功能默认关闭；设置里可回退。
- **数据迁移向前**：只向前迁移；迁移前备份；失败回退旧文件。
- **删除代码**：先确认无引用/无用户配置依赖；在 CHANGELOG 写清；不保留“可能有用”的死代码。

---

## 14. 开放问题

| 问题 | 影响 | 何时决定 |
|---|---|---|
| 插件引擎是否暴露 `PermissionRequest` | M2 是否能做卡片 | M0 spike |
| Windows 终端聚焦 API 的可靠性 | 通知点击体验 | M1/M2 |
| Python 3.9 支持期限 | pyobjc/Pillow 版本 | M5 前 |
| macOS universal2 打包可行性 | 分发体积/兼容 | M5 spike |
| 主题素材版权审核流程 | 画廊是否启动 | M4 后 |
| 多会话用户真实占比 | M3 是否启动 | M0 证据 |

---

## 15. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-30 | v1.0 | 初版：模块边界、四个契约、增量重构顺序、代码规范、测试/CI/DoD、ADR、依赖/性能/演进规则 |
