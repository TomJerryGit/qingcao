# 青草编辑器 性能审计报告

- **审计对象**：`D:\QingCaoEditor`（PyQt5 5.15.11 + QScintilla + Python 3.11.9，约 87K 行）
- **审计角色**：性能审计员
- **审计方式**：**静态代码证据审计**（源码 + 调用链 + 复杂度推导）
- **日期**：本会话

---

## 0. 审计状态：实测数字全部缺失（必须先读）

### 0.1 阻断原因

本次审计**无法执行任何命令**，因此报告中**没有任何实测数字**。

`pwsh` 工具被沙箱阻断，每次调用都在沙箱初始化阶段失败，与本任务描述完全一致：

```
Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)
```

实际执行的命令与结果（逐条记录）：

| # | 命令 | 结果 |
|---|---|---|
| 1 | `Get-Location; Get-ChildItem -Force \| ...; python --version`（默认模式） | `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)` |
| 2 | 同上，`sandbox_permissions: "danger-full-access"` | `the user rejected escalating this command to "danger-full-access"; it stays denied` |
| 3 | `python --version`（默认模式） | `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)` |
| 4 | `python --version`，`workdir: C:\Windows\Temp` | `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)` |
| 5 | 同上，`sandbox_permissions: "workspace-write"` | `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)` |
| 6 | `subagent`（试探子代理是否有独立沙箱） | `Error: subagent depth 2 exceeds maxDepth 1` |

结论：

1. **失败点在宿主的 `pwsh` 沙箱授权步骤**，与 `workdir` 无关，与 `sandbox_permissions` 取值无关——`grantWrite` 目标恒为会话工作区 `D:\QingCaoEditor`，Win32 错误 5（拒绝访问）。这像是工作区 ACL / 卷权限与沙箱辅助进程不匹配，而非本任务可控的代码问题。
2. **提权路径被策略关闭**：本会话 `Approval prompts are disabled`，任何需要审批的调用被自动拒绝，且委派子代理的权限范围在启动时固定、无法从内部放宽。因此第 2 条命令的 `danger-full-access` 无法达成，任务描述中"必须传 danger-full-access"的前提在本会话不成立。
3. **无替代执行通道**：`subagent` 因深度上限不可用；`workflow` 同样依赖子代理，未尝试。
4. 可用的工具仅剩 `read` / `grep` / `glob` / `write` / `edit`，即**纯静态分析**。

### 0.2 这对报告意味着什么

根据本任务的铁律"**不许编造数字**，每个数字都必须来自你实际运行的命令"，本报告：

- **不包含任何我自己测出的数字**。没有 cProfile 输出、没有耗时表、没有 RSS 数字、没有 ReDoS 实测结果。
- 所有结论均标注为 **代码证据 / 复杂度推导**，可被读者用 `read` 逐条复核。
- 第 2 节（性能基线表）与第 4 节（cProfile 原始输出）按要求保留章节与表结构，单元格显式标为 **未实测（沙箱阻断）**，不留空、不猜值。
- 已附带可直接产出全部数字的脚本：`tools/bench_performance_audit.py`（本会话未运行验证）。

**建议给委派方的下一步**：在具备 shell 的环境运行

```powershell
cd D:\QingCaoEditor
python tools\bench_performance_audit.py
```

其输出可直接补全本报告第 2、4 节。若沙箱 ACL 问题可修，这是最短路径。

### 0.3 一个必须说明的例外

`core/search.py` 的注释里保存了**历史实测数字**（1 MB 搜索 >25s → 0.4s 等）。那些是代码注释中的既有记录，**不是本次审计测得的**，我在下文引用时会明确标注为"源码注释记载"。已知背景中列出的两项已修复问题（`_get_line_text` 的 O(n²)、9 面板同步构造）**未重复报告**，仅在涉及处作为对照引用。

---

## 1. 结论摘要

按"代码证据强度 × 影响面"排序。**严重度不等于已实测严重度**——因为无法测量，我依据的是复杂度阶数、是否在主线程、以及触发频率（是否每次按键）。

| 排名 | 问题 | 位置 | 复杂度 | 触发频率 | 严重度 |
|---|---|---|---|---|---|
| 1 | 全文替换每命中一次重建整个字符串 | `core/search.py:1449-1464` | **O(M×N)** | 用户操作 | P1 |
| 2 | `LocalFileProvider.read_text()` 无缓存，每次搜索都重读+重解码全文 | `core/content_provider.py:248-259` | O(N)/次 | 每次查找 | P1 |
| 3 | 查找框输入即触发**主线程**全文扫描，且**强制按正则**处理 | `core/editor.py:1427-1447` + `ui/panels.py:370-379,497-515` | O(N)/次输入 | 每次输入（300ms 防抖） | P1 |
| 4 | `timeout_seconds` 声明但**全仓库无任何检查点** → ReDoS 无保护 | `core/search.py:51,55,102` vs `604-679` | 无上界 | 每次查找 | P1 |
| 5 | 字数统计插件以 **1 Hz 永久**全量扫描当前文档（含隐藏时） | `plugins/wordcount/__init__.py:24-27,98-115` | O(N)/秒 | 后台常驻 | P1 |
| 6 | 全局搜索的文件遍历在主线程同步执行 | `core/search.py:1170-1187` + `ui/global_search_panel.py:957` | O(文件数) | 每次全局搜索 | P1 |
| 7 | 代码度量对每个函数重走整棵 AST | `core/code_metrics.py:43-52` | **O(F×N)** | 打开度量对话框 | P1 |

其余 P2：Minimap 每次切换标签整份文档拷贝（且内容从不同步）、`LogLexer.styleText` 每次样式化都 `editor.text()` 取全文、日志/替换路径的 `sc.text()[start:end]` 小切片模式下拷贝全文、`document.build_line_index` 逐字符 Python 循环、每条匹配建一个 `QTreeWidgetItem`、每文件一次进度信号、`get_info()` 逐行 `SendScintilla`。详见第 3 节。

**最关键的结构性观察**：第 1、2、3、4 条**共享同一个根因**——搜索子系统缺少"文档文本"这一层的缓存与预算控制。`SearchEngine` 实例是在每个操作里**新建**的（`ui/panels.py:443`、`ui/panels.py:605`、`core/editor.py:1446`、`ui/main_window.py:1901`），实例内的 `_text_cache`（`core/search.py:439`）随实例一起死掉；而 provider 层的 `read_text()` 每次都是"读全部块 → `b''.join` → `.decode`"。因此**每一次查找/高亮/替换都要把整个文件读进来并解码一遍**。这一条修好，第 2、3 条的大头即消失。

---

## 2. 性能基线表

> **全部单元格均为"未实测"**。原因见第 0 节：`pwsh` 沙箱阻断，无任何命令可执行。
> 表中"复杂度"一列是**代码推导**（可复核），不是测量值。
> 运行 `python tools\bench_performance_audit.py` 可填充本表。

### 2.1 启动路径

| 操作 | 实测耗时 | 是否达标 | 复杂度/证据 |
|---|---|---|---|
| `import ui.main_window` | 未实测 | — | 无基线 |
| `MainWindow()` 构造 | 未实测 | — | 源码注释记载修复前约 2.46s、修复后约 1.36s（**非本次实测**） |
| `_panels_built` 是否为空集 | **静态判定：是**（见 2.3） | 达标 | 代码证据 |
| 9 个面板逐个构造 | 未实测 | — | 凭 `tools/bench_performance_audit.py --only startup` 可得 |

