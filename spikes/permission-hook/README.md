# PermissionRequest hook spike

M0 可行性 spike 的脚本与配置，结论见 [docs/adr/0001-permission-hook.md](../../docs/adr/0001-permission-hook.md)。验证环境：Claude Code 2.1.312 / macOS arm64 / 2026-10-30。

## 文件

- `hook.sh`：带探针的决策 hook。行为由 `/tmp/desk-pet-spike/mode` 文件控制：`allow / deny / none / malformed / crash / block2 / sleep`；把每次调用的 stdin、环境、起止时间戳追加到 `hook.log`。
- `settings.example.json`：项目级 `.claude/settings.json` 片段，`matcher: "Bash"`，`timeout: 5`（秒）。

## 复跑步骤

```bash
mkdir -p /tmp/desk-pet-spike/.claude
cp hook.sh /tmp/desk-pet-spike/hook.sh && chmod +x /tmp/desk-pet-spike/hook.sh
cp settings.example.json /tmp/desk-pet-spike/.claude/settings.json
echo allow > /tmp/desk-pet-spike/mode

# 该目录需要被 Claude Code 信任（~/.claude.json 的 projects 里 hasTrustDialogAccepted），
# 否则项目级 hooks 不会执行
cd /tmp/desk-pet-spike
claude -p 'Use the Bash tool to run exactly this command: echo SPIKE_RAN >> /tmp/desk-pet-spike/ran.log . Then stop.'
cat ran.log   # allow → 有标记；deny/none/malformed/crash → 无标记
```

组合规则测试（第一个返回决策的 hook 获胜）：在同一 `hooks` 数组里放两个内联 `printf` 命令，一个返回 allow、一个返回 deny，轮换顺序各跑一次。

超时语义：`timeout: 5` + `SPIKE_SLEEP=60` 启动 `sleep` 模式，开 `--debug=hooks --debug-file debug.log`，日志会出现 `timed out after 5000ms`，随后回退终端原生流程。
