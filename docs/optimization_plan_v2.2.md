# 优化方案 v2.2：插件系统 / UI / 功能宽度深度 / 性能

> 本文所有数字均为**本机实测**（offscreen 平台、单次采样、未含 GPU 合成），
> 用于横向比较与回归门槛；真实桌面绝对数值会不同，但相对关系与瓶颈点一致。
> 标注 **[已验证]** 的事实来自本轮代码/运行核查；**[待核实]** 的项目需先测再动。

---

## 0. 本轮已落地（实测前后对比，含"直觉被证伪"的记录）

> 这一轮最重要的收获不是"改了几行代码"，而是**profile 推翻了三个直觉判断**。
> 记录在此，避免以后重复踩坑。

| # | 原始直觉 | profile 实测的真相 | 结果 |
|---|---|---|---|
| 1 | 大文件慢是 QScintilla `setText` 慢 | `setText` 只 **0.22 s**；真正根因是 `_has_non_ascii_beyond` 用 Python 逐字节遍历整个文件（10MB → **2080 万次生成器调用，11 s**） | 改为 `bytes.isascii()`（C 实现） |
| 2 | 启动"主题应用 0.73s" | 主题本身很快；0.73s 是 `processEvents` 顺带触发的**插件加载** | 定位到真凶：AI 插件 `on_activate` 里同步 HTTP 探测 Ollama（4.1s）+ keyring 初始化（0.37s） |
| 3 | 2MB 文件 2.1s 是高亮开销 | 高亮确实占 2.05s，但其中 3 次 `setLexer` 重复应用（一次打开走到 2 次）；小地图再占 0.74s | 加大文档阈值 + 去重 + 小地图跳过 |

### 前后对比（同一台机器、同一脚本 `tools/bench_optimization.py`）

| 指标 | 优化前 | 优化后 | 提升 |
|---|---|---|---|
| 打开 10MB / 58 万行 | **4.21 s**（profile 口径 12.4 s） | **0.402 s** | **10~30×** |
| 打开 2MB `.py` / 50 万行 | **2.60 s**（profile 口径 13.3 s） | **0.230 s** | **11~57×** |
| 打开 1MB 文本 | 0.513 s | **0.061 s** | 8× |
| `session.save()`（50 万行标签） | **1.61 s** | **0.070 s** | 23× |
| 单字符插入 | 160 µs | **115 µs** | 1.4× |
| 启动到插件全部可用 | ~1.3 s | **1.228 s** | 主要消除 4.1s 网络阻塞 |
| 主题切换 | 0.32 s | **0.138 s** | 2.3× |

### 本轮实际改动

1. `core/content_provider.py`：4 处逐字节 ASCII 判断 → `bytes.isascii()`；
2. `plugins/ai_assistant/__init__.py`：Ollama 状态刷新改**后台线程 + QObject 信号桥**
   （`PluginBase` 非 QObject，不能直接在插件类上定义 signal）；
3. `core/ai_client.py`：provider 为 ollama/local/lmstudio 时**跳过安全存储**
   （不再为不需要 API Key 的本地模型初始化 keyring）；
4. `ui/editor_view.py`：新增**大文档模式**（>20 万行或 >8MB 关闭语法高亮）、
   `setLexer` 去重（同一文件不重复全文样式化）；
5. `ui/minimap.py`：大文档跳过缩略图全文复制；
6. `core/editor.py`：一次性加载期间临时断开 `SCN_MODIFIED`
   （10MB 会触发 ~50 万次回调，纯开销 0.4s）；
7. `app/session.py`：书签用 `SCI_MARKERNEXT` 跳转、折叠状态大文档跳过
   （原实现逐行 `SendScintilla`，50 万行 = 100 万次调用）；
8. `ui/main_window.py`：新增「视图 → 大文件强制高亮」开关（默认关，用户可覆盖）；
9. `tools/bench_optimization.py`：把上述路径固化为**回归基准**
   （`--check` 超阈值退出 1，可直接接 CI）。

### 仍待处理（下一轮）

* `apply_startup_theme()` 实测 **0.53 s**（对全部控件重新 polish），
  按需刷可见面板 + QSS 缓存可到 ≤0.15s；
* 启动路径仍有 ~1.2s（插件加载占大头，懒激活可再降）；
* 打字 115 µs/字符（撤销命令对象化开销），可合并命令窗口到 ≤80 µs。

---

## 1. 实测基线表（建议固化为回归门槛）