### 2.2 大文件操作（1 MB / 10 MB）

| 操作 | 1 MB | 10 MB | >500ms 风险 | 复杂度/证据 |
|---|---|---|---|---|
| 打开（provider） | 未实测 | 未实测 | — | `mmap`，见 `core/content_provider.py:437-444` |
| 打开（Scintilla setText 全文） | 未实测 | 未实测 | — | O(N) |
| 滚动 | 未实测 | 未实测 | — | — |
| 语法高亮（Python lexer） | 未实测 | 未实测 | — | — |
| 语法高亮（LogLexer） | 未实测 | 未实测 | **高** | O(N) **每次** `styleText` → `core/log_lexer.py:90`（F7） |
| 代码折叠 | 未实测 | 未实测 | — | 用 Scintilla 内建折叠，无非线性点 |
| Minimap 渲染 | 未实测 | 未实测 | **高** | 每次切标签全文拷贝，`ui/minimap.py:254`（F6） |
| 大纲解析 | 未实测 | 未实测 | 中 | 每行一次 `sc.text(i)`，`ui/outline_panel.py:1434`（F13-邻） |
| 自动补全 | 未实测（**未接线**） | 未实测 | 低 | `LocalCompleter` 无 live 调用点（F19） |
| 字数统计 | 未实测 | 未实测 | **高** | 每 1 秒一次全文扫描，`plugins/wordcount/__init__.py:98-115`（F9） |
| 代码度量 `analyze_file` | 未实测 | 未实测 | **高** | **O(F×N)**，`core/code_metrics.py:43-52`（F5） |
| 代码坏味 `get_smells` | 未实测（**死代码**） | 未实测 | 无 | 无运行时调用点（F17） |
| 搜索 `SearchEngine.search()` | 未实测 | 未实测 | **高** | 每次新建 engine → 全文重读，`core/search.py:619`（F2） |
| 替换 `replace_all` | 未实测 | 未实测 | **极高** | **O(M×N)**，`core/search.py:1449-1464`（F1） |

### 2.3 惰性面板：静态确认结论

任务要求"确认惰性面板是否真的生效（`_panels_built` 应为空集）"。无法运行时验证，但**代码路径可完整判定**：

- `_build_docks()` 只做 `self._panels_built = set()` 与属性置 `None`（`ui/main_window.py:905-928`），**不调用任何 builder**。
- 9 个面板属性都是**普通属性**（`self.outline = None` 等），不是会触发构造的 `property`，因此外部读 `self.outline` 不会意外构造。
- 唯一的构造入口 `_ensure_panel()`（`ui/main_window.py:948-974`）的全部调用点为：
  `1163`（`_show_search`）、`1175`（`_show_global_search`）、`1347/1352/1357/1362/1367/1373/1380/1385`（各 `_toggle_*`）、`1495`（`_show_plugins_panel`）、`1517`（`_show_perf_monitor`）。
  经逐条读取，**这些全部是菜单/工具栏动作处理器，无一在 `__init__` 或启动路径中执行**。
- 因此：**`MainWindow()` 结束后 `_panels_built` 应为空集，惰性改造在代码层面成立**。这与已知背景"已改惰性"一致。

附带发现（非性能，供参考）：全仓库 `ui/` 无 `restoreState`/`saveState` 调用，即 dock 布局本就不持久化，所以惰性改造不会引入"布局丢失"回归。

---

## 3. 各发现的详细分析

> 每条包含：严重度 / 位置 / **实测数字** / 根因 / 建议。**"实测数字"一栏本次统一为"未实测"**，并给出可复核的代码证据与复杂度。

---

### F1 — P1 — 全文替换为 O(M×N)：每命中一次重建整个字符串

**位置**：`core/search.py:1449-1464`（`ReplaceEngine.replace_all`）
**调用点**：`ui/panels.py:640-645`（查找栏"全部替换"）、`ui/main_window.py:1906-1911`（全局替换，逐文件）

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
1449:            new_text = text
1450:            for match in reversed(result.matches):
...
1462:                    new_text = (new_text[:match.char_start] + repl +
1463:                                new_text[match.char_end:])
```

循环体内每次迭代都执行"前缀切片 + 拼接 + 后缀切片"，三者都会分配**整份文档规模**的新字符串。设文档 N 字节、命中 M 处，则总复制量为 O(M×N)，同时产生 M 次全量临时分配——这是典型的"逆向替换位置正确、但实现是二次的"写法。外层再叠加 `provider.read_text()`（`core/search.py:1445`）**又是一次全文读取+解码**，以及 `ui/panels.py:652` 的 `proxy.sc.setText(proxy.document.provider.read_text())` **第三次**全文读取与一次全量 Scintilla 重灌。

补充：`ui/main_window.py:1894-1917` 的全局替换对**每个文件**都重新 `LocalFileProvider.open` → `SearchEngine.search()`（全文重读+扫描）→ `ReplaceEngine.replace_all`（再次全文读 + O(M×N) 重建）→ `provider.save(filepath)`（全量写回）。也就是说，**同一文件在"搜"和"替"两步各被完整读了一遍，而搜索结果 `file_results` 明明是现成的**。

**建议**：

1. 改为分段拼接，一次成型：收集 `(pos, repl)` 后按顺序构造 `parts` 列表 + `''.join(parts)`，复杂度降到 O(N + M)，且只有 1 次全量分配。
2. 全局替换直接复用 `file_results` 中的 `SearchMatch`，不要重新 `search()`；把每文件 2 次全文读降为 1 次，并只在内存里改一次后写一次。
3. `ui/panels.py:652` 的 `setText(read_text())` 与替换引擎是同一份内容的来回搬运，应让 provider 变更通知编辑器做增量刷新，避免第三次全文读取。
4. 把整个替换循环移出 GUI 线程（`ui/main_window.py:1894` 无任何 `QThread`/进度回调，见 F12 邻）。

**预期收益**：替换耗时从 O(M×N) 降到 O(N+M)。M 越大收益越显著；对"每行都命中"的输入（M ∝ N），即从二次降到线性。

---

### F2 — P1 — `read_text()` 无缓存：每次搜索都重读并重新解码整个文件

**位置**：`core/content_provider.py:248-259`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
248:    def read_all(self) -> bytes:
252:        chunks = []
253:        for i in range(self._total_blocks):
254:            chunks.append(self.read_block(i))
255:        return b''.join(chunks)
256:
257:    def read_text(self) -> str:
259:        return self.decode(self.read_all())
```

`read_text()` 没有任何记忆化：每次调用都会①遍历全部块调 `read_block()`（每块从 mmap 切片出一个 `bytes` 副本，`core/content_provider.py:590`）②`b''.join` 再复制一份等长 bytes ③`.decode()` 再产出一份等长 `str`。即**单次调用约 3 份文件规模的分配**，且不留缓存。

而调用密度很高：

| 调用点 | 场景 |
|---|---|
| `core/search.py:619` | `iter_matches()` 每次搜索 |
| `core/search.py:939` | `_ensure_line_index()` 建行索引 |
| `core/search.py:895` | `_get_line_text()` 兜底 |
| `core/search.py:1049,1409,1445` | 替换/预览/写回 |
| `core/document.py:675` | `Document.get_text()` |
| `core/document.py:763` | `Document.build_line_index()` |

关键在于 **`SearchEngine` 是每次操作新建的**：

