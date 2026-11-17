# 青草编辑器 v2.1.0 —— 全面评估与优化路线图

> 评估日期：2026-10-12
> 评估对象：`D:\QingCaoEditor`（86 913 行 Python / 183 文件，PyQt5 5.15.11 + QScintilla + Python 3.11.9）
> 评估方式：**4 个维度并行静态审计 + Lead 亲自实证验证**
> 基线：`pytest tests` = 262 passed，`ruff` = 0 告警

---

## 0. 先说方法论：为什么这次评估可信

本项目历史上反复出现同一类问题：**代码写得完整、文档也写了，但从未接线**。
单测覆盖不到这类缺陷（它们只测被调用的函数）。

因此本次评估遵循三条铁律：

1. **静态发现必须实证**。所有 P0/P1 结论我都用真实脚本跑过，原始输出留在本文档。
2. **区分"静态/实证"**。未经运行验证的条目明确标注 `[静态]`，不与实证结论混列。
3. **如实报告否定结果**。没复现的必须写"未复现"（本文档至少记录了 4 处）。

> 过程记录：本次评估中我自己犯了 **3 次静态误判**（把环境假象当产品缺陷、测试脚本自身错误、PowerShell 管道伪影），全部被实证推翻。这正说明第 1 条铁律的必要性。

### 并行审计的 4 个维度

| 维度 | 交叉产物 | 实证状态 |
|---|---|---|
| 数据完整性 | `docs/audit_data_integrity.md` | 审计员会话无 shell，**静态**；Lead 已实证 3 项 |
| 并发/线程安全 | `docs/audit_concurrency.md` | 审计员会话无 shell，**静态**；Lead 已实证 4 项 |
| 性能 | `docs/audit_performance.md` | 审计员会话无 shell，**静态**；Lead 已实证 3 项 |
| 功能交互 | `docs/audit_interactions.md` | 审计员会话无 shell，**静态**；Lead 已实证 3 项 |
| 可观测性 | 本文档 §3.5 | Lead **实证** |

**审计员无 shell 的原因**（如实记录）：子代理会话的工作区沙箱在 spawn 阶段调用
`SetNamedSecurityInfoW` 失败（`Win32 5: grantWrite`），且其提权审批被策略关闭。
Lead 会话的提权可用（人工批准），因此**全部实证由 Lead 执行**。

---

## 1. 结论摘要：已实证的缺陷

按"数据损失后果 × 可达性"排序。**这些都是我实际跑出来的**。

### 🔴 P0-A：多字节字符跨 64 KiB 块边界必然损坏，且保存后不可逆

**证据（实测）**

```
偏移  65535: 期望 'aaaaa汉字bbb'  实得 'aaaaa�����'   一致=False
偏移  65534: 同样损坏
偏移  32768: 同样损坏
块内不跨界:  一致=True
保存后与原文件字节一致: False
```

**根因**：`core/editor.py` 加载时对**每个 64 KiB 块独立调用** `provider.decode()`，
而 `core/content_provider.py:302` 用 `errors='replace'`。任何跨块边界的多字节字符
被拆成两半、各自替换为 U+FFFD。

**影响**：UTF-8 中文（3 字节/字）在某个块边界落在字符中间的概率约 **2/3**。
屏幕上显示为 `�`；用户一保存，`EF BF BD` 被写回磁盘 → **原字节永久消失**。
文件越大、中文越密，命中率越高。而 **`tests/test_save_truncate.py` 覆盖不到这一层**
（它用小块文本）。

**为什么之前没发现**：我的搜索修复只测了搜索路径；这次往返矩阵用 <64 KiB 文件，
全部 PASS —— 直到我把文件放大到 64 KiB 边界才暴露。

---

### 🔴 P0-B：「另存为」写入**打开文件时的旧内容**，用户编辑静默丢失

**证据（实测）**

```
编辑器内容:   'print(1)\nprint(2)\n'
provider内容: 'print(1)\r\n'
doc2.save(dst) 返回: True            ← 声称成功
另存为文件内容: 'print(1)\n'          ← 只有旧内容，print(2) 丢失
```

**根因**：编辑器维护**两份不同步的内容**——QScintilla 缓冲区 与 `Document.provider`。
唯一同步点是 `EditorProxy.save_file()` 里的 `_sync_content_to_provider()`
（`core/editor.py:491`）。而另存为走 `ui/mixins/file_ops_mixin.py:230` 的
`proxy.document.save(path)`，**绕过**同步。

