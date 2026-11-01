# 主题包格式 v1

> 状态：草案 · 2026-10-30  
> 关联：[路线图](../ROADMAP.md) · [架构](../ARCHITECTURE.md)

## 0. 结论

- **只做本地导入**，不自建画廊/API/商店。
- **优先兼容 Petdex/Codex pack**：8×9 或 8×11 网格、192×208 帧；以 Petdex 当前 manifest 为准，下面是我们支持的兼容子集。
- **兼容现有布局**：`states/<state>.png` 单图，直接复用 `pet/sprites/`。
- **只允许数据**：JSON + PNG/WebP + WAV/MP3；不执行脚本、HTML、SVG。
- 主题加载失败 → 回退内置皮肤，不崩溃。

---

## 1. 目录结构

### 1.1 网格布局（Petdex/Codex）

```text
my-pet/
  pet.json
  spritesheet.png
  sounds/            # 可选
    done.wav
    error.wav
```

### 1.2 单图布局（本项目现有）

```text
my-pet/
  pet.json
  states/
    idle.png
    thinking.png
    tool.png
    reading.png
    waiting.png
    attention.png
    celebrate.png
    error.png
  sounds/
    done.wav
    error.wav
```

> 两种布局二选一；同时存在时以 `pet.json` 的 `layout` 为准。

---

## 2. `pet.json`

### 2.1 网格布局

```json
{
  "schema": 1,
  "id": "my-pet",
  "name": "My Pet",
  "author": "someone",
  "license": "CC-BY-4.0",
  "layout": "spritesheet",
  "frame": {
    "width": 192,
    "height": 208,
    "columns": 8,
    "rows": 9
  },
  "states": {
    "idle": [0, 1, 2, 3],
    "thinking": [8, 9],
    "tool": [16, 17],
    "reading": [24, 25],
    "waiting": [32, 33],
    "attention": [40, 41],
    "celebrate": [48, 49],
    "error": [56, 57]
  }
}
```

- `states` 的值是帧索引（从 0 开始，按行优先）。
- `image`：spritesheet 图片的相对路径，缺省 `spritesheet.png`；路径同样受 §6 约束。
- 未列出的状态按 §3 映射回退；至少要有 `idle`。
- 帧数必须是 `columns × rows` 的合法索引；越界拒绝导入。

### 2.2 单图布局

```json
{
  "schema": 1,
  "id": "my-pet",
  "name": "My Pet",
  "author": "someone",
  "license": "CC-BY-4.0",
  "layout": "states",
  "states": {
    "idle": "states/idle.png",
    "thinking": "states/thinking.png",
    "tool": "states/tool.png",
    "reading": "states/reading.png",
    "waiting": "states/waiting.png",
    "attention": "states/attention.png",
    "celebrate": "states/celebrate.png",
    "error": "states/error.png"
  }
}
```

- 路径必须是主题目录内的相对路径；禁止 `..`、绝对路径、符号链接。
- 缺状态按 §3 映射回退；缺 `idle` 拒绝导入。

### 2.3 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema` | 是 | 当前 `1` |
| `id` | 是 | 唯一 id；小写字母/数字/`-`/`_`；≤ 64 字符 |
| `name` | 是 | 显示名；≤ 80 字符 |
| `author` | 否 | 作者 |
| `license` | 是 | SPDX 标识或 `unknown`；`unknown` 导入时警告 |
| `layout` | 是 | `spritesheet` / `states` |
| `frame` | 网格必填 | `width/height/columns/rows` |
| `image` | 网格可选 | spritesheet 图片相对路径；默认 `spritesheet.png` |
| `states` | 是 | 状态 → 帧索引数组或相对路径 |
| `sounds` | 否 | `{"done":"sounds/done.wav","error":"sounds/error.wav"}` |
| `preview` | 否 | 预览图相对路径 |

> 不支持的字段忽略；但 `license` 缺失/为空拒绝导入。

---

## 3. 状态映射

### 3.1 本项目 8 状态

`idle`、`thinking`、`tool`、`reading`、`waiting`、`attention`、`celebrate`、`error`。

### 3.2 Petdex/Codex 9 行映射

| Petdex 行 | 本项目状态 | 说明 |
|---|---|---|
| `idle` | `idle` | 默认 |
| `running` | `tool` | 干活/跑工具 |
| `waiting` | `waiting` | 等用户 |
| `failed` | `error` | 失败 |
| `review` | `reading` | 读/审查 |
| `jumping` | `celebrate` | 完成/庆祝 |
| `waving` | `attention` | 需要注意 |
| `running-left` | `tool` | 可选方向动画 |
| `running-right` | `tool` | 可选方向动画 |

- 9 行 pack：按行号映射；`running-left/right` 可忽略，只取 `running`。
- 11 行 pack：额外两行保留给 `idle` 变体/`sleeping`；当前只使用前 9 行，不报错。
- 缺 `attention` → `waiting`；缺 `celebrate` → `waiting`；缺其他 → `idle`。

---

## 4. 安装与管理

### 4.1 命令

```text
/pet theme list
/pet theme install <path|zip>
/pet theme use <id>
/pet theme remove <id>
/pet theme info <id>
```

- `install`：校验 → 复制到 `~/.claude/desk-pet/themes/<id>/`；已存在则要求 `--force`。
- `use`：写 `settings.json` 的 `theme` 字段；立即重载。
- `remove`：不能删除当前使用中的主题；先切回内置。
- `info`：显示名称、作者、许可证、帧尺寸、状态覆盖情况。

### 4.2 拖拽导入