- `ui/panels.py:443` `engine = SearchEngine(proxy.document.provider, options)`（查找栏"下一个"）
- `ui/panels.py:605`（查找栏"全部替换"）
- `core/editor.py:1446`（高亮全部）
- `ui/main_window.py:1901`（全局替换，逐文件新建）

`SearchEngine.__init__` 里 `self._text_cache = None`（`core/search.py:439`），该缓存随实例销毁而失效。因此**跨操作的唯一复用层不存在**：按一次"查找下一个"，就是一次完整重读+重解码。

**建议**：

1. 在 `ContentProvider` 层加文本缓存，并用**已有的脏块机制做失效**：`read_text()` 命中缓存直接返回；`_dirty_blocks` 变化、`save`、`reload`、`close` 时置 `None`。provider 是文档级单例，缓存生命周期天然正确。
2. 或者让 `Document` 持有权威文本缓存，`SearchEngine` 从 `Document` 取文本而不是 `provider`。
3. 大文件下可考虑惰性/分块文本视图，避免为一次小范围搜索物化整个 `str`。
4. 至少应在 `read_text()` 上避免"逐块 bytes 列表 + join"的两次多余复制（mmap 可直接一次性切片 + decode）。

**预期收益**：搜索类操作从"每次 O(N) 重读 + O(N) 解码"降为首次 O(N)、之后 O(1) 取缓存；1 MB / 10 MB 下连续查找、高亮、逐次"下一个"的耗时应有数量级下降。这是投入产出比最高的一项。

---

### F3 — P1 — 查找框每次输入触发主线程全文扫描，且强制按正则处理

**位置**：`ui/panels.py:370-379`、`ui/panels.py:497-515`、`core/editor.py:1427-1447`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：调用链完整闭合于 GUI 线程，无任何线程：

```
ui/panels.py:202   self.pattern_edit.textChanged.connect(self._on_pattern_changed)
ui/panels.py:370   def _on_pattern_changed(...)  -> 需 prefs "instant_search"（默认 True）
ui/panels.py:375       self._debounce_timer.start()          # SEARCH_DEBOUNCE_MS = 300 (line 82)
ui/panels.py:176   self._debounce_timer.timeout.connect(self._do_highlight)
ui/panels.py:497   def _do_highlight(...)
ui/panels.py:512       count = proxy.highlight_all(pattern)
core/editor.py:1446        engine = SearchEngine(self.document.provider, options)
core/editor.py:1447        result = engine.search()      # 主线程：read_text() + 正则全文扫描
```

三个独立缺陷叠加：

1. **主线程扫全文**。`_do_highlight` 未起线程，`SearchEngine.search()`（`core/search.py:513`）是同步实现。用户在 10 MB 文件里打字，停顿 300 ms 即冻结界面一次。
2. **强制正则**：`core/editor.py:1445` 写死 `SearchOptions(pattern=pattern, is_regex=True)`。用户**没勾"正则"**时也按正则编译，且 `pattern` 未经 `re.escape`。后果：普通文本查找里含 `.`、`*`、`(` 等元字符会语义错误；非法正则（例如用户输入单个 `(`）会让 `compile()` 失败、`result.error` 被置位后 `highlight_all` 直接返回 0，用户看到的"匹配数"静默归零。
3. **可重入**：`core/editor.py:1467-1468` 在批量绘制中调用 `QApplication.processEvents()`。这会把控制权交回事件循环，用户在绘制期间继续打字就再次进入 `_do_highlight`，造成**递归式全文扫描堆积**。`processEvents()` 在批量循环里通常应换成 `QCoreApplication.processEvents(QEventLoop.ExcludeUserInputEvents)` 或干脆分帧处理。

**建议**：

1. 高亮走后台线程 + 结果回投，或至少按"可见区域优先"增量扫描。
2. `highlight_all` 尊重用户的 `is_regex` 选择，非正则时用 `re.escape`（`SearchOptions(escape_pattern=True)`）。
3. 去掉循环内 `processEvents()`，改为 `QTimer` 分帧或 `ExcludeUserInputEvents`。
4. 复用 F2 的文本缓存，使高亮不必重新读盘。

**预期收益**：消除"打字时周期性卡顿"这一类最影响手感的问题；配合 F2 后单次高亮成本大幅下降。

---

### F4 — P1 — `timeout_seconds` 已声明但永不生效：ReDoS 无任何保护

**位置**：声明 `core/search.py:51,55,102`；实际搜索循环 `core/search.py:604-679`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：全仓库检索 `timeout_seconds|DEFAULT_SEARCH_TIMEOUT` 只命中声明处，**没有任何读取/比较**：

```
core/search.py:51   DEFAULT_THREADS = 4
core/search.py:55   DEFAULT_SEARCH_TIMEOUT = 30
core/search.py:58   MAX_MATCHES = 1000000
core/search.py:101  max_results: int = MAX_MATCHES
core/search.py:102  timeout_seconds: float = DEFAULT_SEARCH_TIMEOUT
core/search.py:104  threads: int = DEFAULT_THREADS
core/search.py:252  if len(self.matches) >= MAX_MATCHES:
```

`iter_matches()` 的循环体只检查两件事：

```python
633:        for m in self._regex.finditer(text):
634:            if self.is_cancelled():
635:                return
636:            if count >= self.options.max_results:
637:                return
```

没有经过时间检查。而且这两道检查**在回溯阶段是无效的**——灾难性回溯发生在**单次** `finditer` 推进内部（C 层正则引擎），Python 层根本拿不到控制权，`is_cancelled()` 和 `max_results` 都来不及执行。也就是说：`(a+)+$` 这类模式一旦配上足够长的输入，**只能等它自己跑完**，`cancel()` 按钮也无效。

叠加 F3 之后后果放大：由于 `ui/panels.py:444` 与 `core/editor.py:1447` 都在**主线程**调用 `search()`，一个恶意/失误的正则会让**整个应用永久无响应**（而非只是搜不到）。

**建议**：

1. **优先**：搜索整体移到工作线程（同时也解掉 F3 的主线程问题），使 `cancel()` 至少可响应。
2. 在工作线程里用**可中断的正则引擎**：`regex` 模块（`re` 的超集，支持 `timeout=` 参数）或 Hyperscan（`core/search.py:477-493` 已有 `_compile_hyperscan`，但仅在 `use_hyperscan and is_regex` 且库存在时启用，`core/search.py:460-462`）。
3. 若坚持用 `re`，则在**分块**扫描中做时间预算检查（每块前后比对 `time.perf_counter()`），把无界单次调用切成有界多段；纯文本（非正则）路径天然安全，可不受限。
4. 现在就把 `timeout_seconds` 接上，否则它是一处**误导性的安全假象**——调用方以为设了 30 秒超时。

**预期收益**：把"应用永久冻结"降级为"搜索被超时中止并提示"，这是可靠性与可恢复性层面的修复。

---

### F5 — P1 — 代码度量 O(F×N)：对每个函数重走整棵 AST，且在 GUI 线程