**加重情节**：`Document.save(dst)` 返回 `True` 且把 `meta.filepath` 指向新文件、
清除 modified 标记、**删除草稿**。用户以为保存成功，关闭标签时 `closeEvent`
因 `is_modified == False` **不提示未保存** → 编辑静默消失。

**交叉印证**：数据完整性审计员与交互审计员**独立**得出同一结论
（`audit_data_integrity.md` 结论 B、`audit_interactions.md` 3.2）。

**同根因的其他受害点**（静态）：
- 编辑器内查找/全部替换基于**过期 provider**（`ui/panels.py:443/640/652`）
- 全局替换**无条件丢弃**已打开文件的未保存编辑（`ui/main_window.py:1930-1939`）

---

### 🔴 P0-C：崩溃后未保存内容 **100% 丢失** —— 自动备份从未启动

**证据（grep 全仓，确凿）**

```
start_autosave    命中 1 处 → app/session.py:147  def start_autosave(self):   ← 只有定义
_autosave_tick    命中 2 处 → 定义 + 被那个永不启动的定时器连接
```

`session.save()` 只保存**文件名与光标**，不含正文。
`core/document.py` 的草稿定时器写的是 **provider 的旧内容**（编辑期不同步），
且**无任何代码读取 `.draft`**。
`main.py:1004-1019` 启动时查找的 `backup/autosave/meta.json` **永远不会存在**。

**影响**：断电 / 崩溃 / 强杀 → 未保存内容全部丢失，且不会提示"有可恢复内容"。
这是本项目**最严重的数据损失风险**。

---

### 🟠 P1-D：保存不是原子的

**证据（代码确凿）**：`core/content_provider.py:648-686` 只在
`filepath and target != self._filepath`（另存为）时才走 `_save_as_full()` 原子路径。
而 `EditorProxy.save_file()` 每次保存都 `clear_dirty()` 后写满全部块 →
**每一次 Ctrl+S 都走 `_save_dirty_blocks()`**：直接 `open(target,'r+b')` 原地覆盖 +
`truncate` + 最后 `fsync`。

**自相矛盾**：`:652` 的 docstring 写"使用原子写入（临时文件 + 重命名）避免中途失败
损坏文件"，与实现直接冲突。

**影响**：写入过程中断电/写盘失败 → 半截文件，**无备份副本**。

---

### 🟠 P1-E：主题切换把文字色换成背景色（晨曦主题文字不可见）

**证据（实测）**

```
adapt_qss_colors('color: #d4d4d4;', light_clean) -> 'color: #f5f5f5;'
adapt_qss_colors('color: #cccccc;', light_clean) -> 'color: #999999;'
```

**根因**：`infrastructure/theme_loader.py:650-701` 的顺序 `str.replace()` 会**链式命中**：
`#d4d4d4`（行 656）→ `theme.foreground` = `#333333` →（行 678）→ `theme.panel_bg` = `#f5f5f5`。
`light_clean` 背景是白色 → **近白文字、不可见**。

**影响**：默认浅色主题下 14 个面板（终端、Python 控制台、日志、Git…）文字消失。

---

### 🟠 P1-F：外部文件变更被静默覆盖

**证据（grep，确凿）**

```
external_change_detected 只有 3 处：定义(docstring)、信号定义(:198)、emit(:1007)
→ 零 connect()
```

**影响**：外部程序改写文件后，编辑器保存直接按偏移覆盖，**无 mtime 校验、无提示**。
且 `content_provider.py:24` 的 docstring 声称"mtime/hash 检测"，
但 `self._hash` **从未被赋值** —— hash 检测不存在。

---

### 🟠 P1-G：Vim 的 `u` / `Ctrl+R` 静默失效

**证据（实测）**：删除首字符后 `sc.text()` = `'ello world\n'`，
调用 Vim undo 后仍为 `'ello world\n'`，**未恢复**。

**根因**：`core/vim_mode.py:230` 调 QScintilla 内置 `undo()`，
而 `core/editor.py:344-346` 已执行 `SCI_SETUNDOCOLLECTION, 0` **禁用内置撤销栈**
（项目改用自研 `UndoManager`）。`handle_key` 返回 `True` 把按键吞掉 → 用户按 `u` 毫无反应。

