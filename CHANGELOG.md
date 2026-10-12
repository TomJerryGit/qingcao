# Changelog

所有重要的项目变更都记录在此文件中。

本项目遵循 [语义化版本](https://semver.org/)。

## [Unreleased]

### 计划中
- 更多 LSP 语言支持
- 协作编辑完善
- 插件市场后端

### 删除

- **移除未接线的插件沙箱原型**
  `infrastructure/plugin_sandbox.py`（1605 行）、
  `infrastructure/sandbox_runtime.py`（1192 行）、
  `core/sandbox_policy.py`（593 行），以及 `tests/test_plugin_sandbox_event.py`
  与 `tests/test_sandbox_socket.py`（共 350 行）。

  **删除理由（有实测证据）**：

  * 这 3390 行**没有任何生产调用方** —— `sandbox_policy` 只被
    `sandbox_runtime` 引用，`sandbox_runtime` 只被测试引用；
    `build.py` 的 hidden-imports 与 `pyproject.toml` 的 coverage omit
    是仅有的其它提及。
  * 它**根本无法启动**：实测 `PluginSandbox.start()` 返回 `False`、
    状态卡在 `RESTARTING`。原因之一是 `_install_security()` 里写的
    `__builtins__.__import__` —— 在非 `__main__` 的普通模块里
    `__builtins__` 是 **dict** 而非 module，赋值会 `AttributeError`
    （已用最小实验复现）。子进程入口与帧协议也有缺陷。
  * 与此同时 **5 个相关单测始终是绿的** —— 它们只测消息常量与
    纯函数，从不真正 `start()`。这正是"测试全绿但功能不可用"的典型。
  * 名字本身构成误导：`plugin_sandbox` 会让人以为插件已被隔离，
    而实际**没有任何隔离**。

  代码可在 git 历史中查阅（`2.1.1` 之前的提交）。若将来要做真隔离，
  需注意这是一项**结构性改造**：现有 `PluginAPI` 大量操作 QWidget
  （面板、菜单、对话框），子进程无法持有这些对象，API 边界必须重新设计。

- 顺带移除 `app/preferences.py` 中无任何 UI/运行时引用的
  `plugin_sandbox` 开关（避免暗示"可以开启真沙箱"）。
- `build.py` 的 hidden-imports 与 `pyproject.toml` 的 coverage omit
  同步清理。验证：78 个 hidden imports 全部可导入。

## [2.1.1] - 2026-09-25

本次更新为**缺陷修复版本**：修复一个会导致**数据损坏**的保存
缺陷、LSP 初始化崩溃、插件权限体系失效，并统一版本号来源、
补齐翻译与资源、降低启动耗时。原有 198 项测试全部保持通过。

### 修复（P0）

- **搜索在大文件上不可用（O(n²)，最严重的性能缺陷）**
  `core/search.py::_get_line_text` 每次调用都执行
  `provider.read_text()` + `text.splitlines()`，即**读取并切分整个
  文件**；而它被 `_build_match` 在**每个匹配**上调用一次，
  复杂度从 O(N) 退化为 O(匹配数 × 文件大小)。

  实测（重复 50 字符文本，纯文本搜索 `quick`）：

  | 文件 | 修复前 | 修复后 |
  |---|---|---|
  | 16 KB（297 匹配） | 0.031 s | — |
  | 64 KB（1 191 匹配） | 0.426 s | — |
  | 256 KB（4 766 匹配） | 9.799 s | < 1 s |
  | 1 MB（19 065 匹配） | **> 25 s 未完成** | **0.415 s** |
  | 10 MB（190 650 匹配） | **> 15 分钟无输出** | **3.702 s** |
  | 10 MB 正则 | 不可用 | 4.479 s |

  上层路径同步受益：`EditorProxy.highlight_all` 对 1 MB / 19 065 处
  高亮从"不可用"降到 **0.928 s**。

  修复方式：新增唯一权威行索引 `_ensure_line_index()`（复用已有的
  全文解码结果，不额外读盘），每行取值降为 O(行长) 切片。

  > **过程中的重要教训（已写入代码注释）**：修复后我尝试把
  > `_build_line_index` 也接到同一个索引上"消除重复构建"，写成
  > `return self._ensure_line_index()[:-1]` —— 结果引入了 **13× 退化**
  > （1 MB 从 0.268 s 变成 3.484 s）。实测每次 `index[:-1]` 要拷贝
  > 19 065 个元素：`_position_to_line_col` 变成 **169.54 µs/次**，
  > 其中列表拷贝占 **182.98 µs/次**，而纯 bisect 只要 **0.60 µs/次**。
  > 改为**直接返回缓存索引、不做任何切片拷贝**后恢复（索引末尾的
  > 哨兵不影响 bisect，因为 `position < len(text)` 永远选不中它）。
  > 这个坑由新增的回归测试 `test_line_index_not_copied_per_match`
  > 长期守住。

- **保存残留旧字节（数据损坏）**
  `core/content_provider.py::_save_dirty_blocks` 只按块
  `seek+write`，**从不截断文件**。把 55 890 字节的文件删到
  12 字节后保存，文件仍是 55 890 字节（新内容 + 旧尾部），
  重开编辑器会看到"已删除的内容又回来了"。
  现按脏块真实长度 `truncate()`，并用磁盘实际大小比较
  （编辑器保存前会先把 `_size` 改成新长度，用它比较会漏掉截断）。
  另修 `_save_as_full` 的 inode 替换问题（`os.replace` 后
  `self._file` 仍指向旧 inode，现重新打开句柄并重建 mmap）。

- **LSP 初始化参数错位导致语言服务不可用**
  `core/editor.py` 调用 `did_open(uri, self.sc.text())`，而签名是
  `did_open(uri, language_id, text, version)`：`language_id` 收到整份
  文件文本、`text` 缺失、`version=None`，随后 `did_change` 必然
  `TypeError`（`NoneType += int`）并被宽泛 `except` 吞掉。
  现已按签名传参、用 `path_to_uri` 生成 URI、补 `did_change`
  防抖同步与 `did_save`/`did_close`；`LspClient` 侧做输入防御
  （text 为 None、version 非法、language_id 疑似全文时回退并告警）。

- **LSP 通道合并污染协议流**
  `QProcess.MergedChannels` 把语言服务器 stderr 并入 stdout，
  stderr 上的日志/banner 会破坏 `Content-Length` 帧解析，
  `_on_stderr` 永不触发。改为 `SeparateChannels`，并让帧解析器
  在遇到非法头时丢弃该段噪声后重试（原实现会一路吃掉后续合法消息）。

- **LSP `initialize()` 必然崩溃**（由真实子进程端到端测试发现）
  `LspClient.initialize()` 调用 `self._uri_to_path(root_uri)`，但本类
  只有无下划线前缀的 `@staticmethod uri_to_path` —— 因此握手第一步
  就抛 `AttributeError`，被 `EditorProxy.toggle_lsp` 的宽泛 `except`
  吞掉。**这意味着即使修好了 did_open 的参数错位，LSP 仍然起不来**；
  纯逻辑单元测试无法发现，只有跨进程握手测试才能暴露。
  已改为 `LspClient.uri_to_path(root_uri)`。

- **插件权限体系失效**
  - 启动路径调用裸 `loader.load_all()`，而
    `PluginManager.load_all` / `_check_and_confirm_permissions`
    全仓无调用者 —— **危险权限确认框永远不会弹出**。
    现改为经 `PluginManager.load_all(auto_activate=True)` 加载。
  - `PluginAPI.grant_permission()` 允许插件一行自我提权
    （`grant_permission('process')` + `run_command(...)`）；
    现在必须由宿主授权，新增 `grant_permissions_by_host()`。
  - `api.win` 是公开属性，插件可经它拿到主窗口与**全权限主 API**
    从而绕过全部检查；现改为弃用属性（打印一次告警）+
    受 `dialog` 权限门控的 `get_main_window()`。
  - `get_plugin_data_dir()` / `save_plugin_config()` 原为
    "无需权限"的写盘后门，现要求 `filesystem` 权限。
  - 内置插件迁移到 `api._host_window()`；为 logtail /
    markdown_preview / todo_panel / wordcount 补上它们实际使用
    的 `dialog` 权限声明。
  - `plugin_sandbox.py` / `sandbox_runtime.py` 顶部加入**醒目的
    未接线警告**（这两份 ~2 800 行代码目前没有任何生产调用方，
    当前版本**没有进程级隔离**）。

### 修复（P1）

- **版本号漂移**：`version.py` / `VERSION` / `installer.iss` /
  各 `build*.py` / 运行时代码共 30 余处各自硬编码版本号，
  且 CHANGELOG 已发布 2.1.0 而代码仍写 2.0.0。
  现统一以 `version.py` 为唯一来源（运行时代码改为导入），
  新增 `tools/check_version.py` 做全仓一致性校验，
  `release.py` 的 bump 会同步写入 `version.py`。
- **插件热重载是空壳**：`_on_directory_changed` 原本只打印一句
  "可能需要重启编辑器"。现实现真正的 unload → load → activate，
  递归监控插件目录与源码文件，支持 `"hot_reload": false` 退出，
  并新增 `plugin_hot_reload` 首选项（默认开）。
- **国际化是空壳**：`locale/` 下只有 1 个 `.po`，其正文是 GBK
  字节却声明 `charset=UTF-8`，且全仓**没有任何 `.mo`** ——
  4 种语言从未生效。现补齐 4 语言（49 条词条）的 UTF-8 `.po`
  与 `.mo`，并新增 `tools/build_translations.py` /
  `tools/compile_locale.py`；`first_run_wizard` 的 `"???"` 韩语
  标签修正为 `한국어`。
- **音效模块是死代码**：`infrastructure/sound_manager.py`（1600+
  行）全仓零调用。现接入文件打开 / 保存 / 报错事件，并新增
  `sound_effects` 首选项（**默认关闭**，避免突然出声）。
- **启动耗时**：`_build_docks` 启动时同步构造全部 9 个面板
  （其中 6 个随即 hide）。改为惰性构造，实测
  `MainWindow()` 从 **2.46 s 降到 1.36 s**。
- `app/plugins.py` 补齐 README 已文档化但代码缺失的
  `lsp` / `debugger` 权限常量。

### 修复（P2）

- **README 渲染崩塌**：全文只有 2 个代码栅栏，中间 17 处裸语言
  标记（`bash`/`json`/`python`/`text`），GitHub 上从第 97 行起
  整篇被渲染成代码块。现重建为 26 个成对栅栏，并修正
  "方式三 pip 安装"（尚未发布 PyPI）、`create_plugin.py` 路径、
  配置文件路径、权限表、`Ctrl+H` 等与实现不符的描述。
- **安装包构建阻断**：`installer.iss` 引用的
  `resources/icons/qingcao.ico` 不存在。现新增
  `tools/make_assets.py`，生成 `qingcao.png` / `qingcao.ico`
  （含 7 种尺寸）与 `splash.png`。
- **lint 配置缺失**：仓库无任何 lint 配置，而 CI 对全仓运行
  ruff/black/isort，必然失败。现新增 `pyproject.toml`
  （ruff / black / isort / pytest / coverage），修复全部
  `F821` 未定义名与 `F811` 重定义（真实缺陷），自动整理
  380 处导入顺序，并把历史存量规则显式记录在 `ignore` 中；
  `ruff check .` 现在 0 告警。工作流改为 ruff 单一门禁 +
  版本一致性 + 翻译编译 + 测试四个 job。
- **仓库卫生**：新增 `tools/clean_repo.py`（默认 dry-run）
  清理 103 个 `*.bak.*` 备份（69 447 行），补全 `.gitignore`
  对 `msg.txt` / `findstr` / `.qingcao-tasks.json` /
  根目录 `fix_*.py` / `_archive/` 的忽略。

### 测试

- 新增回归测试覆盖以上 P0/P1 修复：
  `tests/test_save_truncate.py`（6）、`tests/test_lsp_did_open.py`（10）、
  `tests/test_plugin_permissions.py`（16）、`tests/test_version.py`（13）、
  `tests/test_p1_features.py`（28）、`tests/test_lsp_integration.py`（2）、
  `tests/test_search_performance.py`（8），合计新增 83 项。
- **`tests/test_search_performance.py` 的价值已单向验证**：临时把
  `_get_line_text` 换回修复前实现后，该文件的 8 项中有 **2 项立即
  失败**（256 KB / 4 766 匹配耗时 5.31 s、1 MB 超时），且文件总耗时
  从 1.28 s 膨胀到 180.52 s；换回修复版后恢复 0.93 s 全过。
  它同时守住"每次搜索只构建一次行索引"与"不得按匹配拷贝整表"。
- **`tests/test_lsp_integration.py` 是本次最有价值的补充**：它启动一个
  真实的最小 LSP 服务器子进程，经 `QProcess` 走完
  `initialize → didOpen → didChange → didSave → didClose`，并断言
  服务端**实际收到**的 `languageId`、文本与递增版本号。它当场抓出了
  `initialize()` 的 `AttributeError` 崩溃 —— 这是纯逻辑单元测试无法
  发现的一类缺陷。
  注意：等待必须用 `pytest-qt` 的 `qtbot.waitUntil`（会驱动 Qt 事件
  循环）；用 `time.sleep` 轮询是收不到跨进程信号的。
- **`tests/test_lsp_real_server.py`（7 项，标记 `realserver`）**：
  进一步用**真实 python-lsp-server** 验证语义层 —— 握手 3.8s 完成、
  `completionProvider` 能力被正确解析、`didChange` 后版本 1→2 且
  服务器**再次推送诊断**（这正是 P0-2 的语义后果：修复前
  `version=None` 会抛 TypeError，服务器永远停在打开时的快照）、
  补全返回 **454 项**真实候选。
  因每个用例会 spawn 一个 pylsp（约 25s），已排除出默认套件：
  `python -m pytest -m realserver`。
- 修复 `tests/test_secure_storage.py::test_is_secure` 的顺序依赖：
  原断言硬编码"降级为明文"，在 keyring 可用的真实环境里会随执行
  顺序时通时不通；现改为校验"安全标记与后端类型一致"。
- **198 → 288 passed**（默认 281 + realserver 7）；`ruff check .` 0 告警。

### 打包验证（P2）

- 实际执行 `python build.py`：**成功**，`main()` 返回 0，产出
  `dist/QingCaoEditor/`（377 文件 / 137.0 MB，主程序 7.2 MB）。
- 打包产物实测可运行：`QingCaoEditor.exe --version` 输出
  **v2.1.0**（Qt 5.15.2 / PyQt5 5.15.11 / QScintilla 2.14.1），
  退出码 0 —— 这独立佐证了 P1-1 版本统一确实生效。
- `generate_icon()` 成功产出 `resources/icons/qingcao.ico`，
  即此前阻断 `installer.iss` 编译的那个文件。
  **Inno Setup (ISCC) 本机未安装，因此未实际编译安装包。**
- 新增 `.gitattributes` 统一行尾约定（库内 LF），并将
  `version_info.txt` / `*.spec` / `.pytest_cache/` 加入 `.gitignore`。

## [2.1.0] - 2026-09-24

本次更新聚焦于**跨模块代码审查修复**、**Vim 模式补全**、
**主题切换修复**、**搜索偏移修正**。

### 新增
- **Vim 模式完整实现**
  - 操作符 + 动作: `dw` / `de` / `db` / `d$` / `d0` / `dG` / `dgg`
  - 修改操作符: `cw` / `ce` / `cb` / `c$` / `cc`
  - 复制操作符: `yw` / `ye` / `yb` / `yy`
  - 文本对象: `iw` / `aw` / `i"` / `a"` / `i(` / `a(` / `i[` / `a[` / `i{` / `a{`
  - 具名寄存器: `"a` 前缀（a-z / 0-9 / " / + / * / - / _）
  - 查找重复: `n` / `N`
  - 入口: 工具菜单 → Vim 模式（`Ctrl+Shift+V`）
- **UI 测试套件** (tests/test_vim_mode.py, 11 个测试)
- 测试总数: 187 → 198

### 修复
- **主题切换核心 bug**: `themes/*.json` 无 `qss` 字段，
  `_apply_theme_by_name` 只做 `if theme.qss: setStyleSheet(...)`，
  导致全局 QSS 从未应用。改用 `loader.apply_qss()` 自动生成。
- **主题跟随不全**: 扩展 `adapt_qss_colors` 替换表，
  补充终端色 (`#0d0d0d`)、次要文字、聚焦色 (`#007acc`) 等
- **主题菜单显示**: 从文件名 (`light_clean`) 改为 `display_name` (`晨曦`)
- **字符/字节偏移**: `SearchMatch` 双写 `start/end`（字节）
  和 `char_start/char_end`（字符），修复含中文文件搜索高亮/替换错位
- **`EditorProxy.highlight_all`**: 调用不存在的 `search_all()` →
  改用 `search()`
- **`EditorProxy.search_next`**: 调用签名错误 →
  Python 层遍历 `result.matches`
- **`_search_next` 不前进**: 从 `pos` 开始 → 从 `pos+1` 开始
- **`"a` 寄存器覆盖**: 两次 alnum 输入互相覆盖 →
  加独立 `_waiting_for_register` 状态
- **`yy` 后 `p` 不粘贴**: paste 从旧 `self.register` 读 →
  改从 `registers['"']` 读
- **`SCI_WORDRIGHTPOSITION` 不存在**: `PyQt5` 未导出该常量 →
  改用 `SCI_WORDRIGHT`
- **Ctrl+Z/Ctrl+Y 被吞**: QScintilla 内置绑定占用 →
  `SCI_CLEARCMDKEY` 清除，让主窗口菜单收到
- **`Ctrl+Alt+V` 被 AltGr 解释**: Windows 上无效 →
  改 `Ctrl+Shift+V`
- **`ProjectFileEvent` 子类分派**: `Removed`/`Renamed` 被误当
  `Added` → 先检查子类
- **事件类双重定义**: `app/event_bus.py` 与 `core/events.py`
  各有 44 个同名类 → 统一从 `core.events` 重导出
- **`PluginAPI` 死信号**: `plugin_loaded` / `plugin_unloaded`
  从未 emit → 删除
- **快捷键冲突 5 处**:
  - AI 助手: `Ctrl+Shift+E` → `Ctrl+Alt+E`
  - AI 助手: `Ctrl+Shift+R` → `Ctrl+Alt+Shift+R`
  - Markdown 预览: `Ctrl+Shift+M` → `Ctrl+Alt+M`
  - Python 调试器: `F5` → `F6`
  - TODO 面板: `Ctrl+Shift+T` → `Ctrl+Alt+T`
- **每日技巧日期边界**: 手动点击也更新 `last_tip_date` →
  仅自动触发时更新
- **`outline_panel` 硬编码 50000 行**: 改用
  `large_file_threshold` 偏好推导
- **`DirectoryTree` Git 缓存 5 秒过短**: 改为 30 秒 + 可配置
- **`PythonHighlighter` 性能**: 80 条关键字正则合并为 2 条
- **`command_palette` 使用历史 key 冲突**: `title` 改为
  `action_name`
- **`sandbox_policy.DANGEROUS_MODULES` 冗余**: 移除由权限门控的
  `socket` / `shutil` / `subprocess` 等
- **LSP 位置转换**: 用 `SCI_FINDCOLUMN` → 改用字节偏移
- **pytest-qt 绑定**: PySide6 → PyQt5（避免混用崩溃）

### 变更
- **`adapt_qss_colors` 扩表**:
  - `#0d0d0d` → `background`（终端/控制台）
  - `#2a2d2e` / `#333333` / `#4c4c4c` → 面板变体
  - `#858585` / `#808080` / `#c0c0c0` → 次要文字
  - `#007acc` → `input_focus`（聚焦色）
  - `#404040` → `indent_guide`
  - `#5a5a5a` / `#8f1e1e` → 危险按钮
- `tests/conftest.py`: 设置 `PYTEST_QT_API=pyqt5`
- `EditorWidget.keyPressEvent`: 优先让 VimMode 处理

### 删除
- `PluginAPI.plugin_loaded` / `plugin_unloaded`（死信号）
- `sandbox_policy.DANGEROUS_MODULES` 中由权限门控的冗余模块
- 归档 `fix_*.py` 到 `_archive/fixes/`

### 测试
- 198 passed（187 → 198，新增 11 个 Vim 测试）

## [2.0.0] - 2026-09-19

### 新增
- 全新的 PyQt5 架构
- 完整的 LSP 客户端
- 插件系统与沙箱
- 宏录制与回放
- 多光标与列模式
- 命令面板与文件切换
- AI 助手集成
- 代码片段系统
- 主题编辑器
- 性能监控面板
- 会话快照
- 集成终端
- Git 集成
- 自动更新

### 修复
- 编辑器渲染性能
- 大文件加载
- 快捷键冲突检测

### 变更
- 从 PySide6 迁移到 PyQt5
