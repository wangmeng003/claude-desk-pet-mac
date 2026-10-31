# Claude 娘桌宠 · claude-desk-pet

一个给 [Claude Code](https://claude.com/claude-code) 用的小插件：Claude 干活的时候，桌面上会有一个 Q 版 Claude 娘陪着你，实时显示它在做什么。

![六种状态预览](docs/preview.png)

## 功能

**🧡 桌宠悬浮窗**：透明背景、永远置顶，可以拖到屏幕任何位置

| Claude 在做什么 | 桌宠的样子 |
|---|---|
| 思考中 | 闭眼想事情，"思考中…" |
| 跑命令、改文件 | 敲键盘，气泡里显示正在改哪个文件 |
| 读文件、搜索、上网查 | 捧着书记笔记 |
| 回复完，等你说话 | 敲门："轮到你啦！" |
| 出错 | 慌张冒汗 |
| 被你打断 | 心虚 |
| 干了 3 分钟以上的大活 | 撒花庆祝 🎉 |
| 等你超过 10 分钟 | 开始发呆 zZ |

还有一个彩蛋：连续出错 3 次会……石化 🗿

- **双击**桌宠：把 Claude 窗口叫到前台
- **右键**菜单：调大小（小/中/大）、切到 Claude 时自动隐藏、提示音开关、隐私模式、原生通知、勿扰模式（不弹横幅不响铃）、去处理（切到终端）、退出

**📊 Token 状态栏**：输入框下方常驻一行用量信息

> 📊 本会话 输入 12.3k · 输出 4.1k · 缓存命中 87% · $0.42 · 上下文 31% · 5h额度 23%

**🔔 提示音**：回复完播放钢琴"叮咚"，出错播放复古 RPG"哔哔"

**🪪 权限审批卡片（实验性）**：Claude 请求权限时，桌宠弹单请求卡片——项目、工具、摘要、
风险徽标（`rm -rf`/`sudo` 等高危命令红色警告 + 二次确认），Allow / Deny / 回退终端三选一。
任何一环失败（桌宠挂了、超时、坏数据）都回退终端原生提示，**绝不自动放行**。

需要把原生 `PermissionRequest` hook 指到客户端脚本（`hooks/permission_client.mjs`，零依赖，
用 Claude Code 自带的 node 运行），在 `~/.claude/settings.json` 里加：

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "node <插件目录>/hooks/permission_client.mjs",
            "timeout": 620
          }
        ]
      }
    ]
  }
}
```

注意：同一事件配置多个 hook 时**第一个返回决策的获胜**——如果你已有会返回 allow/deny 的
权限 hook，桌宠卡片可能永远等不到请求；桌宠客户端无桥可连时输出空 `{}`，不占别人的决策位。

**命令**

- `/token-stats`：查看本会话和本项目累计的 token 用量、缓存命中率、额度
- `/pet`：不小心关掉了桌宠？用它重新召唤
- `/pet setup`：macOS 上重新准备运行环境（首次安装失败时用）
- `/pet doctor`：自诊断（版本/依赖/状态目录/单实例/日志），输出可直接粘贴到 issue

## 运行要求

**Windows**

- **Windows**（悬浮窗和提示音用的是 Windows 的接口）
- **Python 3**，并且在命令行里输入 `python` 能直接运行
- **Pillow** 图像库，用下面这条命令安装：

```bash
pip install pillow
```

**macOS**

- **macOS 11+**，用原生 `NSWindow`（pyobjc）实现悬浮窗
- **Python 3**：`python3 --version` 能运行（没有的话先安装 Xcode Command Line Tools）
- **Pillow + pyobjc**：第一次启动时插件会自动在 `~/.claude/desk-pet/venv` 建虚拟环境并安装，需要联网，大约 1 分钟

自动安装失败时，也可以手动准备：

```bash
python3 -m venv ~/.claude/desk-pet/venv
~/.claude/desk-pet/venv/bin/pip install --only-binary :all: pillow 'pyobjc-framework-Cocoa==11.1'
```

（Python 3.10+ 也可以装最新版 `pyobjc-framework-Cocoa`；上面的 11.1 同时支持 3.9 和更新版本。）

桌宠会自动按平台分派：Windows 走 `pet/pet.pyw`，macOS 走 `pet/pet_mac.py`。

## 安装

**在终端里的 Claude Code**，输入：

```
/plugin install desk-pet --marketplace wangmeng003/claude-desk-pet-mac
```

然后按 `y` 添加插件市场，选择 user（用户）范围，按回车确认。

**也可以在命令行里运行：**

```bash
claude plugin install desk-pet --marketplace wangmeng003/claude-desk-pet-mac
```

**在 Claude 桌面端**：点输入框旁边的 **+** → **Plugins** → **Add marketplace**，填入 `wangmeng003/claude-desk-pet-mac`，再点 **Add plugin**。

装好后，新开一个会话，桌宠就会出现在屏幕右下角。macOS 第一次运行会自动准备 Python 环境，可能需要约 1 分钟；如果桌宠没出现，运行 `/pet setup` 重试，或查看 `~/.claude/desk-pet/setup.log`。

## 桌宠没出现？

1. macOS 上先运行 `/pet setup`，看依赖是否能装好。
2. 查看日志：
   - `~/.claude/desk-pet/setup.log`：环境安装日志
   - `~/.claude/desk-pet/mod-launch.log`：启动失败时的错误
   - `~/.claude/desk-pet/pet-error.log`：桌宠自己崩溃时的堆栈
3. 确认 `python3 --version` 能运行、网络能访问 PyPI；公司网络有限制时，按上面的手动命令装依赖。
4. Windows 上确认 `python` 命令可用，并且已经 `pip install pillow`。

## 自定义

- **换立绘**：把 `pet/sprites/` 里的 PNG 换成你自己的图（透明背景，文件名保持不变）
- **换提示音**：替换 `sounds/done.wav`（完成）和 `sounds/error.wav`（出错）
- **改台词**：气泡里的文字写在 `hooks/register.ts` 里

桌宠的位置、大小和开关保存在 `~/.claude/desk-pet/settings.json`。

## 开发路线

后续计划见 [docs/ROADMAP.md](docs/ROADMAP.md)，架构与代码质量约定见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，技术契约见 [docs/specs/](docs/specs/)。

近期只做三件事：核心 loop 稳定、权限提醒、安装体验。多会话和主题放在后续条件里程碑；XP、看板、工作台等方向在路线图的 Explore 里按触发条件推进。

## 说明

- 这是个人粉丝作品，与 Anthropic 官方无关
- 立绘由作者用 AI 绘图生成，最初是为自己的视频做的素材
- 代码使用 MIT 许可证，详见 [LICENSE](LICENSE)

### 关于这个 fork

本仓库 fork 自 [BingXing-ai/claude-desk-pet](https://github.com/BingXing-ai/claude-desk-pet)（原作者的 Windows 版），
由 **wangmeng003** 维护，补充了：

- **macOS 支持**：新增 `pet/pet_mac.py`（原生 `NSWindow` 悬浮窗 + pyobjc），`pet/launch.py` 与 `hooks/register.ts` 按平台分派启动
- **首次运行自动准备环境**：macOS 下自动创建 venv 并安装 Pillow/pyobjc，失败时可用 `/pet setup` 重试
- **立绘变形修复**：每张立绘保持自己的宽高比
- **兼容性修复**：去掉 `plugin.json` 的 `types` 字段，避免旧版 Claude Code 同步市场时跳过整个插件

上游更新可以随时同步：

```bash
git remote add upstream git@github.com:BingXing-ai/claude-desk-pet.git
git fetch upstream && git merge upstream/main
```

原作者的版权声明保留在 [LICENSE](LICENSE) 中。
