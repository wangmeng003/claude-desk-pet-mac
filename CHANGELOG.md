# 更新记录

## Unreleased

- M1 Step 3：`hooks/register.ts` 按职责拆为 `context`（每会话一个 SessionContext，收拢模块级可变变量）、`state`（工具名→状态/文案纯映射）、`state_writer`（状态文件写入）、`accounting`（token/花费记账）、`statusline`（状态栏与统计文本格式化）、`launcher`（venv/启动）、`commands`（/pet、/token-stats 用例）；register 只注册事件与命令。行为不变，tsc 零配置差异通过
- hooks 引入 node:test 单测（12 个）：state 映射、accounting 累计/花费增量钳制、statusline 缩写与命中率；CI ts job 增加单测步，node.d.ts 提供 node:test/assert 最小类型 shim
- M1 Step 2：抽出 `pet/platforms/mac/`（window=PetView 绘制/拖拽/窗口几何、menu=右键菜单、focus=进程/前台检测、notify=提示音），pet_mac.py 变为 composition root（settings/core/platforms 组装 + poll/tick/watch_* 编排）；golden 测试零改动全绿，--shot 冒烟新旧渲染逐像素等价
- 包名用复数 `platforms`：原名 `platform` 会遮蔽标准库 platform（pytest 启动即缓存标准库模块，`import platform.mac` 必失败），ARCHITECTURE/ROADMAP 引用已同步
- M1 Step 1：抽出 `pet/core/`（models/state_reader/sessions/view_model，纯 stdlib），pet_mac.py / pet.pyw 改为薄壳调用 core；行为不变，27 个 golden 测试原样全绿，新增 16 个 core 纯函数单测
- CI 增加 core 边界检查：pet/core 出现 AppKit/tkinter/PIL/urllib 等直接失败
- M1 Step 0：characterization tests + CI（pytest 全平台 golden 测试锁定 sessions 读取/poll 映射/视图规则；ruff、mypy、tsc --noEmit；macOS/Windows 双平台 CI）
- pet_mac.py / pet.pyw 零行为变更接缝：import 时绑定端口锁改为 `acquire_lock()`，main 启动时获取

## 0.1.3

- macOS 首次运行自动创建 `~/.claude/desk-pet/venv` 并安装 Pillow + pyobjc，不再需要手动准备环境
- 新增 `/pet setup`：安装失败或环境损坏时可强制重试
- 环境安装失败时在状态栏/通知栏提示，并写入 `~/.claude/desk-pet/setup.log`
- README 补充 macOS 安装说明和「桌宠没出现？」排错步骤

## 0.1.2

- 市场改名 `desk-pet-mac`，避免与上游市场名冲突
- 版本号升到 0.1.2，补 `author` 字段
- README 安装命令改为 `wangmeng003/claude-desk-pet-mac`

## 0.1.1

- 去掉 `plugin.json` 的 `types` 字段，避免旧版 Claude Code 同步市场时跳过整个插件

## 0.1.0

- 首次发布：桌宠悬浮窗、Token 状态栏、完成/出错提示音
- `/token-stats`、`/pet` 命令