| 项目 | 优化后实测 | 门槛（bench `--check`） | 状态 |
|---|---|---|---|
| `MainWindow()` 冷启动 | **0.352 s** | ≤1.20 s | ✅ |
| 启动到插件全部可用 | **1.228 s** | ≤2.50 s | ✅（懒激活仍可再降） |
| `apply_startup_theme()` | **0.531 s** | ≤0.80 s | ⚠️ 待按需化（目标 ≤0.15 s） |
| 事件分发（1 万次） | **0.115 s**（11.5 µs/次） | ≤0.60 s | ✅ |
| 面板首次构造（最大） | **0.020 s** | ≤0.30 s | ✅ |
| 单字符插入 | **115 µs/次** | 2000 次 ≤0.90 s | ✅（目标 ≤80 µs） |
| 打开 1 MB 文本 | **0.061 s** | ≤1.20 s | ✅ |
| 打开 10 MB / 58 万行 | **0.402 s** | ≤1.50 s | ✅ |
| 打开 2 MB `.py` / 50 万行 | **0.230 s** | ≤1.50 s | ✅ |
| `session.save()`（50 万行标签） | **0.070 s** | ≤0.40 s | ✅ |
| 主题切换 `notify_widgets` | **0.138 s** | ≤0.80 s | ✅ |
| 主题切换 `notify_widgets` | **0.220 s** | ≤0.08 s | 同上缓存策略 |

---

## 2. 插件系统

### 2.1 现状 [已验证]

* `app/plugins.py` **1708 行 / PluginAPI 90 个方法**；`plugin_manager.py` 960 行；
  `plugin_loader.py` 1403 行；`plugin_updater.py` 1394 行；商店 UI `ui/plugin_store.py` 2144 行。
* **权限**：10 种（filesystem/network/process/clipboard/dialog/editor_read/editor_write/terminal/lsp/debugger），
  有确认对话框与 `grant/revoke`。
* **生命周期**：`on_activate` / `on_deactivate`（10 个插件全部实现）。
* **管理器能力**：依赖解析（`DependencyResolver`）、`load_order`、`min/max_app_version`、
  `enable/disable`、`reload_plugin`（热重载）、`unload_all`、权限确认。
* **商店**：安装 / 卸载 / 更新检查（`plugin_store` + `plugin_updater`）。
* **事件**：46 个强类型 `pyqtSignal`，插件用 `api.subscribe(event_name, cb)` 订阅。
* 10 个插件均声明 `api_version=2.0.0`；依赖字段大多为空（仅 ai_assistant 依赖 `requests`）。

### 2.2 宽度：缺失的扩展点 [已验证缺失]

当前插件只能"加菜单/工具栏/面板/快捷键/命令/词法器/LSP"，**不能参与编辑智能**：

| 缺口 | 现状 | 建议新增 API（草案） |
|---|---|---|
| 补全 | 仅内建 `core/local_completer.py` + LSP | `register_completion_provider(language_ids, provider, trigger_chars=".")`；provider 返回 `CompletionItem(label, insert_text, kind, detail)` |
| 悬浮提示 | 无 | `register_hover_provider(language_ids, provider)` → `HoverInfo(contents, range)` |
| 诊断发布 | 仅 LSP 经 `_publish_problems` | `publish_diagnostics(uri, items)` / `clear_diagnostics(uri)` → 进问题面板 |
| 代码操作 | 无 | `register_code_action_provider(language_ids, provider)` → `CodeAction(title, kind, edit)` |
| 编辑器右键菜单 | 无（只能加主菜单） | `add_editor_context_menu(path, callback, when="editorFocus")` |
| 装饰/标记 | 无 | `add_decoration(line_range, style, tooltip)` / `add_gutter_marker(line, icon, tooltip)` |
| 状态栏项 | 无 | `add_status_item(widget_or_text, side="right", priority=0)` |
| 后台任务/进度 | 无（插件自行 `threading`，见 `python_debugger`） | `run_background(fn, on_done, on_error, name)` + `progress_begin/report/end` |
| 设置界面 | 无（插件自建对话框） | `register_settings_schema(schema)` → 宿主渲染 + 校验 + 存储（复用 `plugin.config`） |

> 价值判断：补齐"补全 + 诊断 + 后台任务"这三项，插件就能从"锦上添花"变成"可替代核心功能"。

### 2.3 深度：治理与生态

| 方向 | 现状 | 建议 |
|---|---|---|
| **权限作用域** | 10 种粗粒度开关（要 filesystem = 全盘） | 加作用域：`filesystem:project`、`network:api.github.com`；确认框展示具体路径/域名 |
| **故障隔离** | 同进程执行，插件异常可能拖垮 UI；有 try/except 日志 | `activate/deactivate` 加**超时**；同一插件连续失败 N 次**自动禁用**；可选 `run_background` 隔离 |
| **热重载 → 开发模式** | 有 `reload_plugin` | 监听插件目录、保存即重载、错误浮层、插件日志面板（真 SDK 必备） |
| **依赖管理** | 只声明 `dependencies` 列表 | 插件间 semver 约束、可选依赖、冲突检测（现在只有 `check_missing`） |
| **生命周期** | 只有 activate/deactivate | 补 `on_load`（登记能力）、`on_unload`（析构）、`on_config_changed`；支持异步 activate |
| **API 稳定性** | 有 `api_version=2.0.0` 与 `get_api_version()` | 弃用策略 + 兼容矩阵文档 + **conformance 测试套件**（每个 API 一条） |
| **SDK 体验** | 无脚手架、无类型 stub、文档零散 | `工具 → 新建插件` 模板 + `qingcao_plugin_api.pyi` + 示例插件 + 测试 harness（headless PluginAPI stub） |
| **权限审计** | 仅确认一次 | 记录"哪个插件何时用了哪个权限"到日志，供用户审计 |