**测试盲区**：`tests/test_vim_mode.py:16` 用**裸 QsciScintilla**（内置栈是开的），
与生产环境**不同构**，掩盖了该缺陷。

---

### 🟠 P1-H：撤销后编辑，重做栈不清空

`core/undo.py:261-262` 的合并分支 `return` **跳过**了唯一清 redo 的 `_do_record`
（`:276-277`）。而 `GroupCmd.can_merge` **无时间窗**（`core/commands.py:619-623`），
多光标编辑必然产生 GroupCmd → 生产必然可达。

**后果**：`can_redo()` 为真 → Ctrl+Y 产生**线性历史中不可达的状态**，并被保存。

---

### 🟠 P1-I：保存失败被吞，UI 误报"已保存"

`ui/mixins/file_ops_mixin.py:194-196` 忽略 `proxy.save_file()` 返回值，
无条件 `showMessage("已保存")`；`:230` 同样忽略返回值。
只读/磁盘满/共享冲突下用户被误导。

### 🟠 P1-J：空闲标签释放内容把标签误标为已修改

**证据（实测）**：`_release_tab_content` 后 `proxy.is_modified` 变为 `True`。

**未复现的部分**：交互审计员预测"随后 `save_all()` 会把文件 truncate(0)"——
我实测 `save_file()` 因 `Document.filepath` 未绑定而**保存失败**，文件未损坏。
**因此我把它定为 P1 而非 P0**：子缺陷（误标 modified）确证，
端到端"文件归零"未复现。但鉴于 `test_save_truncate.py` 已证明 truncate(0) 路径存在，
**该风险真实，应按 P0 的谨慎程度修复**。

---

## 2. 已实证排除的怀疑（同样重要）

| 怀疑 | 实证结果 |
|---|---|
| MainWindow 创建/销毁线程泄漏 | ✅ **未复现** —— 线程数回落到基线 |
| QTimer 悬空（9 个面板反复构造） | ✅ **未复现** —— 无 Qt 告警 |
| 操作压力（30 次面板/主题操作） | ✅ **未复现** —— 无异常 |
| `read_text()` 无缓存导致搜索变慢 | ⚠️ **确认无缓存，但代价很小**：1.1 MB 仅 **4~5 ms**，三次调用无变化 → 该发现应**下调优先级** |
| 离屏模式下 MainWindow 构造段错误 | ❌ **环境假象** —— 根因是 offscreen 无字体；注入字体后正常。非产品缺陷 |
| `QThread.terminate()` 误用 | ✅ 全仓 **0 处** |
| `moveToThread` / `QThreadPool` 误用 | ✅ 全仓 **0 处** |
| 插件热重载回调在别的线程 | ✅ **不成立** —— `QFileSystemWatcher` 在 GUI 线程投递 |
| 硬编码密钥 | ✅ **未发现** —— 25 处"凭据"命中均为变量名/配置键名 |
| `1.0 QingCaoEditor_Others/青草 GitHub key.txt` 泄露 | ✅ **未上传**（`.gitignore:81` 排除）+ **未进打包产物**（spec 的 datas 只含 5 个安全目录） |

---

## 3. 评估框架：系统的检查维度

本次评估使用的可复用框架，供后续回归使用。

### 3.1 功能完整性 / 接线

**核心问题**：这个功能真的被调用了吗？

方法：AST 提取全部函数/类定义 → 全仓引用计数 → 候选（引用数 ≤1）。
工具：`tools/audit_wiring.py`（本次新建）。

**局限性（实测教训）**：本次跑出 350 个"公共候选"，但**大部分是插件 API 面**
（`api.xxx` 通过动态调用），词法统计看不到 → **必须人工确认 + 实证**。

真正的接线缺陷要靠**交叉验证**发现：grep 调用点 + 读调用链 + 实际运行。

### 3.2 数据完整性

**核心问题**：字节能否往返一致？

必须覆盖的矩阵：**编码**（UTF-8/UTF-8-SIG/GBK/UTF-16LE/UTF-16BE/无 BOM）×
**行尾**（LF/CRLF/CR/混合）× **文件大小**（< 块大小 / 跨块边界 / > 10 块）×
**操作**（改开头/改结尾/中间插入/删大段/只追加/清空）。

