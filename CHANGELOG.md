# 更新记录

## Unreleased

- M2 #15：审批卡片 UI（specs/permission.md §5.5，macOS + Windows）+ 宠物 ↔ 桥接线：
  - `pet/platforms/mac/card.py` / `pet.pyw` 内 `PermissionCard`：项目·工具/摘要/风险徽标/
    展开命令/允许·拒绝·回退终端三键/倒计时；detail 只在卡片内存（可复制不可编辑），
    关窗即丢，全程零落盘（测试锁定）；定高窗口（360×300），展开只是切 hidden
  - 风险分级交互（#14 规则的消费端）：high=红色徽标「高危 · 破坏性操作」+ 默认焦点
    「回退终端」+ 允许需点两次（首点变「确认放行？再点一次」）；Esc 永远=回退终端；
    用户关卡片 = ask（不是 deny）；倒计时 600s，到点桥侧转 ask 并自动关卡片
  - 接线：HTTP 线程只入队（`queue.SimpleQueue`），poll 定时器在主线程 drain——
    弹卡/关卡/倒计时全部主线程，不做跨线程 AppKit 调用；桥侧结束（超时/退出）经
    `on_settled` 通知宠物关掉匹配卡片；卡片窗口随桌宠常驻所有空间
  - 退出修复：macOS 上 `stop:` 无后续事件时打不穿 `app.run()`（实测 macOS 27），
    统一 `quit_app()`（stop + 空事件唤醒）；菜单退出/无会话自动退出原走 `terminate_`
    = `exit(0)`，finally 不执行、bridge.json 泄漏、pending 无人回——全部改走 run() 返回
    路径；SIGTERM 实测：pending → `{"decision":"ask","reason":"error"}`、bridge.json/
    pet.lock 双清
  - 测试：`tests/test_permission_flow.py` 8 项（入队→弹卡、忙时不双卡、决策回桥、
    settled 只关匹配卡、无桥静默、detail 零落盘、倒计时文案、默认焦点）；E2E：
    卡片窗口真弹出（CGWindowList 两窗）+ SIGTERM 优雅退出
- M2 #12：权限客户端 `hooks/permission_client.mjs`（原生 PermissionRequest hook → bridge，
  specs §5.1/§7，ADR-0001）：零依赖 .mjs（Claude Code 自带 node，双平台同一条命令）；
  入参映射（prompt_id→id、description/command→summary、完整命令→detail、cwd basename→project、
  隐私模式不带项目名）；bridge.json 缺失/坏 JSON/pid 死/HTTP 失败/非 2xx/超时 → 一律输出
  无决策空 `{}`（回退终端原生提示，不占其他 hook 的决策位）；只有 bridge 的 allow/deny
  才产生真决策；绝不自动 allow、不缓存 allow、被超时杀掉=进程死即 fail-open；debug 日志只记
  错误类别不落命令内容。CI hooks 单测收编 `*.test.mjs`。真实 claude 矩阵 5/5：allow 执行 /
  deny 拦截且消息传给模型 / 桥被杀（死 pid 识破）/ 无 bridge.json / hook 超时 15s 杀掉——
  全部零误放行
- M2 #13：权限审批桥（specs/permission.md §5.2-5.4）：
  - `pet/bridge/permission.py` 状态机 idle → pending → allowed/denied/ask：
    同一时刻一个请求（忙时 409 不排队）、重复 id 409、超时 600s 转 ask、
    `fail_all` 宠物退出时把 pending 立即转 ask；线程安全（HTTP 线程 wait / UI 线程 decide）
  - `pet/bridge/server.py`：只绑 127.0.0.1 随机端口、per-run token（`Authorization: Bearer` +
    `hmac.compare_digest`）、非空 `Origin` 一律 403（CSRF）、body ≤ 64KB、字段校验（超长/缺字段 400）；
    `bridge.json` 0600（port/token/pid/started_at）启动写退出删；任何内部异常 → 500 + ask（fail-open）
  - `PermissionRequestViewModel` 落在 `core/models.py`：renderer 只收 VM，不 import bridge 不做网络
  - risk 由 bridge 取 `max(客户端上报, 本地规则计算)`（客户端报 low 但命令含 rm -rf 时兜成 high）
  - 24 项契约测试：鉴权/校验/忙时/重复 id/超时/退出清理/回调异常 fail-open/会话不串
