# 审查指南（Review Guide）

本文件为 [2.1.1] 缺陷修复批次的**复核清单**，目的是让审查者在
236 项文件改动中快速定位到真正需要人眼判断的部分。

- 修复清单与理由见 [CHANGELOG.md](../CHANGELOG.md) 的 `[2.1.1]`
- 自动化验收：
  - `python -m pytest tests` → **281 passed**（7 项 realserver 默认排除）
  - `python -m pytest -m realserver` → **7 passed**（真实 pylsp 联调）
  - `python -m ruff check .` → 0 告警
  - `python tools/check_version.py` → 一致
  - `python build.py` → 成功，`main()` 返回 0

---

## 1. 建议优先阅读的 6 个文件

这些文件承载了本次所有高风险改动（数据正确性 / 协议正确性 / 安全边界）。

| # | 文件 | 看什么 | 风险等级 |
|---|---|---|---|
| 1 | [core/content_provider.py](../core/content_provider.py) | `_save_dirty_blocks` 的 `truncate` 与"用磁盘真实大小比较"；`_save_as_full` 的 inode 重开；新增 `_reopen_file_handle` | **数据损坏** |
| 2 | [core/document.py](../core/document.py) | `_replace_full_content` 中元数据**先于**写块更新（否则新块被静默拒绝） | **数据截断** |
| 3 | [core/lsp_client.py](../core/lsp_client.py) | 通道分离；`_process_buffer` 的噪声跳过；`did_open` 输入防御；`initialize` 的 `uri_to_path` 调用 | **协议正确性** |
| 4 | [core/editor.py](../core/editor.py) | `toggle_lsp` 的 `did_open` 三参调用；`_sync_lsp_document` 防抖；`did_save`/`did_close` | 协议正确性 |
| 5 | [app/plugins.py](../app/plugins.py) | `grant_permission` 宿主校验；`get_main_window` 权限门控；`win` 弃用属性；`_host_window` | **安全边界** |
| 6 | [ui/main_window.py](../ui/main_window.py) | `_load_plugins` 改走 `PluginManager.load_all`；`_ensure_panel` + `_build_panel_*` 惰性构造 | 安全 / 启动 |

---

## 2. 三个最容易"看不出来但很关键"的细节

### 2.1 truncate 必须用 `os.fstat`，不能用 `self._size`

编辑器保存前会先调 `Document._replace_full_content()`，那里**已经**
把 `provider._size` 改成新长度。若截断判断用 `self._size` 比较，就会
得出"没变短"的结论 → **截断被跳过**，旧字节继续残留。

这正是我第一版修复的失败原因：单元测试显示 `P0-1 FIXED: False`。

```python
# core/content_provider.py
try:
    on_disk = os.fstat(f.fileno()).st_size   # 磁盘真实大小
except Exception:
    on_disk = self._size
if new_size < on_disk:
    f.truncate(new_size)
```

### 2.2 LSP 帧解析的噪声跳过不能"丢到第一个 `\r\n\r\n`"

噪声与协议头可能**在同一段**里：

```
noise\nContent-Length: 33\r\n\r\n{"jsonrpc":...}
```

此时第一个 `\r\n\r\n` 位于整个消息之后，把它之前的内容当噪声丢掉，
等于把**整条合法消息**吃掉。正确做法是先定位 `Content-Length:` 起点。

### 2.3 Qt 跨进程测试必须驱动事件循环

`QProcess` 的 `readyReadStandardOutput` 等信号只在 Qt 事件循环里投递。
用 `time.sleep` 轮询会永远收不到回复，测试表现为"握手超时"，
从而误判为代码有 bug。

```python
from pytestqt.qtbot import QtBot  # 通过 qtbot fixture 注入
qtbot.waitUntil(lambda: client.is_initialized, timeout=8000)
```

---

## 3. 本次由验证新发现并修复的缺陷

| 缺陷 | 如何发现 | 影响 |
|---|---|---|
| `LspClient.initialize()` 调用不存在的 `self._uri_to_path` | 真实子进程 LSP 端到端测试 | **即使修好 did_open，LSP 仍起不来**；握手第一步 `AttributeError` 被宽泛 `except` 吞掉 |
| `Document._replace_full_content` 元数据后更新导致新块被拒 | 保存"缩短→增长→再缩短"循环测试 | 内容被截断为旧长度 |
| 我自己的帧解析噪声修复仍会吃掉消息 | 子类逐行追踪 `_process_buffer` | 噪声后首条消息丢失 |
| `tests/test_secure_storage.py` 顺序依赖 | 全量套件 vs 单文件结果不一致 | keyring 可用环境下断言随机失败 |

---

## 4. 验证方式与边界

### 已验证