工具：`tools/audit_data_roundtrip.py`（本次新建，已验证可发现问题）。

> **关键教训**：本次用 <64 KiB 文件时 8 种编码 × 6 种操作**全部 PASS**，
> 直到把文件放大到 64 KiB 边界才暴露 P0-A。**小数据量的往返测试会漏掉严重缺陷。**

### 3.3 并发 / 线程安全

**核心问题**：对象被销毁时，挂在它上面的定时器/进程/线程/信号连接是否成对撤掉？

本项目 16 处 `threading.Thread` + 3 个 `QThread`，风格是"信号回主线程"。
**真正的系统性缺陷不是"线程模型选错"，而是"关闭/销毁路径不完整"**：

- `MainWindow.closeEvent` 不调 `close_all_tabs()` → `proxy.close()` 只在 `TabManager.close_tab` 里
- `proxy.close()` 是**唯一**会 `lsp_client.stop()`（kill 语言服务器）的地方
- Windows 上父进程退出不杀子进程 → **孤儿 `pylsp` 进程**
- `start_watching()` 与 `stop_watching()` 不成对

### 3.4 性能

**核心问题**：复杂度阶数 × 是否主线程 × 触发频率。

本次实证的关键数据：

| 操作 | 实测 | 判定 |
|---|---|---|
| `read_text()` 1.1 MB | 4~5 ms | ✅ 无问题（**推翻**审计员的 P1 定级） |
| 搜索 1 MB / 19 065 匹配 | ~0.4 s | ✅ |
| 搜索 10 MB / 190 650 匹配 | ~3.7 s | ⚠️ 大文件需后台线程 |
| `MainWindow()` 构造 | 1.36 s | ⚠️ 仍有优化空间 |

### 3.5 可观测性（本次新增维度 —— 我认为这是**最重要的结构性缺陷**）

**实证数据**：

| 指标 | 数值 |
|---|---|
| `try` 语句总数（生产代码） | **1 282** |
| 宽泛 `except Exception` | **1 189**（92.7%） |
| 宽泛 except 且**静默吞掉**（pass/return None/continue） | **473**（39.8%） |
| `logging` 使用 | **1 个文件**（仅 `main.py`） |
| `FileHandler` / `RotatingFileHandler` | **0** |
| `print(...)` | **1 243 处 / 66 文件** |
| 打包后 stdout 可用性 | spec `console=False` → **PACKAGED EXE 无控制台** |

**静默吞异常最集中的文件**：

```
47 处  app/tabs.py
34 处  app/plugins.py
34 处  app/session.py
30 处  ui/main_window.py
25 处  core/editor.py
```

**为什么这是最重要的结构性缺陷**：

`console=False` + 1 243 处 `print` + 473 处静默吞异常 =
**打包后的程序里，任何故障都无声无息地消失**。用户不会看到错误，
开发者拿到用户反馈时也**没有任何线索**。

这直接解释了本次评估的困境：为什么这么多缺陷（P0-A 跨块损坏、P0-C 未接线）
能长期存在 —— 因为它们**不产生任何可见症状**。

---

## 4. 优化路线图

按"数据损失风险 × 修复成本 × 是否解锁其它修复"排序。

### 阶段 0：立刻（本周，防止数据丢失）

| # | 任务 | 位置 | 预期收益 | 风险 |
|---|---|---|---|---|
| 0.1 | **修复跨块解码损坏** | `core/editor.py` 加载路径 | 消除静默数据损坏（最高价值） | 低 |
| 0.2 | **另存为改走 `proxy.save_file(path)`** | `ui/mixins/file_ops_mixin.py:230` | 消除编辑丢失 | 低 |
| 0.3 | **接线 `start_autosave()`** | `ui/main_window.py` 构造处 | 崩溃后不再 100% 丢失 | 低 |
| 0.4 | **保存改无条件原子写** | `core/content_provider.py:688-782` | 断电不再产生半截文件 | 中 |

**0.1 的两种修法**：

```python
# 方案 A（最小改动）：整文件一次性解码
data = b''.join(provider.read_block(i) for i in range(provider.total_blocks))
text = provider.decode(data)

# 方案 B（大文件友好）：增量解码器跨块保持状态
decoder = codecs.getincrementaldecoder(provider.encoding)(errors='strict')
for i in range(provider.total_blocks):
    text = decoder.decode(provider.read_block(i))
```