- M2 #14：风险规则纯函数（specs §5.6）：`pet/bridge/risk.py` `assess(tool, summary, detail) →
  high/medium/low`，不用 LLM；high=`rm -rf`/`sudo`/`curl|sh`/`chmod 777`/凭据面/force push，
  medium=`git reset --hard`/全局安装/网络下载/项目外写，默认 low；规则表可整体替换，
  Unicode/长命令/空输入不崩；「可关闭」开关在卡片层（#15）
- M2 #11：attention 事件升级（权限请求/通知事件 → 气泡 + 原生通知 + 声音）：
  - 通知策略从 `wants_notify` 换成 `NotifyGate`（纯函数对象，测试锁定）：
    celebrate/error/attention 三类状态切换时弹一次；**同一件事（session+状态+文案）
    2 秒内只弹一次**；attention 的 key 含 state，不会被前面的完成通知窗口吃掉
    （权限事件优先于完成通知）
  - attention 通知带铃声（macOS 通知 `sound name "Glass"`；Windows Toast 自带系统音），
    celebrate/error 仍然静音横幅（完成提示音另有 wav 叮咚，避免双响）
  - 状态文件协议 v1 的 `session` 字段接入 `SessionState`（去重键的一部分；
    normalize 对其余 v1 字段仍忽略）
  - 菜单新增「勿扰模式（不弹横幅不响铃）」：`settings.json` 的 `dnd`，开启后横幅与
    wav 提示音都不出，气泡/表情照常；通知开关 `notify` 关掉时横幅也不出
  - 菜单新增「去处理（切到终端）」：聚焦跑着 claude 的 App（macOS NSWorkspace 激活 /
    Windows SetForegroundWindow + 最小化恢复）；找不到窗口时气泡给出项目路径
  - 修复 M1 遗留回归：PetView 漏转发 `togglePrivacy:`/`toggleNotify:`，macOS 菜单里
    「隐私模式/原生通知」两项自 #8/#6 起一直点了没反应（AppKit 对没有 selector 实现
    的菜单项静默禁用）；现把全部菜单动作补齐转发
- M1 #6：原生通知（celebrate/error/attention 三类状态，状态切换时弹一次）：
  - macOS：`osascript display notification`（脚本进程稳定免权限；UNUserNotificationCenter 需要真实
    bundle 身份，点按回调拿不到，留 M2 #11 评估）；accessory 应用无 Dock 图标，「Dock 弹跳」以
    换状态小跳 + 提示音替代
  - Windows：PowerShell 借 WinRT 模板发 Toast + `FlashWindowEx` 闪 Claude 窗口任务栏
  - 「点击通知聚焦终端」偏离说明：两条通知通路都拿不到点按回调，通知正文常备项目名 +
    「双击桌宠回到终端」（双击聚焦终端两平台已有）；隐私模式下正文不带项目名
  - 桌宠菜单新增「原生通知」开关（`settings.json` 的 `notify`，默认开）
  - 通知策略收口在 `core.view_model.wants_notify/notify_body`（纯函数，测试锁定）：
    同状态重复刷新不弹，「不反复弹窗」
- M1 #8：隐私模式 + 状态文件健壮性收口：
  - 桌宠菜单新增「隐私模式」开关（写 `settings.json` 的 `privacy`）；hooks 写状态时
    60s 缓存重读该开关，开启后 `project` 置空、tool/reading 的动态文案（带文件名）换成
    「在干活…/在看资料…」——收口在写入方，状态文件、气泡、将来的通知自然都干净
  - 文案底线（无论开关）：只写文件 basename，命令内容/prompt 一概不进状态文件（测试锁定）
  - 坏状态文件：读取侧跳过不崩（已有测试），`/pet doctor` 标记 `state=坏文件`（记录）
  - 旧格式兼容：`aborted`→error、缺字段容忍（#10 已落地）
  - 原子写偏离说明：引擎 `fs` 只有 `write` 没有 rename，状态文件写不了 tmp+rename；
    由读取侧损坏容忍兜底（半截 JSON 跳过），设置文件已是 tmp+`os.replace` 原子写
- M1 #7：`/pet doctor` 自诊断——`pet/doctor.py` 一趟收集：平台/Python、插件版本、
  运行目录可写性（不可写即短路）、状态目录（最新 3 个会话文件的 state 与年龄、坏文件标记）、
  依赖（macOS venv 的 Pillow+pyobjc / Windows 的 Pillow+tkinter）、单实例（锁文件 PID 判活 +
  端口探活）、日志（mtime + 错误日志末尾 2 行）；路径脱敏（HOME → ~），输出可直接粘贴到 issue；
  有 `[err]` 时退出码 1。hooks 侧 `doctor.ts` 只负责跑脚本回显（引擎没有文件读取 API）
- M1 #5：单实例锁 = 端口互斥 + 锁文件（pid/port/ts）+ 明确提示：
  - 端口 bind 是唯一互斥量；`<运行目录>/pet.lock` 只记录 pid/port 供提示与诊断，
    崩溃残留（PID 已死）下次启动自动识别清理
  - 双开不再静默退出：已有桌宠在跑时提示「PID xxx，不再开第二只」；端口被其他程序占用时
    说清端口号与改法（`PET_PORT` 环境变量换端口，hooks 探活同步读取同一值）
  - 修复 #4 遗留：单实例端口此前只 bind 不 listen，探活 connect 恒被拒 → 活着的桌宠
    被当死的、每 10s 拉起循环；现在 listen + 后台 accept，探活真实可用（含回归测试）
  - 修复 TIME_WAIT 重绑：探活连接由服务端先关，端口留 ~30s TIME_WAIT，桌宠退出后
    立刻重启恒失败；`bind` 前设 `SO_REUSEADDR`（Windows 默认允许重绑，不动）
  - 修复 Windows 判活误报：`OpenProcess` 对「已退出但句柄被持有」的进程照样给句柄
    （CI 的 job 对象就会这样），死桌宠被当活的、新实例起不来；补 `GetExitCodeProcess`
    判 STILL_ACTIVE（259）
  - hooks 自动拉起传 `--quiet`：单实例冲突只写 `pet-error.log` 不弹对话框
    （否则端口被占时每 10s 弹一次）；`--shot` 不再参与抢锁
- M1 #4：生命周期 = 活跃会话 + 状态 TTL（协议 §1.2），替代 pgrep/tasklist：core 新增 `STATE_TTL`/`is_live_data`/`has_live_session`；双端 `watch_lifecycle` 无活跃会话超 120s 才退出，Windows 终端找不到 claude.exe 误退根治；hooks 新增 `petAlive` 端口探活 + 10s 节流，桌宠被杀后下一个 Claude 事件自动拉起
- M1 #10：状态协议 v1 落地（specs/state.md）——8 事件映射 + schema 对齐 + 契约测试：
  - hooks 写入方按协议 §4.1 全量映射：`session.start`→waiting(false)、`turn.start`→thinking、
    `tool.call`→tool/reading、工具失败→error(true)、`turn.complete`→waiting(true)/celebrate(false)/error，
    **新增 `notification`→attention(true)「需要你看一下」与 `session.end`→idle(false)「晚安～」**（引擎事件
    清单见 ADR 0001）；aborted 不再是协议状态，写入时直接映射 error
  - 状态文件升级 schema v1：补 `v`/`session`/`agent`/`attention` 字段（可选键给了才写），
    `sound`/`attention` 由写入方显式设置
  - pet 读取方：normalize 新增 attention/idle 识别；未知/缺失 state 回退从 waiting 改为 **idle**（协议 §1.3）；
    旧格式 `aborted` 读取时映射 error；v1 新字段容忍忽略
  - 石化彩蛋迁移：hooks 不再写 `stone`，连续 3 次 error 由渲染层（mac/Windows 双端 poll）自己触发
  - `contracts/state.schema.json` 建立，TS `STATES` 与 Python `PROTOCOL_STATES` 各有契约测试对齐同一份 schema
  - `attention` 立绘复用 knock（端到端验证：状态文件→--shot 截图显示敲门立绘+「需要你看一下」）
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
- hooks 单测从 12 个增加到 24 个（新增 launcher 运行时解析、state_writer 状态文件 schema）
- CI：hooks 单测改成 `node --test --experimental-strip-types hooks/*.test.ts`。
  node 22 的 `--test` 不接受目录参数，会把目录当模块加载报 `MODULE_NOT_FOUND` 直接失败
  （本机 node 26 上两种写法都能过，只有 node 22 会炸，所以要在 CI 的 22 上验）
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