| 项目 | 方式 | 结果 |
|---|---|---|
| 保存不残留旧字节 | 端到端：55 890 字节 → 12 字节 | 磁盘 = 12 字节 ✅ |
| **搜索性能（最严重缺陷）** | 1 MB / 19 065 匹配；10 MB / 190 650 匹配 | **>25 s → 0.415 s**；**>15 min → 3.702 s** ✅ |
| 搜索正确性 | 逐行核对 + 中文列号 + CRLF + 越界 | line/col/line_text 与修复前完全一致 ✅ |
| 编辑器层搜索 | `EditorProxy.highlight_all` / `search_next` | 1 MB 高亮 19 065 处 = 0.928 s；连续查找正确 ✅ |
| LSP 完整握手（最小服务器） | 真实子进程 + QProcess + JSON-RPC | 5 个消息全部到达，版本 1→2 ✅ |
| LSP 语义（真实 pylsp） | python-lsp-server 1.15.0 联调 | 握手 3.8s；didChange 后诊断**再次推送**；补全 **454 项** ✅ |
| 插件权限门控 | 单测 + 启动路径 spy | 10 个插件均经权限确认 ✅ |
| 版本一致性 | `tools/check_version.py` | 0 处漂移 ✅ |
| 4 语言翻译 | gettext 实际加载 | 保存/Save/保存/저장 ✅ |
| 惰性面板 | 启动 `_panels_built == set()`；按需构造 9/9 成功 | ✅ |
| 启动耗时 | `MainWindow()` 冷启动 | 2.46 s → 1.36 s ✅ |
| GUI 实际渲染 | offscreen + 手动注册系统字体后截图 | 见下节 ✅ |
| **打包链路** | `python build.py` 全量执行 | **成功，`main()` 返回 0**；377 文件 / 137.0 MB ✅ |
| **打包产物可运行** | `QingCaoEditor.exe --version` | **v2.1.0**，退出码 0 ✅ |
| 安装器图标资源 | `build.generate_icon()` | 产出 `qingcao.ico` ✅ |

### 未验证（需你的环境）

- **安装包编译**：本机 **Inno Setup (ISCC) 未安装**，因此
  `installer.iss` 未实际编译。其依赖的
  `resources/icons/qingcao.ico` 现已存在（此前是构建阻断项）。
- **真实显示器渲染**：见下节说明。
- **与 pylsp 的诊断内容兼容性**：pylsp 1.15.0 默认**不报未定义名**
  （`publishDiagnostics` 内容为空列表）。因此真实服务器测试断言的是
  "诊断通知到达 + 结构合规 + didChange 后再次推送"，而**不是**
  "必须有错误内容"。这一点已如实写进测试注释，避免将来因 pylsp
  策略变化而假失败。

### 行尾符问题（影响 diff 可读性）

仓库历史提交中 **CRLF/LF 混用**。这会把真实改动放大成巨量 diff：
本次审查中 `git diff --numstat` 显示 **59 761 行**变更，而
`git diff --ignore-all-space --numstat` 只有 **5 726 行**真实改动。

逐文件核对结果（168 个已修改文件）：

| 分类 | 数量 | 说明 |
|---|---|---|
| 行尾未变 | 148 | 内容改动，行尾保持原样 |
| CRLF → LF | 16 | 含 `core/macro.py`、`ui/preferences_panel.py`、`build_*.py`、`installer.iss`、`VERSION` 等 |
| LF → CRLF | 2 | `core/secure_storage.py`、`tests/test_secure_storage.py`（这对文件很可能是**会话前**的编辑） |
| 其他/混合 | 2 | — |
| **纯行尾差异（内容完全相同）** | **0** | 即：没有任何文件可以被简单地"还原因行尾而丢失内容" |

已新增 `.gitattributes` 声明库内统一 LF。**建议把一次性归一化作为
独立提交**，不要与功能改动混在一起：

```bash
git add --renormalize .
git commit -m "chore: 统一行尾为 LF"
```


### 关于 GUI 截图的重要说明

`QT_QPA_PLATFORM=offscreen` 下 PyQt5 的字体目录不存在，**字体数据库
为 0 个字体族**，导致首次截图正文完全空白（`QFontMetrics` 对所有
字体名返回相同宽度）。截图前需手动注册系统字体：

```python
from PyQt5.QtGui import QFontDatabase
QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\consola.ttf")
QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
```

在**真实显示器**上系统字体会正常加载，无需此步骤。

目视确认结果（`docs/screenshot_main_window.png`）：中文菜单栏
（文件/编辑/视图/工具/帮助）、工具栏、带语法高亮的 Python 编辑区、
**中文函数名与文档字符串**、行号、折叠标记、状态栏（会话恢复、
内存占用）全部正确渲染。

---

## 5. 仓库中本次会话之前就存在的改动

以下文件在本次修复**开始之前**就已经是未提交状态，我**没有**回退它们，
也无法替作者判断意图。请确认是否要保留：

- `core/secure_storage.py`（约 594 行改动，规模最大）
- `plugins/demo/__init__.py`、`plugins/demo/plugin.json`、
  `plugins/my_plugin/__init__.py`
- `resources/theme_fallback.json`、`themes/eye_protect.json`
- `docker-compose.yml`、`plugins/git_deep/diff_view.py`（部分）
- `tests/` 下多个既有测试文件的改动

> 备注：本次会话中我一度用 PowerShell 重写 5 个插件的
> `self.api.win` → `self.api._host_window()`，该操作意外引入 UTF-8 BOM
> 并产生了大面积空白差异。已用 `git checkout` 还原这 5 个文件，改为
> **字节精确替换**重做。因此 `git diff` 中这些插件文件的差异主要来自
> 会话前的既有改动，而非本次修复。

**建议**：正式提交前先用
`git diff --stat` 总览、再对上述文件单独 `git diff <file>`
确认取舍；本次修复的改动带 `P0-x` / `P1-x` / `P2` 标记，便于区分。