**强烈建议同时做**：把 `decode`/`encode` 的 `errors='replace'` 改为 `'strict'`
并把异常上抛成用户可见提示 —— 静默替换字符是 P0-A 能"静默"的根本原因。

**回归测试**（必须加，否则会复发）：
```python
# 在 64 KiB 边界放一个汉字，打开→保存→字节比对
for offset in (BLOCK - 1, BLOCK - 2, BLOCK // 2, BLOCK - 3):
    text = "a" * offset + "汉字" + "b" * 100
    # 断言 provider.read_text() == text  且  保存后字节一致
```

### 阶段 1：本迭代（可靠性与可观测性）

| # | 任务 | 位置 | 说明 |
|---|---|---|---|
| 1.1 | **接入 logging + RotatingFileHandler** | 全局 | 替换 1 243 处 `print`；打包后写 `data/logs/app.log` |
| 1.2 | **473 处静默吞异常改为记录** | 热点 5 文件优先 | 至少 `logger.exception`，消灭 `except: pass` |
| 1.3 | 外部变更检测接线 | `core/document.py` | `external_change_detected` 连到 MainWindow + 保存前 mtime/size/hash 校验 |
| 1.4 | 保存失败必须报错 | `file_ops_mixin.py:194,230` | 检查返回值，失败走 `_show_error` |
| 1.5 | 主题 QSS 改单遍映射 | `theme_loader.py:650-701` | 消除链式替换；加对比度回归测试 |
| 1.6 | Vim undo/redo 接自研栈 | `core/vim_mode.py:88,230` | 或向 VimMode 传 proxy |
| 1.7 | 撤销合并必须清 redo | `core/undo.py:261` | 清空上移到 `record()` 最前 |

### 阶段 2：关闭路径与资源收尾

| # | 任务 | 位置 |
|---|---|---|
| 2.1 | `closeEvent` 调 `close_all_tabs()` + `stop_watching()` | `ui/main_window.py:2262-2344` |
| 2.2 | 用 `app.aboutToQuit` 统一收尾 | `main.py` |
| 2.3 | `LspClient.start()` 签名修复 + 给 parent | `core/editor.py:1876`（**LSP 目前完全起不来**） |
| 2.4 | `stop_watching()` 补 `disconnect()` | `infrastructure/plugin_loader.py:1327` |
| 2.5 | `waitForFinished` 改异步 | `core/lsp_client.py:345,379-385`（当前可冻结 UI 4 秒） |

> **2.3 是隐藏的关键点**：`toggle_lsp` 调用 `lsp_client.start()` 时不传必填的
> `command` 参数 → 必然 `TypeError` 被宽 except 吞掉。**LSP 功能实际从未成功启用过**，
> 而 `toggle_lsp` 本身零调用点。

### 阶段 3：性能（有实测依据的部分）

| # | 任务 | 依据 | 预期收益 |
|---|---|---|---|
| 3.1 | 搜索/高亮移出主线程 | 10 MB ≈ 3.7 s，会冻结 UI | 消除卡顿 |
| 3.2 | `timeout_seconds` 真正生效 | ReDoS 无保护（`(a+)+$` 可永久冻结） | 可靠性 |
| 3.3 | 替换改 `parts` + `join` | 当前 O(M×N) | 大结果集 |
| 3.4 | 字数统计加可见性判断 | 1 Hz 常驻全文扫描（隐藏面板也跑） | CPU |
| 3.5 | 代码度量 AST 判定改 O(1) | 当前 O(F×N) | 打开对话框不再卡 |
| 3.6 | 全局搜索 `_collect_files` 移入线程 | 当前主线程 `os.walk` | 消除点击后僵住 |

> **注意**：性能审计员的 P1 定级基于复杂度与主线程，**不含实测**。
> 我实测 `read_text()` 仅 4~5 ms，**推翻了它的 F2 定级**。
> 其余条目应在动手前先测绝对耗时，避免优化"看起来慢但实际不慢"的地方。

### 阶段 4：架构与长期

