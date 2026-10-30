# 竞品与市场调研

> 调研日期：2026-10-30  
> 用途：路线图附录，不作为“功能对齐清单”。  
> 关联：[路线图](../ROADMAP.md)

## 0. 怎么读这张表

GitHub 没有公开安装量。下表用 stars、Release 安装包累计下载、npm 月下载、下游项目数做**热度代理**：

- 下载量包含自动更新/CI/重复安装，不等于唯一用户；
- stars 受传播/时间影响，不等于留存；
- 这些数字只用来判断“这个方向有没有人用”，不用来排优先级。

结论：**“只会跟着状态换表情”已经商品化。** 差异化在注意力（权限/多会话）、主题生态、安装体验和中文社区。

---

## 1. 主要项目

| 项目 | 类型 | 关键信号 | 学什么 | 许可证提醒 |
|---|---|---|---|---|
| [`NanmiCoder/cc-haha`](https://github.com/NanmiCoder/cc-haha) | Agent 桌面工作台，桌宠是模块之一 | 15.2k stars；≈24 万安装包下载 | 工作台形态与分发；桌宠可以只是入口 | 以仓库 LICENSE 为准 |
| [`rullerzhou-afk/clawd-on-desk`](https://github.com/rullerzhou-afk/clawd-on-desk) | 纯桌宠 × 20+ Agent 监控 | 6.6k stars；≈12 万下载 | 权限气泡、15 类 hook、多会话 HUD、远程审批、主题、安装包 | **AGPL-3.0**：只借鉴产品思路；复用代码需隔离/遵守 AGPL |
| [`crafter-station/petdex`](https://github.com/crafter-station/petdex) | 宠物画廊 + CLI + 桌面端 | 4.3k stars；npm 6.7k/月；21 个下游项目 | 开放宠物包格式、`npx` 一键安装、画廊/API、创作者生态 | MIT：可参考/复用，注意署名 |
| [`anthropics/claude-desktop-buddy`](https://github.com/anthropics/claude-desktop-buddy) | 官方硬件 BLE 桌宠参考 | 2.7k stars | 7 状态、硬件审批、角色包协议；第二屏/硬件方向 | 以仓库 LICENSE 为准 |
| [`OpenPetsHQ/openpets`](https://github.com/OpenPetsHQ/openpets) | 桌宠平台 + 插件 SDK v3 | 1.35k stars；≈3.6 万下载 | 插件沙箱/权限、MCP、隐私过滤、`doctor`、安装包 | MIT |
| [`ntd4996/agentpet`](https://github.com/ntd4996/agentpet) | 桌宠 + 电子宠物养成 | 394 stars；≈6.8k 下载 + brew | Token 喂养、等级/成就、按项目宠物、菜单栏监控、用量看板 | MIT |
| [`Ido-Levi/claude-code-tamagotchi`](https://github.com/Ido-Levi/claude-code-tamagotchi) | 状态栏宠物 + 行为监控 | 435 stars | 养宠数值、200+ 台词、性格预设；行为拦截暂缓 | MIT |
| [`ssssssanjiu/clawd-conduit`](https://github.com/ssssssanjiu/clawd-conduit) | Clawd 的 15 事件接线层 | 174 stars | 权限 HTTP hook、幂等安装/卸载、绝对路径、排错文档 | MIT |
| [`Renakoni/chara-desk`](https://github.com/Renakoni/chara-desk) | 桌宠 + 本地工作台 | 51 stars | 权限卡片、Token 看板、供应商/Skills/MCP 管理、codex-pet 主题 | MIT |
| [`LorisYounger/VPet`](https://github.com/LorisYounger/VPet) | 经典桌宠模拟器（非 Agent） | 7.1k stars | 动画/交互深度、Mod 生态；宠物本体体验标杆 | 以仓库 LICENSE 为准 |

**补充信号**

- **纯桌宠破圈样本**：`BongoCat`（24.4k）靠键盘/鼠标互动 + 短视频传播；`VPet`（7.1k）靠养成/Mod。说明“宠物本体体验”仍是传播基础，但单独做很难形成工作流粘性。
- **形态创新**：`oc-claw`（362）把宠物放进 macOS 刘海/Windows 任务栏岛；`HachimoDock`（506）做 ESP32 硬件宠物；`claude-desktop-buddy` 做 BLE 硬件审批。
- **官方下场**：Anthropic 有硬件 buddy；社区工具 `cc-buddy` 显示 Claude Code 已有 `/buddy` 宠物系统（2.1.97+ 移到服务端）。**“只会跟着状态换表情”已经商品化**，差异化在权限审批、多会话、主题生态和安装体验。

---

## 2. 五个被验证的需求

1. **权限/等待输入**：长任务跑起来后用户离开终端，回来发现卡在 allow 三分钟。Clawd、Chara Desk、Conduit、官方硬件 buddy 都在解决这个。价值最高，也最容易形成口碑。
2. **多会话/多 Agent**：同时跑 2–5 个 Agent 后，“谁在干活、谁卡住、谁完成”比“宠物可爱”更重要。
3. **主题/角色生态**：Petdex 用开放格式 + 画廊 + CLI 把“宠物”变成内容供给；AgentPet/Chara/HachimoDock 都兼容 codex-pet 格式。
4. **成长/统计**：Token 是天然经验值。AgentPet 用真实 token/会话喂养，做等级/成就/连续天数/排行榜。
5. **安装体验**：Clawd/AgentPet 都有 installer/brew/notarized；本项目 macOS 首次运行要建 venv + 从 PyPI 装 Pillow/pyobjc，这是最大的转化漏斗。

---

## 3. 学到什么 / 不学什么

### 学

- **权限提醒**是最高价值的“工具属性”，但审批卡片必须建立在 hook 可靠的前提下；先通知，后审批。
- **多会话聚合**是 power user 的强需求，但先验证占比，不默认所有用户都多开。
- **Petdex 格式**值得兼容，不值得自建画廊；用开放格式换内容供给。
- **安装体验**决定转化；先一键脚本/zip，签名/打包后置。
- **`doctor`/日志/幂等安装**是低成本高口碑的支持能力。
- **原生/轻量**是差异化的基础；不要为了功能对齐引入 Electron。

### 不学

- 不把竞品功能清单当路线图；不因为 Clawd 有 20+ Agent 就跟着做。
- 不做 LLM 行为拦截（误报/信任/延迟/责任）。
- 不自建主题画廊/远程审批/工作台，直到核心 loop 和留存有证据。
- 不复制 AGPL 代码；只借鉴产品思路。
- 不用“宠物很可爱”掩盖“装不上/错过权限/多开乱”的核心问题。

---

## 4. 许可证清单

| 项目 | 许可证 | 能否复用代码 |
|---|---|---|
| `clawd-on-desk` | AGPL-3.0 | 否（除非隔离/遵守 AGPL 或取得授权） |
| `petdex` | MIT | 可以，保留版权/许可声明 |
| `openpets` | MIT | 可以，保留版权/许可声明 |
| `agentpet` | MIT | 可以，保留版权/许可声明 |
| `claude-code-tamagotchi` | MIT | 可以；行为拦截思路暂不采用 |
| `clawd-conduit` | MIT | 可以 |
| `chara-desk` | MIT | 可以 |
| `claude-desktop-buddy` | 以仓库为准 | 复用前确认 |
| `VPet` | 以仓库为准 | 复用前确认 |
| `BongoCat` | 以仓库为准 | 复用前确认 |

> 所有第三方代码/素材进入本仓库前，必须确认许可证并记录在 `THIRD_PARTY_NOTICES.md`（v1.0 前建立）。

---

## 5. 对路线图的输入

| 调研结论 | 路线图落点 |
|---|---|
| 权限提醒价值最高，但卡片依赖 hook | M2 分 P1/P2；M0 spike 决定 |
| 多会话是强需求但占比未知 | M3 条件启动；M0 验证 |
| Petdex 已占格式/画廊 | M4 只做本地导入；画廊 Explore |
| 安装是最大漏斗 | M5 一键脚本/托盘；签名后置 |
| 游戏化/看板有需求但非核心 | Explore，有触发条件再做 |
| 工作台/20+ Agent 是另一个市场 | Explore/v2，不承诺 |
| LLM 行为拦截风险高 | 暂缓，规则型提醒替代 |