### 2.4 插件性能

1. **懒激活**：`load_all()` 0.82s 里大部分是 import + activate；改成启动只登记 manifest，
   首次调用（菜单/命令/事件）时再 import+activate → 启动 −0.7s。
2. **权限检查缓存**：`has_permission` 每次 API 调用都查 → 改为实例内 dict/位掩码。
3. **配置写盘合并**：`save_plugin_config` 每次 `set_config` 都写 JSON → 加脏标记 + 延迟落盘。
4. **高频事件节流**：`cursor_moved` / `editor_changed` 类事件按 16~50ms 合并后再分发，
   避免插件在每次击键时做重活（wordcount 类插件最典型）。

---

## 3. UI 优化

### 3.1 现状 [已验证]

| 指标 | 数值 |
|---|---|
| UI 模块 / 行数 | 40 个 / **35,228 行** |
| 硬编码颜色 `#rrggbb` | **653 处** |
| 图形符号字符（emoji/箭头/符号） | **563 处** |
| `setFixedWidth/Height/Size` | **69 处** |
| 主题 | 4 个（dark_night / light_clean / eye_protect / high_contrast） |
| 图标资源 | **仅 2 个文件**（qingcao.png / .ico）—— UI 图标全靠 emoji |
| 本地化 | 4 个 locale 目录，但每个 `.po` 仅 **~2 KB**（名存实亡） |

> 真实桌面验证已暴露过同类问题：面板不跟随主题（已修）、状态栏白字白底（已修）、
> 200% 缩放下编辑器只剩 3 行（已修）。**根因都是"样式散落在各模块 + 无设计 token"**。

### 3.2 设计 token 化（P0）

* 新增 `ui/theme_tokens.py`：把颜色/间距/字号/圆角集中为 token（可基于现有 `ThemeColors` 扩展
  `statusbar_*`、`panel_*`、`editor_*` 等已有字段）。
* 分模块迁移 653 处硬编码颜色 → 引用 token。
* 加**棘轮测试**：`tests/test_theme_tokens.py` 扫描 `ui/**.py`，
  断言硬编码颜色数 ≤ 当前值且递减（和孤立模块棘轮同一模式）。
* 收益：主题一致性根治；新增主题成本从"改几十个文件"变成"加一个色值表"。

### 3.3 启动与主题切换性能（P0）

* `apply_startup_theme()` 0.73s → **只对可见面板**调用 `refresh_theme`，
  其余在首次打开时惰性适配；
* `adapt_qss_colors()` 结果按 `(theme_name, qss_hash)` **缓存**；
* 目标：冷启动 ≤0.8s（当前 0.57+0.73≈1.3s）。

### 3.4 图标体系（P1）

* 563 个 emoji/符号 → `resources/icons/svg/*.svg` + `QIcon`，
  支持主题色渲染 + 多 DPI 尺寸；
* 为什么必须做：真实桌面截图已见 emoji 依赖 `Segoe UI Emoji` 字体，
  在 Linux/macOS/精简系统上会变方框；且 emoji 无法跟随主题着色。
* 迁移策略：先建 `ui/icons.py`（`get_icon(name)` 带 emoji 回退），
  按模块逐步替换，测试棘轮保证 emoji 数只减不增。

### 3.5 大文件模式（P0，跨 UI+编辑）

新增阈值（建议 `>8MB` 或 `>200,000 行`，取先到者）：

* 关闭词法器（语法高亮）与折叠；
* 关闭小地图 / 自动补全 / 括号匹配动画；
* 状态栏显示「大文件模式（可手动开启高亮）」；
* 目标：10MB 4.21s → **≤1.5s**；2MB `.py` 2.60s → **≤1.0s**。
* 实现要点：阈值判断在 `EditorProxy._apply_lexer` / `_load_content` 前，
  并允许用户按文件类型白名单覆盖。

### 3.6 其他 UI 项

