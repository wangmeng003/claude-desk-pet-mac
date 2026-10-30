# 更新记录

## Unreleased

- 全面代码审查，修掉 14 个真 bug（每个都补了回归测试）：
  - **坏数据不再搞崩桌宠**：状态文件里的 `text`/`project` 不是字符串、`state` 是 list（不可哈希）时，
    以前会一路流到渲染层抛异常（Windows 上 `draw_bubble` 抛错还会让 poll 轮询彻底停摆，桌宠永远冻住）。
    现在在 core 边界就回退成默认值
  - **设置不再丢**：`save_settings` 改成同目录临时文件 + `os.replace` 原子写（以前写一半被 kill 就留下半截 JSON，
    下次启动设置全丢）；`load_settings` 校验 JSON 是不是对象（是数组时以前写设置直接 TypeError，桌宠起不来）
  - **`--shot` 不再把截图路径当运行目录**：以前 `pet_mac.py --shot /tmp/x.png` 会把 `/tmp/x.png` 当成运行目录，
    桌宠去 `/tmp/x.png/sessions` 找状态文件、还用不上真实设置。新增 `pet/core/cli_args.py` 统一解析
  - **`--shot` 截到的是桌宠自己**：透明窗口没有后备存储，`CGWindowListCreateImage` 抓回来的是背后的屏幕
    （实测抓到终端），截图等于测了个寂寞。改成 `cacheDisplay` 渲染 view 自己
  - **Windows poll 循环不再一错就死**：`root.after` 在函数末尾，中途抛错就永远不再调度
  - **工具不会被执行两遍**：`tool.call` 处理器在 `next(e)` 之后抛错时，兜底的 catch 会再跑一次 `next(e)`
  - **venv 路径跟着运行目录走**：launcher 里写死 `~/.claude/desk-pet/venv`，换运行目录就拿错解释器
  - **项目会话数不再少算**：`ensureSessionRecord` 现在一定会建出项目记录
  - 状态文件 `ts` 改成 Unix 秒（状态协议 §2 写的是秒，之前写的是毫秒；将来按 ts 算 TTL 会把文件当未来时间戳丢掉）
  - 立绘缺失/损坏不再让桌宠起不来；settings 里的坐标是 None/字符串时回退默认位置
  - 记异常本身不再抛异常（AppKit 会为 drawRect 里的异常杀进程）
  - **气泡不再被长文案撑破**：气泡宽度被窗口卡死，文件名一长文字就溢出到气泡外面。
    mac/Windows 都改成逐字截到放得下为止（加省略号）；文案本身按状态协议 §4.3 截到 60 字符
- hooks 单测从 12 个增加到 22 个（新增 launcher 运行时解析、state_writer 状态文件 schema）

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