**位置**：`core/code_metrics.py:43-52`；GUI 触发点 `ui/code_metrics_panel.py:138-173`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
43:    for node in ast.walk(tree):
44:        if isinstance(node, ast.ClassDef):
45:            metrics['classes'] += 1
46:        elif isinstance(node, ast.FunctionDef):
47:            # 判断是否方法（在类里）
48:            if any(isinstance(p, ast.ClassDef) for p in ast.walk(tree)
49:                   if hasattr(p, 'body') and node in p.body):
50:                metrics['methods'] += 1
51:            else:
52:                metrics['functions'] += 1
```

外层对全部节点走一遍是 O(N)。但对**每一个** `FunctionDef`，第 48 行又执行一次**完整 `ast.walk(tree)`**（O(N)），并在生成器里对每个有 `body` 的节点做 `node in p.body` 线性成员检查（O(|body|)）。设函数数 F、节点数 N，总代价 **O(F × N)**。

这是纯二次实现，而且目的极其廉价——"该函数是否为类方法"。`ast` 模块本身提供 O(1) 判定的方式：在遍历中维护类作用域栈，或一次 `ast.walk` 收集 `ClassDef` 的 `body` 集合后查表即可。

同一文件另有独立冗余：`calculate_complexity()`（`core/code_metrics.py:73-89`）对**每一行**跑 **8 次** `re.findall`（8 个决策关键字各一次），即 8× 全文正则扫描，且 `text.splitlines()` 在 `analyze_python`（第 25 行）已经在做一遍。

GUI 侧：`ui/code_metrics_panel.py:142` 与 `:170` 直接调用 `analyze_file` / `analyze_directory`，**无 QThread**（该文件内无任何线程设施）。`analyze_directory`（`core/code_metrics.py:131-175`）会遍历整个项目并为每个文件调用 `analyze_file`，于是把上述 O(F×N) 对**每个文件**执行一遍，全部阻塞在打开对话框的那一瞬间。

**建议**：

1. 把"是否方法"改为 O(1)：一次遍历收集类体，或维护作用域栈；消除内层 `ast.walk`。
2. `calculate_complexity` 合并为单次遍历：用**一个**预编译交替正则 `re.compile(r'\b(?:if|elif|for|while|and|or|except|with)\b')` 每行一次 `findall`，8× 降为 1×。
3. 复用一次 `splitlines()` 结果，避免重复切分。
4. 度量与目录分析移到工作线程，UI 显示进度。
5. 目录分析可设文件数与总字节上限。

**预期收益**：单文件度量由二次降为线性；目录级度量由 O(Σ F_i×N_i) 降为 O(总代码量)，并解除对话框阻塞。

---

### F6 — P2 — Minimap：每次切换标签整份文档拷贝，且内容从不与编辑同步

**位置**：`ui/minimap.py:254`（拷贝）、`:260-262`（共享 lexer）、`:330-346`（更新路径）；调用点 `ui/main_window.py:1789-1793`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据，两个问题）：

**(a) 每次切换标签整份拷贝。** `ui/main_window.py:1790-1793` 在 `_on_tab_changed` 中对当前编辑器调用 `self.minimap.set_editor(editor)`，而 `set_editor` 的内容搬运是：

```python
254:                self.setText(editor.text())
```

`editor.text()` 先物化一份完整 `str`，`setText` 再把这份文本灌进 Minimap 自己的 Scintilla 文档。于是**切换一次标签，内存里多一份完整文档，并做一次全量文本灌入 + 词法分析**。代码注释（第 251-252 行）说明这是为了规避 `SCI_SETDOCPOINTER` 的 Access Violation，属于不得已，但代价没有被控制。

**(b) 文本永不同步——它其实是"坏的"，不是"快的"。** 需要特别指出，Minimap 在编辑时**并不刷新文本**：

```python
283:  editor.textChanged.connect(self._on_main_text_changed)
330:  def _on_main_text_changed(self):
332:      self._schedule_update()
339:  def _do_update(self):
342:      self._update_viewport()
343:      self.repaint()
```

`_do_update` 只重算视口矩形并重绘，**没有任何 `setText`**。全文件检索 `minimap.py` 里 `setText` 仅出现在第 254 行。因此 Minimap 显示的是**上次切换标签时的旧内容**，滚动条位置指示器对着旧文本计算 `SCI_GETLINECOUNT`（第 365、411、424 行）。所以"编辑期间 Minimap 很便宜"只是因为它什么都没更新。**若按预期行为修复同步，当前设计下每次按键都会退化为一次全文拷贝**——所以这个问题的正确修法是重新设计，而不是简单补一句 `setText`。

**(c) 共享同一个 lexer 实例。** 第 260-262 行把主编辑器的 lexer 直接 `setLexer` 给 Minimap。QScintilla 的 `setLexer` 会对 lexer 调用 `setEditor(self)`，即 lexer 的归属编辑器被改成 Minimap；同一个 `QsciLexer` 被两个 Scintilla 同时使用时，样式化目标会互相抢占，等于把主编辑器的高亮置于未定义状态，并造成重复词法分析工作。

**建议**：

1. 用**轻量自绘**替代"第二个 QScintilla"：直接读取可见区域若干行并在 `paintEvent` 里画色条，成本与行数而非字节数相关；这也顺带解决同步正确性。
2. 若必须保留 Scintilla 实例，则①给 Minimap 独立 `setLexer(克隆的 lexer)` 而非共享；②改为**增量**更新（监听 `SCN_MODIFIED`，只替换受影响行区间），不要整份 `setText`。
3. 加"大文件自动禁用 Minimap"的阈值开关（例如超过 `large_file_threshold` 就不建 dock）。
4. 视口指示器改用主编辑器的行数，不要依赖 Minimap 自己那份可能过期的文档。

**预期收益**：消除每次切标签的整份文档复制与重复词法分析；恢复 Minimap 内容正确性（当前是静默错误）。

---

### F7 — P2 — `LogLexer.styleText` 每次样式化都取全文再切片

**位置**：`core/log_lexer.py:90`（配合 `:96-100` 的规则循环）

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
82:    def styleText(self, start, end):
84:        self.startStyling(start)
...
90:        text = editor.text()[start:end]
...
96:        for pattern, style in self._rules:
97:            for m in pattern.finditer(text):
```

这是**与已知已修复的 `search.py::_get_line_text` 完全同一类**缺陷：为了拿到 `[start:end]` 这一小段，先执行 `editor.text()` **物化整份文档**，再切片丢弃绝大部分。QScintilla 会对可见/变更区间反复调用 `styleText`，因此对 N 字节日志，一次完整样式化的总代价约 O(N) × 调用次数，退化为二次；且每次调用都产生一份 N 字节临时 `str` 供 GC 回收。

**正确写法在仓库内已有范例**：`core/editor.py:1278` 使用 `self.sc.text(start_pos, end_pos)`（区间重载）。此处应同样写成 `editor.text(start, end)`，即**不要**先 `text()` 再切片。详见 F14 的说明。

另注（需实测确认，我不敢断言）：`styleText(start, end)` 的 `start`/`end` 是 Scintilla 的**字节位置**，而 Python 侧 `editor.text()` 返回的是 `str`；对含非 ASCII（中文）的日志，用字节下标去切 `str` 本身就存在**字符/字节错位**风险，即除了慢还可能标错位置。改用 `editor.text(start, end)` 可一并回避该疑点——因为区间换算交由 QScintilla 处理。

第 96-100 行还对 7 条规则各做一次 `finditer` 全文扫描，其中 `\b\d+\b`（第 72 行）会命中所有数字，是 7 条里最贵的一条；这些正则本身**没有嵌套量词**，回溯风险低（见第 3 节 ReDoS 用例）。

**建议**：

1. 改为 `editor.text(start, end)`（仓库内既有惯用法），只取所需区间。
2. 合并 7 条规则为一次性扫描（如按 token 分类），减少重复遍历。
3. 对超大日志设样式化上限（例如超过阈值只高亮可见区）。