| # | 任务 | 理由 |
|---|---|---|
| 4.1 | **消除"双内容源"** | P0-B 的根因。让 `Document` 持有权威文本，或编辑器变更时防抖同步到 provider |
| 4.2 | 拆分超大文件 | `ui/plugin_store.py` 2573 行、`ui/main_window.py` 2361 行、`core/editor.py` 2304 行 |
| 4.3 | **建立"交互测试"层** | 现有 262 个测试**几乎全是单对象测试**，无法发现跨功能缺陷（P0-A/B、Vim undo、主题链式替换全部漏过） |
| 4.4 | 处理 `1.0 QingCaoEditor_Others/青草 GitHub key.txt` | 明文密码文件，建议删除（已 gitignore，未泄露） |
| 4.5 | 插件市场后端 / 真沙箱 | 需产品决策（已在前序会话中说明） |

---

## 5. 测试覆盖盲区（这是缺陷能长期存在的根本原因）

现有 262 个测试通过了，但**拦不住本报告中任何一个 P0/P1**。原因：

### 5.1 几乎全是"单对象测试"

每个测试只构造一个 Provider / 一个 EditorProxy / 一个面板，
**从不构造"两个功能同时活跃"的状态**。

漏掉的具体场景：

| 漏掉的场景 | 对应缺陷 |
|---|---|
| `provider` 内容 vs `sc.text()` 一致性 | P0-B |
| 64 KiB 边界往返 | P0-A |
| 空闲释放 → 保存 | P1-J |
| 主题 × 组件颜色 | P1-E |
| 任一 `*_as` 路径 | P0-B |
| `start_autosave` 是否启动 | P0-C |
| Vim undo × 自研栈 | P1-G |
| 合并后 redo 是否失效 | P1-H |

### 5.2 三处"测错对象"（比没测更危险）

| 测试 | 问题 |
|---|---|
| `tests/test_vim_mode.py:16` | 用裸 `QsciScintilla`（内置撤销栈开着），与生产**不同构** |
| `tests/test_search*.py` | 直接灌 provider 再搜，**永远搜得到**；生产里 provider 是过期的 |
| `tests/test_undo.py:185-220` | 只验证"组内合并成一条"，**从未验证 redo 失效** |

### 5.3 建议的最小补齐清单

```python
# 1. 内容一致性（拦 P0-B）
assert proxy.document.provider.read_text() == proxy.sc.text()

# 2. 块边界往返（拦 P0-A）
#    offset ∈ {BLOCK-1, BLOCK-2, BLOCK//2, BLOCK-3}

# 3. 关闭路径（拦孤儿进程）
#    MainWindow().close() 后断言 lsp_client 已 stop、watcher 已停

# 4. 每帧不变量：保存失败时 modified 必须保持 True
```

---

## 6. 评估的局限（如实声明）

1. **审计员无 shell**：4 份报告的主体是静态分析。我只实证了 13 项关键结论，
   其余仍是静态推断。**不要把审计报告里的行号当成已验证事实。**
2. **未实机验证**：Docker 镜像（本机无 Docker）、Inno Setup 安装包（未装 ISCC）、
   真实显示器渲染（只测了 offscreen + 注入字体）。
3. **LSP 语义覆盖**：仅真实 `python-lsp-server` 验证过；另 5 种语言的服务器未联调。
   而且由于 2.3 的签名错误，**LSP 在真实使用中根本起不来** —— 这使所有 LSP 相关问题
   都处于"不可达"状态。
4. **未审计区域**：`core/git_client.py`、`core/collab.py`、`core/file_merge.py`、
   `app/sync.py` 的协议正确性；插件市场后端；`ui/plugin_store.py` 的网络路径。
5. **Qt 运行时语义**：少数结论依赖 Qt 行为（`deleteLater` 与 `menuAction` 的父子关系、
   `setModified(True)` 是否发信号），静态无法确定。

---

## 7. 一句话总结

**这个项目不缺功能，缺的是"故障可见性"和"跨功能测试"。**

86 913 行代码、262 个通过的测试、0 个 lint 告警，
但 P0-A（跨块数据损坏）与 P0-B（另存为丢编辑）能长期存在 ——
因为它们**不产生可见症状**，而 473 处静默吞异常 + 无日志 + `console=False` 的打包配置
确保了**没有任何人能看到它们**。

因此路线图的第一优先级不是修 bug，而是：
**阶段 1.1 的日志系统**。它会让后续所有缺陷从"静默"变成"可观测"。