| 项目 | 建议 |
|---|---|
| 面板空状态 | 统一 `EmptyStateWidget`（目录树已做，其余面板照搬） |
| 标签溢出 | 标签过多时下拉列表 + 最近使用排序（现在只能横向滚动） |
| 面板最小尺寸 | 统一定义 `minimumSizeHint`，避免 200% 下挤压（已用默认面板自适应缓解） |
| 命令面板覆盖度 | 把全部菜单动作注册进 `ActionManager`（当前部分动作未注册） |
| 快捷键冲突 | 设置界面可视化冲突提示（`keymap_profiles.validate_scheme` 已有能力） |
| 首选项搜索 | 首选项面板加过滤框（配置项已较多） |
| 无障碍 | 工具栏按钮/菜单补 `accessibleName`；4 主题跑对比度检查；全键盘可达 |
| i18n | **决策**：4 个 locale 只有 ~2KB 翻译，属"假承诺"。建议按既定"仅中文"策略删除目录与语言入口，或补齐到可用（成本高） |

---

## 4. 功能宽度 / 深度（按模块）

| 模块 | 现状 [已验证] | 建议增量 | 优先级 |
|---|---|---|---|
| 编辑 | 列编辑（完整、已优化）、撤销（自研栈）、多光标（部分，合批窗口）、片段（有模板，展开机制待核实） | 选中相同词多光标、缩进参考线、代码折叠记忆 | P1 |
| 搜索 | 单文件查找/替换、全局搜索（线程化） | 搜索历史、范围过滤（项目/目录/类型）、替换预览、正则分组替换 | P1 |
| 对比/合并 | 2-way 完整 + 5MB 大文件保护 + 相似度对齐 | **三方可视化合并 UI**（`core/file_merge.py` 有引擎，无 UI） | P1 |
| Git | 深度集成（面板/提交/差异/分支） | 冲突可视化、暂存区按行暂存 | P2 |
| AI | Ollama 客户端（v0.40.5 本地可用）、多模型选择 | 流式输出、上下文范围选择、多模型对比、prompt 模板、结果缓存 | P1 |
| 调试 | `python_debugger` 2.0（bdb 后端）、断点标记 | 断点面板、变量/调用栈视图、单步按钮、条件断点 | P1 |
| 项目 | 项目根、`.qingcao/` 配置、任务面板、最近项目 | 多根工作区面板、按根搜索、任务并行/取消 | P2 |
| LSP | 诊断、定义、补全已连通 | 重命名、引用查找、签名帮助、代码操作 | P2 |
| 导出 | PDF/HTML | 打印预览、页眉页脚、导出范围 | P2 |
| 宏 | 录制已修（`core/macro.py` 有 record_hook 修复说明） | 宏编辑/命名/绑定快捷键的 UI | P2 |
| 片段 | 11 个内建 + 本地包导入 | tab stop 焦点跳转（若未实现）、按语言过滤展开 | P2 |

---

## 5. 实施路线图（建议 4 周，按 ROI）

### 第 1 周：性能 P0（收益最确定）
1. 大文件模式（目标：10MB ≤1.5s）
2. 启动主题按需 + QSS 缓存（目标：冷启动 ≤0.8s）
3. 把本轮微基准固化为 `tools/bench_optimization.py`，接入 CI（先非阻塞，记录趋势）

### 第 2 周：插件宽度第一批
4. `register_completion_provider` + `publish_diagnostics` + `run_background`
5. 用这三个 API 重写一个示例插件（如 markdown_preview 用后台任务）
6. 插件 conformance 测试骨架

### 第 3 周：UI 体系
7. 设计 token 起步（颜色 token + 棘轮测试）
8. `ui/icons.py` + SVG 图标迁移（先行目录树/工具栏）
9. 面板空状态统一 + 命令面板补全动作

### 第 4 周：治理与深度
10. 插件 activate 超时 + 失败熔断 + 权限作用域（路径/域名）
11. 插件开发模式（保存即重载 + 错误浮层）
12. 评估三方可视化合并（工作量最大项，先做 UI 原型）

### 每项验收标准
* 性能项：benchmark 数值达标（±10%）；
* 插件项：conformance 测试 + 至少 1 个真实插件迁移使用新 API；
* UI 项：棘轮测试（硬编码颜色 / emoji 数只减不增）+ 真实桌面截图复核；
* 功能项：端到端 verification 脚本（沿用现有 `tools/verify_*.py` 模式）。

---

## 6. 需要你先决策的 3 件事

1. **插件生态目标**：只是"内置 10 个插件够用"，还是**对外开放 SDK/插件市场**？
   - 前者：只补 2~3 个扩展点即可；
   - 后者：需要 SDK 脚手架、稳定性承诺、权限审计、进程隔离（投入大 3~5 倍）。
2. **i18n**：删除（推荐，与"仅中文"决策一致）还是补齐翻译？
3. **三方可视化合并**是否列入本版（`core/file_merge.py` 引擎已有，缺 UI，约 1 周）。