**预期收益**：日志高亮的单位成本从"全文"降到"区间"，删掉每次调用的 N 字节临时分配。

---

### F8 — P2 — `save_file` 单次保存两次全文拷贝 + 逐行列表化

**位置**：`core/editor.py:473`、`479-480`、`487-488`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
473:            text = self.sc.text()                     # 第 1 次全文
478:            if settings.value("trim_trailing_whitespace", True, type=bool):
479:                lines = [l.rstrip() for l in text.splitlines()]   # 全量列表
480:                text = '\n'.join(lines)               # 再拼回全文
...
487:            if text != self.sc.text():                # 第 2 次全文
488:                self.sc.setText(text)                 # 可能再全量重灌
```

一次保存里 `self.sc.text()` 被调用两次（第 473、487 行），每次都是一份完整文档的 `str`；中间还额外产生 `splitlines()` 的整表 + `join` 的全文。第 487 行只为做一次相等判断而重新物化全文——完全可以用已持有的 `text` 与"是否发生了 trim/换行变化"的布尔标志来替代。

同类冗余还存在：`trim_trailing_whitespace`（`:1823-1828`）与 `remove_blank_lines`（`:1836-1841`）各做一次 `text()` + `splitlines` + `join` + 可能的 `set_text`。

**建议**：

1. 删除第 487 行的第二次 `self.sc.text()`，改为用第 478-484 行是否实际改动了文本的标志判断。
2. 需要整体重写时用 `QScintilla` 的 `beginUndoAction/endUndoAction` 包住，避免多次重排。
3. `trim_trailing_whitespace` 等批量编辑考虑走 Scintilla 原生命令或只改受影响行，而不是全量 `set_text`。

**预期收益**：保存路径的峰值内存与拷贝次数约减半；保存大文件时的大块临时分配减少。

---

### F9 — P1 — 字数统计插件以 1 Hz 永久全量扫描当前文档（含面板隐藏时）

**位置**：`plugins/wordcount/__init__.py:24-27`（定时器）、`:98-115`（`refresh`）；文本来源 `app/plugins.py:376-381`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
24:        self.timer = QTimer(self)
25:        self.timer.setInterval(1000)
26:        self.timer.timeout.connect(self.refresh)
27:        self.timer.start()
```

```python
 98:    def refresh(self):
103:            text = self.api.get_current_text()
107:            chars = len(text)
108:            chars_no_space = len(re.sub(r'\s', '', text))
109:            words = len(text.split())
110:            lines = text.count('\n') + 1 if text else 0
111:            paragraphs = len([l for l in text.split('\n') if l.strip()])
```

而 `app/plugins.py:380`：

```python
380:            return editor.sc.text()
```

即每次 `refresh()` 都会：

1. `sc.text()` → **一份完整文档 `str`**；
2. `re.sub(r'\s', '', text)` → 一次全文正则替换，**只为取长度**，却物化了第二份近乎全长的字符串；
3. `text.split()` → 全文分词，产生一个包含所有词的**列表**；
4. `text.split('\n')` + 列表推导 → 又产生一个包含所有行的**列表**。

这个函数**每秒无条件执行一次**。`refresh()` 内**没有可见性判断**，定时器一旦启动就常驻；而面板是懒创建的（`_ensure_panel`，第 155-161 行），所以只要用户**曾经打开过一次**字数统计面板，此后即使把 dock 关掉，后台仍会永远每秒全量扫描当前文档。对于 10 MB 文档，这相当于每秒固定产生数份 10 MB 级临时对象并做多趟全量扫描——用户完全感知不到，只表现为持续的 CPU 占用与 GC 压力。

**建议**：

1. `refresh()` 首行判可见性：`if not self.isVisible(): return`（或用 `showEvent`/`hideEvent` 启停定时器）。
2. 只在**文本变化后**重算：连接编辑器的 `textChanged`/脏标记，或对 `document` 维护递增版本号，版本未变则直接返回。
3. 用**单遍**统计替代多次全量：一次遍历得到字符/非空白/行/段落，避免 `re.sub` 与两个大列表；词数统计可用 `str.count` + 状态机或按需增量。
4. 用 `SCI_GETLENGTH`、`SCI_GETLINECOUNT` 直接向 Scintilla 取字符/行数（O(1)），不做全文物化。
5. 定时器间隔拉长或改为事件驱动。

**预期收益**：消除一个**常驻的、每秒一次的 O(N) 全文扫描**。这是本次审计中"用户无感但持续消耗"最典型的一处。

---

### F10 — P1 — 全局搜索的目录遍历在主线程同步执行

**位置**：`core/search.py:1170-1187`（`FileSearcher.search`）、`:1305-1340`（`_collect_files`）；调用点 `ui/global_search_panel.py:957`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：`FileSearcher.search()` 的顺序是"**先收集文件，再起线程**"：

```python
1170:        # 收集文件列表
1171:        try:
1172:            files = self._collect_files(
1173:                root_dir, file_filter, exclude_dirs, include_hidden
1174:            )
...
1181:        # 启动后台线程
1182:        self._worker = threading.Thread(
1183:            target=self._do_search,
1184:            args=(files, options),
1185:            daemon=True,
1186:        )
1187:        self._worker.start()
```

`_collect_files`（`:1305-1340`）是一个**完整的阻塞 `os.walk`**，在最坏情况下还要对 `dirnames` 做列表重建与对每个文件名执行 `fnmatch`（`:1334`、`1356-1362`，`fnmatch` 内部会编译/匹配通配符）。而 `ui/global_search_panel.py:957` 是在**GUI 线程**直接调用 `self.searcher.search(...)` 的。

后果：用户点"搜索"后，在 worker 线程启动**之前**，界面已经因为遍历整个目录树而冻结。目录越大（或越冷、越分散在慢盘上），冻结越久，而且此时**进度条还停在 0、取消按钮尚未生效**（`_cancel_event` 只被 `_do_search` 检查，见 `:1242`），用户既没反馈也取消不了。

**建议**：

1. 把 `_collect_files` 一并移入 worker 线程，或做成"边遍历边发射文件、边搜索"的流式管线。
2. 让 `cancel()` 在收集阶段也可生效（`os.walk` 循环内检查 `_cancel_event`）。
3. 文件收集结果可做目录级缓存（配合 F14 的缓存治理），但注意失效策略。

**预期收益**：消除"点搜索后先僵住一段时间"的体验问题，并让取消在最早阶段生效。

---

### F11 — P2 — 每个文件发一次进度信号：大型仓库下事件循环被灌满

