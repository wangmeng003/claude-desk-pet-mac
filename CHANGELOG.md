# 更新记录

## Unreleased

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