- M4 可选：拖主题文件夹/zip 到桌宠窗口 → 校验 → 确认安装。
- 拖拽只接受本地路径；不自动下载。

### 4.3 内置主题

- 内置皮肤可先复用 `pet/sprites/`；后续迁移到 `themes/builtin/`，默认使用。
- 内置素材只用原创/已授权；许可证记录在 `THIRD_PARTY_NOTICES.md`。
- 用户主题独立许可证；不默认随仓库分发。

---

## 5. 校验

### 5.1 结构

- `pet.json` 存在、≤ 64KB、合法 JSON。
- `schema` 支持（当前 1）。
- `id` 合法；安装时目录名可重命名，安装后 `id` 与目录名一致。
- `license` 非空。
- `layout` 合法；`states` 至少包含 `idle`，且 `idle` 非空。
- 网格：`columns/rows > 0`；`width/height` 在 32–1024；帧索引不越界。
- 单图：路径在主题目录内；文件存在；PNG/WebP 可解码。
- `sounds` / `preview` 路径同样必须在主题目录内；文件类型/大小符合限制。

### 5.2 资源限制

| 项 | 上限 |
|---|---|
| 单包解压后 | 20MB（建议） |
| `pet.json` | 64KB |
| 单张图 | 4096×4096 |
| 帧尺寸 | 32–1024 px |
| 音频 | 2MB/个，WAV/MP3 |
| 文件数 | 200 |

- 超限拒绝，给出明确错误。
- zip 导入：防 zip bomb（解压上限、文件数上限、路径穿越）。
- 不解压符号链接/设备文件。

### 5.3 失败行为

- 校验失败：不安装、不切换；显示原因。
- 运行时加载失败：回退内置皮肤；记录 `pet-error.log`；不崩溃。
- 缺状态：按 §3 映射回退（`attention`/`celebrate` → `waiting`，其余 → `idle`）。
- 图片解码失败：该状态回退 `idle`；仍失败则内置占位图。

---

## 6. 安全

- **不执行代码**：禁止 `.js`、`.py`、`.sh`、`.html`、`.svg`（SVG 可含脚本）；只允许 JSON/PNG/WebP/WAV/MP3。
- **路径安全**：拒绝绝对路径、`..`、符号链接、硬链接；解析后必须位于主题目录内。
- **不联网**：导入/使用主题不发起网络请求；未来画廊也必须显式开启。
- **不读用户数据**：主题加载器只读主题目录；不读 `~/.claude` 其他内容。
- **渲染安全**：图片只作为纹理绘制；不解析元数据中的 HTML/命令。
- **许可证**：`license` 必填；`unknown` 警告；内置素材必须有来源记录。

---

## 7. 测试

### 7.1 fixture

```text
tests/fixtures/themes/
  valid-spritesheet/
  valid-states/
  missing-idle/
  missing-license/
  bad-frame-index/
  path-traversal/
  oversized/
  bad-image/
  unknown-state/
```

### 7.2 用例

- [x] 合法网格包导入/切换/回退。（tests/test_theme.py；macOS 实机截图验证）
- [x] 合法单图包导入/切换/回退。
- [x] 缺 `idle` 拒绝；缺其他状态回退。（回退链 attention/celebrate→waiting→idle 走到底）
- [x] 缺 `license` 拒绝；`unknown` 警告但可导入。
- [x] 帧索引越界拒绝。
- [x] 路径穿越/符号链接拒绝。
- [x] 超大文件/zip bomb 拒绝。（pet.json/单图/音频/全包大小/文件数/zip 条目逐项校验）
- [x] 坏图片回退，不崩溃。（loader 拒魔数不对的图；运行时解码失败由渲染层逐张回退）
- [x] 删除使用中的主题被拒绝。
- [x] 主题切换后设置持久化，重启仍生效。（settings.json `theme` 字段；渲染层启动即读 + mtime 探测立即重载）
- [ ] 默认无网络请求。（构造上无网络代码——stdlib 只用 os/json/re/shutil/zipfile/stat；未单测）

### 7.3 实现备注（M4 第一刀，2026-11-02）

- 网格包的 sheet 路径：manifest 支持 `image` 字段，缺省 `spritesheet.png`；Petdex
  manifest 的精确字段仍未对照（§9 开放问题保持），当前按本兼容子集实现。
- 帧动画未接：网格包每个状态先取第一帧静态绘制；多帧动画是后续切片。
- 拖拽导入（§4.2）未做，只有 `/pet theme install`。
- 硬链接不检测：`st_nlink>1` 区分不了包内正常复制与指向包外的硬链接；目录与
  zip 两条安装路径都逐级拒绝符号链接，包内文件不执行，泄露面已封。
- 「use 立即重载」实现为渲染层按 settings.json mtime 探测（250ms 轮询内生效）。
- 内置皮肤仍在 `pet/sprites/`，未迁移 `themes/builtin/`（§4.3 允许「先复用」）。

---

## 8. 非目标

- 自建画廊/API/商店。
- 付费/账号/云同步。
- 主题执行脚本/插件。
- 主题绑定 XP/成就。
- 自动从网络下载主题（Explore 后再评估，默认关闭）。

---

## 9. 开放问题

| 问题 | 何时解决 |
|---|---|
| Petdex manifest 的精确字段/版本 | M4 前对照最新规范 |
| 11 行 pack 的额外两行如何映射 | M4 前 |
| 动图 GIF/APNG 是否支持 | 先不支持；PNG/WebP 静态帧 |
| 主题预览图生成 | M4 可选 |
| 社区主题许可证审核 | 画廊启动前 |