**位置**：`core/search.py:1258`（配合 `:1241-1258`）

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
1241:            for i, filepath in enumerate(files):
...
1258:                self.search_progress.emit(i + 1, total)
```

`search_progress` 是 `FileSearcher`（`QObject`）的信号，发射方是 `threading.Thread` 里的 `_do_search`，接收方是 GUI 线程的 `GlobalSearchPanel`。跨线程且默认 `AutoConnection` ⇒ **每个文件一次 queued 事件**。设仓库有 F 个文件，就会向 GUI 事件队列投递 F 个进度事件（外加每个有命中的文件的 `file_result.emit`，`:1255`）。

万级文件的仓库意味着万级事件涌入事件循环，进度条更新本身（`_on_search_progress`，`ui/global_search_panel.py:986`）会成为 GUI 负载的主要来源，甚至导致搜索线程跑完了界面还在追进度。

**建议**：

1. 节流：仅在进度变化超过阈值（如每 1% 或每 50 ms）时才发射。
2. 用共享计数器 + GUI 侧 `QTimer` 轮询，替代每文件信号。
3. `file_result` 同样批量化（与 F12 合并考虑）。

**预期收益**：事件队列长度从 O(文件数) 降到 O(1)；大仓库搜索期间界面更跟手。

---

### F12 — P2 — 每条匹配建一个 `QTreeWidgetItem`，且全局替换阻塞主线程

**位置**：`ui/global_search_panel.py:251-283`（逐匹配建项）、`:979`（结果到达）；`ui/main_window.py:1894-1917`（全局替换）

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

**(a) 逐匹配建项。** `add_file_result` 对 `matches` 里**每一条**匹配执行一次 `QTreeWidgetItem(file_item)` 并设置 6 个 `setData` + 3 个 `setText` + `setFont` + `setForeground`：

```python
251:        for match in matches:
252:            match_item = QTreeWidgetItem(file_item)
253:            match_item.setData(0, Qt.UserRole + 1, NODE_TYPE_FILE)
...
273:            match_item.setText(0, line_text)
274:            match_item.setText(1, str(match.line))
275:            match_item.setText(2, str(match.col))
278:            font = match_item.font(0)
279:            font.setBold(False)
280:            match_item.setFont(0, font)
283:            match_item.setForeground(0, QBrush(QColor("#cccccc")))
```

`QTreeWidgetItem` 是重量级对象，且 `setFont(0, font)` 会触发字体解析与项数据同步。注意 `MAX_MATCHES = 1000000`（`core/search.py:58`），而 `add_file_result_batch`（`:290`）虽存在，主路径走的是逐条版本。结果是"匹配数"直接决定建项数与控件开销，且这项工作在 GUI 线程、由后台线程的结果信号驱动逐文件进行。

**(b) 全局替换无进度、无线程。** `ui/main_window.py:1894-1917` 对每个受影响文件：新建 `LocalFileProvider` → `open` → `SearchEngine.search()`（**又一次全文重读+扫描**）→ `ReplaceEngine.replace_all`（**再次全文读 + O(M×N) 重建**，见 F1）→ `provider.save`（全量写回）。整段循环在 GUI 线程内，**没有任何进度回调或取消入口**，且它甚至没有复用 `file_results` 里现成的匹配。

**建议**：

1. 结果树改为**虚拟/惰性渲染**：只渲染展开的文件节点，或采用 `QTreeView` + 自定义 model + `fetchMore` 增量加载。
2. 对匹配数设硬上限（例如每文件最多渲染 N 条 + "还有 M 条"提示），前提是搜索仍可导出完整结果。
3. 复用 `file_results` 做替换，去掉重复 `search()`；把替换循环移到工作线程并加进度/取消。
4. 批量建项时用 `setUpdatesEnabled(False)` 包裹（`_render` 在 `ui/outline_panel.py:1471` 已有该模式，可借鉴）。

**预期收益**：大结果集从"卡住若干秒"降到可交互；全局替换从"无反馈冻结"变成可观察、可取消。

---

### F13 — P2 — `document.build_line_index` 用逐字符 Python 循环，且每次重建都重读全文

**位置**：`core/document.py:763-767`（构建）、`:743-746`（失效）

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
763:        text = self.provider.read_text()
764:        index = [0]
765:        for i, char in enumerate(text):
766:            if char == '\n':
767:                index.append(i + 1)
```

两个问题：

1. **逐字符 Python 级循环**。对 N 字节文本是 N 次解释器循环迭代。而同一仓库里 `core/search.py:946-948` 的正确写法是 C 层 `str.find` 循环：

   ```python
   946:            pos = text.find('\n')
   947:            while pos >= 0:
   948:                index.append(pos + 1)
   ```

   两者相差一个数量级以上的常数因子，且记忆体分配模式也不同。

2. **重建即重读全文**。第 763 行调用 `provider.read_text()`，而该方法无缓存（F2）。索引在 `:287, :325, :352, :476, :697, :738` 六处被 `_invalidate_line_index()` 置脏。因此"任一编辑动作使索引失效 → 下次 `build_line_index()` 重读并重新解码整个文件 + 逐字符重扫"。

   缓解事实（必须说明，避免夸大）：我检索了 `get_line_count` / `get_position_line_col` / `get_line_text` / `get_line_start` / `get_line_end` 的调用点，`ui/` 下**没有**对 `Document` 这些方法的调用（`ui/editor_view.py:1265,1275` 用的是 Scintilla 自身的 `get_line_count()`，即 `SCI_GETLINECOUNT`）。当前命中只出现在 `core/document.py:1638-1641` 的 `__main__` 演示块与 `tests/`。**因此它目前不是一个"每次都触发"的热路径**，而是一处**高风险潜伏点**：任何未来在按键路径上调用 `document.get_line_count()` 的改动，都会立刻变成 O(N)/次按键。

**建议**：

1. 改用 `text.find('\n')` 循环（直接复用 `core/search.py:946-948` 的实现，或把该逻辑抽成共享工具）。
2. 与 F2 一并解决 `read_text()` 缓存，使索引重建不再重读磁盘。
3. 若将来需要按键级查询，改为增量维护（记录编辑位置的偏移增量）而不是整体失效。

**预期收益**：索引构建常数因子显著下降；配合 F2 后重建成本再降一个数量级；消除该潜伏点被误用的风险。

---

### F14 — P2 — 用小切片却物化全文：`sc.text()[start:end]` 模式多处残留

**位置**：`core/editor.py:1083`、`core/editor.py:1568`、`core/vim_mode.py:488`、`:521`、`:755`

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：与 F7、以及与已知已修复的 `search.py::_get_line_text` 同源的模式——为取一个很短的目标（一个词、一个选区），先 `sc.text()` 物化整份文档再切片：

- `core/editor.py:1083` `sel_text = self.sc.text()[start:end]`（当前单词，通常 < 20 字符）
- `core/editor.py:1568` `word = self.sc.text()[start:end]`（当前单词）
- `core/vim_mode.py:488` `text = self.editor.text()[start:end]`
- `core/vim_mode.py:521` `text = self.editor.text()[start:end_with]`
- `core/vim_mode.py:755` `text = self.editor.text()[start:end]`

其中 vim 的三个点位于**按键驱动**的文本对象操作路径上（按一次键 → 一次全文拷贝）。

**关键证据：正确写法就在同一个文件里。** `core/editor.py:1278`（`duplicate_line`）用的是 **`QsciScintilla.text()` 的区间重载**：

```python
1277:            # 修复：使用 Python API 获取文本
1278:            text = self.sc.text(start_pos, end_pos)
```

该文件 1244-1246 行的修复说明"使用 self.sc.text() 替代 SCI_GETRANGE"，指的正是"改用 Python 的 `sc.text(start, end)` 区间重载、不再手写 `SCI_GETRANGE`"。也就是说：

- `sc.text(start, end)` 是本仓库**已经采用并验证过的正确惯用法**（区间取值，不物化全文）；
- 同一文件内 `:1083`、`:1568` 却写成 `sc.text()[start:end]`（先全文再切片），**与 200 行外的既有写法不一致**——这更像遗漏，而非有意选择；
- `ui/minimap.py:473` 也已在用 `self.text(line)` 单行重载，说明这些重载是可用且已知的。

（更正说明：我最初把 1244-1246 行的注释误读为"项目知道该用 SCI_GETRANGE"。实际语义相反——项目是**从** `SCI_GETRANGE` **迁移到** `sc.text(start,end)`。这不削弱本发现，反而给出了一处仓库内可直接对照的正确范例。）

**建议**：把这批 `sc.text()[start:end]` 统一改为 `sc.text(start, end)`（或 `selectedText()`）；在 `EditorProxy` 上加一个 `get_range(start, end)` 帮助方法把这批调用点收敛，避免以后再次扩散。**不要**建议回退到 `SCI_GETRANGE`——那正是本项目此前刻意迁移掉的做法。

**预期收益**：这些调用点的成本从 O(N) 降到 O(区间长度)，对"按键触发"的 vim 路径尤其明显。

---

### F15 — P2 — `EditorWidget.get_info()` 逐行调用 `SendScintilla` 统计折叠行

**位置**：`ui/editor_view.py:1274-1279`（被 `:1284` `dump()` 与 `:1291` `__repr__()` 调用）

**实测数字**：未实测（沙箱阻断）。

**根因**（代码证据）：

```python
1274:            'folded_lines': sum(
1275:                1 for i in range(self.get_line_count())
1276:                if not self.SendScintilla(
1277:                    QsciScintilla.SCI_GETFOLDEXPANDED, i
1278:                )
1279:            ),
```

对**每一行**发起一次 `SendScintilla` 跨语言调用（SIP 边界开销，微秒级/次），行数 L 时即 L 次调用。10 万行的文件意味着 10 万次跨边界调用。

风险点在于可达性：`get_info()` 被 `__repr__()` 调用，因此**任何**对编辑器控件的 `repr()`/`str()` ——包括调试日志、异常消息格式化、Qt 的调试输出、`print(widget)`——都会触发这 L 次调用。这类调用常常出现在故障路径上，恰是最不该卡住的地方。当前 `ui/` 内未检索到对 `EditorWidget.get_info()`/`dump()` 的常规调用点，故列为 P2 潜伏缺陷。

**建议**：

1. `folded_lines` 改为按需计算（单独的 `count_folded_lines()`），从 `get_info()` 里移除。
2. `__repr__()` 只输出 O(1) 字段，绝不触发全行扫描。
3. 若确需全量统计，用 Scintilla 的折叠状态批量接口或缓存结果。

**预期收益**：消除 `repr()`/日志路径上的 O(行数) 跨边界调用风暴。

---

### F16 — P2（默认关闭，条件性）— 光标拖尾每次移动清空全文指示器

**位置**：`ui/editor_view.py:856-871`，开关默认 `False`（`ui/editor_view.py:176`、`app/preferences.py:111`）

**实测数字**：未实测（沙箱阻断）。**注意：该特性默认关闭，因此当前默认配置下不产生开销。**

**根因**（代码证据）：

```python
859:            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
...
865:            length = self.SendScintilla(QsciScintilla.SCI_GETLENGTH)
866:            self.SendScintilla(
867:                QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_CURSOR_TRAIL
868:            )
869:            self.SendScintilla(
870:                QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length
871:            )
```

`_on_cursor_moved`（`:850-854`）由 `cursorPositionChanged` 触发，即**每次光标移动**（含每次按键导致的列变化）。开启时，每次都会用 `SCI_INDICATORCLEARRANGE, 0, length` **清除整个文档区间**的指示器——清除代价与区间长度相关，于是每次按键都触碰全文范围。正确做法是只清除上一批拖尾点所在的小区间（`_cursor_trail_points` 里已有这些位置，见 `:875-881` 的遍历）。

另注 `core/editor.py:1616-1645` 存在**第二份重复实现**，且第 1620 行每次调用都读一次 `QSettings`（`settings.value("cursor_trail", False, type=bool)`）；`core/editor.py:807` 会调用它。建议一并合并去重。

**建议**：只清除上一帧记录的拖尾区间；把 QSettings 查询结果缓存为实例字段。

**预期收益**：开启该特性时，每次光标移动的开销从 O(N) 降到 O(拖尾点数)。

---

### F17 — 潜伏（当前无运行时开销）— `core/code_smell.py` 是死代码

**位置**：`core/code_smell.py`（整文件），重点 `:149-175`

**实测数字**：未实测。**关键静态结论：无任何运行时调用点。**

**代码证据**：全仓库检索 `code_smell` 只命中 `build.py:407` 的打包模块清单；检索 `get_smells|SmellDetector` 只命中其自身定义（`core/code_smell.py:20,178,180`）。即该模块被列入打包清单，但**没有任何模块导入或调用它**。

因此其中的性能特征**当前不产生任何用户可感开销**，我不将其列为 P1/P2。但记录在此，因为它一旦被接线就会立刻成为问题：

```python
154:        for i in range(len(self.lines) - self.MIN_DUPLICATE_LINES):
156:            block = '\n'.join(self.lines[i:i + self.MIN_DUPLICATE_LINES]).strip()
...
164:            if block in seen:
...
175:                seen[block] = i
```

`seen` 字典保存**每一个不同的 5 行窗口**的完整文本副本——即常驻内存约为文档的 5 倍量级（外加 dict 与 str 对象开销），且是 O(行数) 次 `'\n'.join` 分配。若将来接上，建议改为滚动哈希（如对 5 行窗口做 `tuple` 化或 hash）避免保存原文。

附带一处**功能失效**（非性能）：`_check_nesting`（`:130-147`）通过 `getattr(parent, 'parent', None)` 向上走，但 `ast.parse` 生成的标准节点**没有 `parent` 属性**，故 `depth` 恒为 0，`deep_nesting` 永远不会被报告。这是死分支。

---

### F18 — 潜伏（当前无运行时开销）— `LocalCompleter.update_from_file` 从未被调用

**位置**：`core/local_completer.py:45-70`

**实测数字**：未实测。**关键静态结论：`update_from_file` 无调用点。**

**代码证据**：全仓库检索 `update_from_file|_extract_words` 只命中 `core/local_completer.py:45,51,66`（定义及其内部调用）。`LocalCompleter` 本身**是**被使用的（`core/usage_stats.py:282-283,462-463`、`ui/usage_stats_panel.py:274-275` 通过 `get_local_completer()` 取用），但它们只用词频读取接口，不触发全文抽取。

因此下面这个模式**当前不产生开销**：

```python
69:        pattern = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]{1,40}\b')
70:        return pattern.findall(text)
```

两点说明：①正则**每次调用都重新编译**（第 69 行在函数体内），应提到模块级；②一旦有人把 `update_from_file` 接到"保存/切换文件/按键"上，就是一次全文正则扫描（而且 `file_words` 按文件路径累积、**无上限淘汰**，长期运行会持续增长）。

另有 `get_completions` 的小规模二次行为：`:103` 与 `:109` 的 `word not in [r[0] for r in results]` 每轮重建结果列表（O(R²)），但结果集受 `most_common(50/100)` 与 `limit` 约束，量级小，优先级低。

**建议**：接线前先把正则提到模块级；给 `file_words` 加 LRU/容量上限；`get_completions` 用 `set` 去重。

---

## 4. cProfile 原始输出

**未获取。** 原因见第 0 节：`pwsh` 在沙箱授权阶段即失败，无法执行 `python -m cProfile` 或任何脚本。

本节保留结构，以下是**应当执行的命令**与**预期产出**（预期清单来自静态阅读，非实测）：

### 4.1 启动路径

```powershell
cd D:\QingCaoEditor
$env:QT_QPA_PLATFORM = "offscreen"
python -c "import cProfile,pstats,io; from PyQt5.QtWidgets import QApplication; from PyQt5.QtGui import QFontDatabase; QFontDatabase.addApplicationFont(r'C:\Windows\Fonts\consola.ttf'); a=QApplication([]); from ui.main_window import MainWindow; p=cProfile.Profile(); p.enable(); w=MainWindow(); p.disable(); s=io.StringIO(); pstats.Stats(p,stream=s).sort_stats('cumulative').print_stats(15); print(s.getvalue()); print('panels_built=', getattr(w,'_panels_built',None))"
```

或直接：

```powershell
python tools\bench_performance_audit.py --only startup
```

### 4.2 大文件操作

```powershell
python tools\bench_performance_audit.py --only bigfile --size 10
python tools\bench_performance_audit.py --only bigfile --size 1
```

### 4.3 ReDoS 与内存

```powershell
python tools\bench_performance_audit.py --only redos
python tools\bench_performance_audit.py --only memory
```

### 4.4 关于 `tools/bench_performance_audit.py`

该脚本由本次审计编写，覆盖本报告第 2 节表格的全部行项，并额外：
- 对 `provider.read_text()` 做"第 1 次 vs 第 2 次"对比，用于**直接证实 F2 无缓存**；
- 对 `ReplaceEngine.replace_all` 单独计时，用于**证实 F1 的二次行为随 M 增长**；
- ReDoS 用 `multiprocessing` 子进程 + 超时（10 s），**避免把审计机本身挂死**；
- 内存用 `psutil.Process().memory_info().rss` 分步记录增量。

**重要声明**：该脚本**在本会话中从未运行过**，未经任何验证。可能存在导入路径、API 名称或逻辑错误。请把它当作待调试的起点，而不是可信工具；若报错，请以报错为准并修正后使用。

---

## 5. 未覆盖 / 不确定

### 5.1 因环境阻断而完全未覆盖

| 项目 | 状态 |
|---|---|
| 任何实测耗时（1 MB / 10 MB 全部操作） | **未测** — 无 shell |
| 启动 cProfile 热点排序（任务要求 1） | **未测** |
| `_panels_built` 运行时取值 | **未测**（静态判定为空集，见 2.3） |
| ReDoS 恶意输入实测（任务要求 3） | **未测** |
| RSS 内存增长（任务要求 4） | **未测** |
| "耗时超过 500 ms"的操作清单 | **未测** — 摘要表给的是风险判断，非测量 |
| 滚动性能 | **未测** |
| Python 语法高亮（QsciLexerPython）实际开销 | **未测** |
| 代码折叠实际开销 | **未测** |
| 大纲解析实际开销 | **未测** |
| 自动补全实际开销 | **未测**（且已确认无 live 调用点） |

### 5.2 已确认的死代码 / 无运行时开销（避免误报）

- `core/code_smell.py` 整模块无调用点（F17）——`_check_duplicates` 的内存特征**当前不成立**。
- `core/local_completer.py::update_from_file` 无调用点（F18）。
- `ui/editor_view.py` 光标拖尾默认关闭（F16）。

如果后续有人把这些接上，F16/F17/F18 会从"潜伏"升级为实际缺陷。**请勿把这三条计入当前性能预算。**

### 5.3 静态分析无法判定、需要实测才能确认的点

1. **F1 的常数因子**：`O(M×N)` 的阶数由代码确定，但"多慢"完全取决于 M 与 N 的实际组合。M 较小时它可能并不显眼。
2. **F9 的真实 CPU 占用**：每秒一次 O(N) 扫描的绝对代价取决于 N 与 CPU；我只能确定它**无条件周期性执行**，不能确定它占多少 CPU 百分比。
3. **F10 的冻结时长**：`os.walk` 的耗时对磁盘类型、目录规模、冷热缓存极度敏感，必须实测。
4. **F2 的收益上限**：取决于单次 `read_text()` 相对正则扫描的占比。若正则扫描远贵于读取解码，则缓存收益被稀释（但仍为正）。
5. **`ui/outline_panel.py:1434` 的 `lines = [sc.text(i) for i in range(n)]`**：这是逐行 `SendScintilla` 取行（上限 `max_lines`，`ui/outline_panel.py:1423-1424` 由 `large_file_threshold` 推出，默认可达 200000 行）。它是 O(行数) 次跨边界调用，但每次取值量小；我**未测**其与"一次性取全文再 split"孰优孰劣，故未列为独立发现。建议在基准脚本中单独计时。
6. **信号节流（F11）与建项（F12）的实际卡顿**：取决于匹配总数，未测。
7. **`core/editor.py:1616-1645` 与 `ui/editor_view.py:856-881` 两份光标拖尾实现的取舍**：我只确认存在重复实现与每次读 `QSettings`，未测其影响（默认关闭）。

### 5.4 未审计区域（超出本次重点，或与性能无关）

- `core/lsp_client.py`、`core/git_client.py`、`core/collab.py`：LSP/Git/协作的启动与同步开销**未审**。这些模块含子进程与网络，可能有独立的性能问题。
- `ui/plugin_store.py`、`ui/theme_market.py`：含 `QThread` worker（`ui/plugin_store.py:1356`、`ui/theme_market.py:67`），网络路径**未审**。
- 主题/QSS 应用开销（`infrastructure/theme_loader.py`，含 `_theme_cache`）：**未审**。
- `app/plugins.py` 插件加载与 `build.py` 打包：**未审**。
- 并发正确性由另一份审计负责（`docs/audit_concurrency.md`，当前仍是占位文件）。

### 5.5 关于严重度标注的诚实说明

本报告把 F1-F5、F9、F10 标为 P1，依据是**复杂度阶数（二次/无界）+ 是否在主线程 + 触发频率（是否每次按键或每秒）**，而**不是**实测耗时。若实测显示某个 P1 的绝对耗时很小（例如 M 很小使 F1 不显著），应下调其优先级。

**我没有、也不能给出"某某操作耗时 XXX ms"这样的数字。** 任何看起来像测量值的地方，请以第 0 节为准：它们都不存在。

---

## 附：修复优先级建议（按投入产出比）

1. **F2（provider 文本缓存）** —— 单点修复，同时惠及 F3、F5-邻、F13 的搜索/高亮/替换路径。最高性价比。
2. **F9（字数统计可见性 + 事件驱动）** —— 改动极小（几行），消除一个常驻的每秒全文扫描。
3. **F1（替换改 `join` 分段）** —— 改动小，把二次降为线性。
4. **F4 + F3（搜索移出主线程）** —— 一并解决主线程冻结与 ReDoS 不可取消；顺带让 `timeout_seconds` 有意义。
5. **F5（AST 判定改 O(1)、复杂度正则 8 合 1）** —— 改动小，直接消除二次。
6. **F10 / F11 / F12（全局搜索管线）** —— 改动中等，收益在大型仓库场景。
7. **F6（Minimap 重新设计）** —— 改动较大，但同时修掉一个静默的正确性缺陷。
8. **F7 / F14（区间取值收敛）** —— 机械替换，可批量做，并应抽成共享帮助方法防止再次扩散。
9. **F8 / F13 / F15 / F16 / F17 / F18** —— 顺手清理项。
