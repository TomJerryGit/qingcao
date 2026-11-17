# 功能交互与状态一致性审计报告 —— 青草编辑器 (QingCaoEditor)

- 审计对象：`D:\QingCaoEditor`（PyQt5 代码编辑器；Python 3.11.9 / PyQt5 5.15.11 / Windows）
- 审计员角色：**功能交互与状态一致性**审计员（独立于开发方）
- 报告文件：`docs/audit_interactions.md`（UTF-8）
- 配套测试：`tests/test_audit_interaction_{undo,state,theme,file_io,macro,plugin}.py`

---

## 0. 关于「实证」的诚实声明（请先读这一节）

**本次审计没有执行过任何一条 shell 命令，因此本报告中不存在任何真实的运行输出。**

### 0.1 实际发生的阻塞（原始输出，逐字复制）

审计会话的 `pwsh` 工具在**进程启动阶段**就失败，与命令内容完全无关：

```
Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)
```

我实际尝试过的全部路径（**全部失败，不是没试**）：

| # | 命令 | 参数 | 原始结果 |
|---|---|---|---|
| 1 | `Get-Location; Get-ChildItem -Directory` | 默认 | `Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)` |
| 2 | `python -c "import sys; print(sys.version)"` | 默认 | 同上 |
| 3 | `echo test` | 默认 | 同上 |
| 4 | `Get-Location` | `workdir=$env:TEMP` | 同上（沙箱仍对工作区根目录授权） |
| 5 | `python -c "print(1)"` | `run_in_background=true` | 后台作业 `pwsh-1007` → `status: failed`，`job_output` 仍是同一行错误 |
| 6 | `cd D:\QingCaoEditor; Get-Location` | `sandbox_permissions="danger-full-access"` + 中文 justification | `Error: the user rejected escalating this command to "danger-full-access"; it stays denied` |

**根因（推断，未验证）**：沙箱在 spawn 子进程前调用 `SetNamedSecurityInfoW` 给
`D:\QingCaoEditor` 授予写权限，当前账户缺少对该目录的 `WRITE_DAC`，得到 Win32 5（拒绝访问）。
本会话策略明确写明 `Approval prompts are disabled in this session`，
且我作为被委派的子代理「权限范围在启动时固定、无法从内部拓宽」，
因此**没有任何可用的绕过途径**。这是环境缺陷，不是我命令写错。

我也尝试了唯一的替代执行通道：调用 `subagent` 让子代理去跑测试，
被拒绝 —— `Error: subagent depth 2 exceeds maxDepth 1`。

### 0.2 由此产生的报告性质（必须让读者知道）

- 本报告的**全部结论来自静态代码审计**：用 `read` 逐行读代码、用 `grep` 核对调用链与全仓引用点。
- 每条发现都标注 **`静态定位，未动态复现`**。第 2 节矩阵里「实测」一列**全部是 `未执行`**；
  「静态判定」列是代码推导的**预测**，不是观测值。请勿把预测当实测引用。
- 我**真实编写**了 6 个 pytest-qt 测试文件（见第 6 节），每个断言都写明了不变式与失败原因。
  **这些文件本身也从未被执行过**，可能存在笔误 —— 它们的价值是「待跑」，不是「已跑」。
- 因此本报告中 **`未复现` 与 `确认存在` 是两种不同强度的结论**，我在每条发现里都明确区分。
- 需要交叉参考：同仓库另有 `docs/audit_data_integrity.md`（数据完整性审计员），
  它记录了同样的沙箱阻塞，并独立得出与我第 3.2 节一致的「另存为写入旧内容」结论。
  下文凡与之重合处，我标注为 **交叉印证（两名审计员独立静态复读同一代码路径）**。

### 0.3 我"读到了什么"作为替代性原始证据

无法运行，所以我把证据降到"可被别人复查的源码事实"：

- 每条发现都给出 `文件:行号` 与**逐字代码片段**（我从 `read` 的真实输出里抄的，未改写）；
- 每条发现都给出**全仓引用点统计**（例如"`convert_eol` 只有 1 处定义、0 处调用"），
  这是 `grep` 的真实输出，属于可复核的客观事实；
- 每条发现都给出**最小复现步骤**，并写明期望结果与（预测的）实际结果。

---

## 1. 结论摘要（最严重的 5 个交互缺陷）

### 摘要 1 — P0：后台标签内存回收 × 保存 = **文件被写成 0 字节**（数据丢失）
`TabManager._release_tab_content()`（`app/tabs.py:1490-1528`）对闲置 >30 分钟的标签直接调用
`widget.clear()`。这个 clear 会触发 `SCN_MODIFIED`，被 `EditorProxy._on_scintilla_modified`
**当成"用户编辑"**记录进撤销栈并把 `proxy._modified` 置为 `True`。
此后 `save_all()` / 关闭标签时选"保存"，`EditorProxy.save_file()` 读取的是**已被清空的
`sc.text()`（空串）**，`_sync_content_to_provider("")` 写一个长度 0 的脏块，
`LocalFileProvider._save_dirty_blocks` 执行 `f.truncate(0)` → **磁盘文件变空**。
两个功能单独看都正常（内存回收正常、保存正常），组合起来摧毁用户文件。

### 摘要 2 — P0：「另存为」写入的是**打开文件时的旧内容**，用户在编辑器里做的一切全部丢失
`EditorProxy` 自始至终维护**两份不同步的内容**：Scintilla 缓冲区 与 `Document.provider`。
唯一同步点是 `EditorProxy.save_file()` 里的 `_sync_content_to_provider()`
（`core/editor.py:491`、`528-552`）。而「另存为」走的是
`ui/mixins/file_ops_mixin.py:230` 的 `proxy.document.save(path)` —— **完全绕过**同步，
直接把 provider 里那份"打开时的快照"写到新路径。
同一根因还导致：编辑器内查找/全部替换基于过期内容（`ui/panels.py:443/640/652`）、
全局替换丢弃未保存编辑（`ui/main_window.py:1930-1939`）。
**交叉印证**：`docs/audit_data_integrity.md` 结论 B 独立得出同一结论。

### 摘要 3 — P1：Vim 模式的 `u` / `Ctrl+R` **静默失效**（撤销诉求被吞掉）
`core/vim_mode.py:230` 调 `self.editor.undo()`、`:88` 调 `self.editor.redo()`，
这里的 `self.editor` 是 QScintilla 控件（`ui/main_window.py:1539` `editor = proxy.sc`）。
但 `EditorProxy._connect_signals` 在 `core/editor.py:344-346` 执行了
`SCI_SETUNDOCOLLECTION, 0` **彻底禁用 Scintilla 内置撤销栈**，
改用自研 `UndoManager`。于是 Vim 的 undo/redo 是空操作，
而 `handle_key` 返回 `True` 把按键吞掉（`ui/editor_view.py:507-513`）——
用户按 `u` 什么都不会发生，也收不到任何提示；菜单里的 Ctrl+Z 却是好的。

### 摘要 4 — P1：撤销后编辑，重做栈不清空 → **Ctrl+Y 产生"历史上从未出现过"的内容**
`UndoManager.record()` 的合并分支 `if self._try_merge(command): return`
（`core/undo.py:261-262`）**在 `_do_record` 之前返回**，而清空 redo 栈的代码
只在 `_do_record` 里（`core/undo.py:276-277`）。
两条合并路径都不清 redo：
- `_pending_group` 时间窗合并（`core/undo.py:334-353`，窗口由 `merge_interval` 控制）；
- 与栈顶命令合并（`core/undo.py:358-379`，`InsertCmd.can_merge` 用硬编码 200ms，
  `GroupCmd.can_merge` **没有任何时间窗**，`core/commands.py:619-623`）。

后者在生产代码里必然发生：多光标/列模式编辑会被包成 `GroupCmd` 记录
（`core/editor.py:695-711`），两个 `GroupCmd` 永远合并。
后果：`can_redo()` 返回 True，UI 把"重做"置为可用，执行后内容错乱。

### 摘要 5 — P1：主题切换把"文字色"换成了"背景色"（晨曦主题文字不可见）
`infrastructure/theme_loader.py:650-701` 的 `adapt_qss_colors` 是一串**顺序执行**的
`str.replace()`。前面的替换会**产生**新的 hex 字符串，而这些新字符串又命中列表中**后面的**条目：

```
#d4d4d4  --(行 656)-->  theme.foreground  --(行 678)-->  theme.panel_bg
#cccccc  --(行 657)-->  theme.tab_fg      --(行 659)-->  theme.line_number_fg
```

`light_clean`（晨曦）里 `foreground="#333333"`（行 436）、`panel_bg="#f5f5f5"`（行 482），
于是原本写 `#d4d4d4` 的**所有文字**（终端、控制台、日志、Git 面板……共 14 个面板的
`refresh_theme` 都调用这个函数）被换成 `#f5f5f5` —— 与面板背景同色，**文字消失**。

> 其余 8 条 P1/P2 发现见第 3 节。

---

## 2. 交互矩阵（功能对 × 结果）

**结果图例**
- `缺陷(静态)` = 静态审计判定存在交互缺陷，**未动态复现**
- `通过(静态)` = 静态审计未发现交互缺陷
- `未测` = 本次未覆盖（原因见第 5 节）

「实测」列全部为 `未执行`（见第 0 节）。

| # | 功能对 | 静态判定 | 实测 | 依据 |
|---|---|---|---|---|
| 1 | 撤销 × 命令合并（InsertCmd 200ms 窗） | **缺陷(静态)** P1 | 未执行 | `core/undo.py:261,276,358-379` |
| 2 | 撤销 × 命令合并（GroupCmd，无时间窗） | **缺陷(静态)** P1 | 未执行 | `core/commands.py:619-623` |
| 3 | 撤销 × `_pending_group` 时间窗 | **缺陷(静态)** P2 | 未执行 | `core/undo.py:334-353`（注：生产代码未调用 `begin_group`） |
| 4 | 撤销 × 搜索替换（面板全部替换） | **缺陷(静态)** P0 | 未执行 | `ui/panels.py:640-653` |
| 5 | 撤销 × 全局搜索全部替换 | **缺陷(静态)** P1 | 未执行 | `ui/main_window.py:1930-1939` |
| 6 | 撤销 × Vim 模式（u / Ctrl+R） | **缺陷(静态)** P1 | 未执行 | `core/vim_mode.py:88,230` + `core/editor.py:344-346` |
| 7 | 撤销 × 宏回放 | **缺陷(静态)** P1 | 未执行 | `core/macro.py:702-707,619-626` |
| 8 | 撤销 × 外部文件变更（重载） | **缺陷(静态)** P1 | 未执行 | `app/tabs.py:1399-1458` |
| 9 | 撤销 × 后台标签内存回收/恢复 | **缺陷(静态)** P1 | 未执行 | `app/tabs.py:1490-1528`、`1092-1096` |
| 10 | 撤销 × LSP 重命名 | **未测** | 未执行 | 见第 5 节 |
| 11 | 撤销 × 格式化（formatter） | **未测** | 未执行 | 见第 5 节 |
| 12 | 标签切换 × 搜索高亮/匹配计数 | **缺陷(静态)** P2 | 未执行 | `ui/panels.py:531`、`ui/main_window.py:1755-1807` |
| 13 | 标签切换 × LSP 诊断（跨标签泄漏） | **缺陷(静态)** P2 | 未执行 | `core/editor.py:1951`（不校验 uri） |
| 14 | 标签切换 × 折叠/书签/光标 | **缺陷(静态)** P2 | 未执行 | `app/tabs.py:1490-1528`（clear 后未恢复指示器） |
| 15 | 标签切换 × minimap / 大纲 | 通过(静态) | 未执行 | `ui/main_window.py:1769-1795` 每次切换都重设 |
| 16 | 标签切换 × 语法高亮 | 通过(静态) | 未执行 | 每个 EditorWidget 持有自己的 lexer |
| 17 | 主题切换 × 编辑器背景/前景 | 通过(静态) | 未执行 | `theme_loader.apply():920-921` |
| 18 | 主题切换 × 自定义高亮色（QSS） | **缺陷(静态)** P1 | 未执行 | `theme_loader.py:650-701` 链式替换 |
| 19 | 主题切换 × 编辑器偏好（高亮当前行） | **缺陷(静态)** P2 | 未执行 | `theme_loader.py:927` vs `editor_view.py:269` |
| 20 | 主题切换后再编辑 | 通过(静态) | 未执行 | 主题不触碰 undo 链路 |
| 21 | 编码切换 × 保存 | **缺陷(静态)** P1 | 未执行 | `status_bar_mixin.py:177-188` + `document.py:593-615` |
| 22 | 行尾切换 × 保存 | **缺陷(静态)** P1 | 未执行 | `document.py:620-623`、`convert_eol` 为死代码 |
| 23 | 编码/行尾 × 再次打开是否保持 | **缺陷(静态)** | 未执行 | 同上（写盘未变，重开自然回退） |
| 24 | 另存为 × 编辑器内容 | **缺陷(静态)** P0 | 未执行 | `file_ops_mixin.py:230` ∈ 摘要 2 |
| 25 | 另存为 × 修改标记 `*` | **缺陷(静态)** P2 | 未执行 | `file_ops_mixin.py:230` 不调 `setModified(False)` |
| 26 | 另存为 × LSP URI | **缺陷(静态)** P1 | 未执行 | `core/editor.py:218,770-780,2018-2028` |
| 27 | 另存为 × 文件监听器（watcher） | **缺陷(静态)** P2 | 未执行 | `app/tabs.py:1334-1342` 未迁移路径 |
| 28 | LSP × 关闭标签 | 通过(静态) | 未执行 | `app/tabs.py:694-698` → `proxy.close()` → `did_close` |
| 29 | LSP × 文件被外部删除 | **缺陷(静态)** P2 | 未执行 | `app/tabs.py:1348-1353` 只提示，未清 LSP/撤销 |
| 30 | 插件热重载 × 菜单项 | **缺陷(静态)** P1 | 未执行 | `app/plugins.py:592-602,1537-1542` |
| 31 | 插件热重载 × 工具栏/快捷键 | 通过(静态，有隐患) | 未执行 | `app/plugins.py:676,1554-1562`；`deleteLater` 兜住了 parent 不匹配的问题 |
| 32 | 插件热重载 × 事件订阅（cleanup） | 通过(静态) | 未执行 | `app/plugins.py:842-849` |
| 33 | 插件 `unsubscribe` × 已订阅事件 | **缺陷(静态)** P2 | 未执行 | `app/plugins.py:817-836` 映射表缺 9 个事件 |
| 34 | 自动保存 × 未保存内容 | **缺陷(静态)** P1 | 未执行 | `start_autosave()` 全仓 0 处调用 |
| 35 | 会话恢复 × 修改标记 | **缺陷(静态)** P2 | 未执行 | `app/session.py:266` vs `550-702` |
| 36 | 退出 × 未保存标记 | **缺陷(静态)** P2 | 未执行 | `ui/main_window.py:2301-2305` 只有 Discard/Cancel |
| 37 | 崩溃恢复 × TabManager 注册/修改标记 | **疑似(静态)** P2 | 未执行 | `app/session.py:1087-1098` |
| 38 | 编码切换 × 行尾显示组件 | 通过(静态) | 未执行 | 两者独立更新状态栏 |

---

## 3. 逐项发现

> 每条格式：**严重度 · 状态 → 涉及文件:行号 → 机制 → 最小复现 → 原始证据 → 影响 → 建议修法**
> 「原始证据」= 我从 `read` 真实输出里逐字抄下的代码 + `grep` 的全仓引用统计。

### 3.1 【P0】后台标签内存回收 × 保存 → 文件被清空（0 字节）

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `app/tabs.py:72` — `IDLE_RELEASE_MINUTES = 30`
- `app/tabs.py:202-205` — 空闲定时器**无条件启动**
- `app/tabs.py:1463-1488` — `_check_idle_tabs()`
- `app/tabs.py:1490-1528` — `_release_tab_content()`（**缺陷源头**）
- `app/tabs.py:1581-1603` — `save_all()`（触发点之一）
- `app/tabs.py:1589-1599`、`617-644` — 关闭标签时的保存触发点
- `core/editor.py:645-739` — `_on_scintilla_modified`（把释放误判为编辑）
- `core/editor.py:461-526` — `save_file()`（读取被清空的 `sc.text()`）
- `core/content_provider.py:688-782` — `_save_dirty_blocks`，截断在 `749-750`

**机制（逐步）**

1. `_release_tab_content` 的前置检查只看 `is_modified` 和 `len(text) >= 1000`：

```python
1503:            if is_modified:
1504:                return
1505:
1506:            # 内容太短不释放
1507:            text = widget.text()
1508:            if len(text) < 1000:
1509:                return
1510:
1511:            # 缓存内容
1512:            self._released_content[widget] = text
1513:
1514:            # 清空编辑器
1515:            widget.clear()
```

2. `widget.clear()` 是 `SCI_CLEARALL`，会发出 `SCN_MODIFIED(SC_MOD_DELETETEXT)`。
   `EditorProxy._on_scintilla_modified` 只在 `self._undoing or self._restoring` 时提前返回
   （`core/editor.py:657-658`），而 `_release_tab_content` **两个标志都没设**，所以：

```python
718:            self.undo_manager.record(cmd)
719:
720:            # 标记文档为已修改
721:            if not self._modified:
722:                self._modified = True
723:                self.document.mark_modified()
724:                self.modified_changed.emit(True)
```

   → 一个**纯内存优化动作**把标签变成了"已修改"。

3. `save_all()` 遍历所有 `proxy.is_modified` 的标签并保存：

```python
1597:                if getattr(widget.proxy, 'is_modified', False):
1598:                    widget.proxy.save_file()
```

4. `save_file()` 取 `self.sc.text()`（此时是**空串**）→ `_sync_content_to_provider("")`
   → `provider.write_block(0, b"")` → 脏块 `{0: b''}` 是**非空 dict**，
   所以 `LocalFileProvider.save` 不会走 `if not self._dirty_blocks ... return True` 的短路
   （`core/content_provider.py:666-668`），而是进入 `_save_dirty_blocks`：

```python
724:        # 落盘后的真实长度（脏块覆盖范围的最大末尾）
725:        new_size = 0
726:        for block_id, data in self._dirty_blocks.items():
727:            new_size = max(
728:                new_size, block_id * self._block_size + len(data)
729:            )
...
745:                try:
746:                    on_disk = os.fstat(f.fileno()).st_size
747:                except Exception:
748:                    on_disk = self._size
749:                if new_size < on_disk:
750:                    f.truncate(new_size)
```

   `new_size = 0 < on_disk` → **`f.truncate(0)`，文件归零。**

**最小复现步骤（可贴进报告让别人复现）**

前置：把 `app/tabs.py:72` 的 `IDLE_RELEASE_MINUTES` 临时改成 `0`（或直接调用私有方法）。

```python
from app.tabs import TabManager
p = r"D:\tmp\big.txt"
open(p, "w", encoding="utf-8").write("x" * 2000 + "\n")

tabs = TabManager()
proxy = tabs.open_file(p)
widget = tabs.widget(0)
assert proxy.is_modified is False        # 刚打开，干净

tabs._release_tab_content(widget)        # 等价于闲置 30 分钟后自动触发
print(repr(widget.text()))               # -> ''
print("is_modified =", proxy.is_modified) # -> True  ← 缺陷 1（被误标为已修改）

tabs.save_all()                          # 等价于「全部保存」
print(os.path.getsize(p))                # -> 0     ← 缺陷 2（文件被清空）
```

**期望**：`is_modified` 仍为 `False`（用户没改过），`os.path.getsize(p)` 仍为 2001。
**预测实际**：`True` / `0`。

**原始证据（grep 全仓引用统计）**

```
$ grep -n "IDLE_RELEASE_MINUTES\|_check_idle_tabs\|_released_content" -r .
app\tabs.py:72:IDLE_RELEASE_MINUTES = 30        # 后台标签闲置多久后释放内容
app\tabs.py:178:        self._released_content: Dict[Any, str] = {}
app\tabs.py:202:        self._idle_timer = QTimer(self)
app\tabs.py:203:        self._idle_timer.setInterval(IDLE_CHECK_INTERVAL_MS)
app\tabs.py:204:        self._idle_timer.timeout.connect(self._check_idle_tabs)
app\tabs.py:205:        self._idle_timer.start()
app\tabs.py:705:        self._released_content.pop(widget, None)
app\tabs.py:1092:            if widget in self._released_content:
app\tabs.py:1094:                    widget.setText(self._released_content.pop(widget))
app\tabs.py:1463:    def _check_idle_tabs(self):
app\tabs.py:1477:            if widget in self._released_content:
app\tabs.py:1487:                if elapsed > IDLE_RELEASE_MINUTES * 60:
app\tabs.py:1512:            self._released_content[widget] = text
app\tabs.py:1530:    def force_release_idle(self):
```
→ 定时器**无任何开关**，`TabManager()` 一构造就启动，生产路径必然可达。

**影响**
用户把一个大文件（>1000 字符）切到后台 30 分钟，再执行「全部保存」或关闭该标签时选
"Save"，磁盘文件被**清空**。而且清空**没有任何备份**（`start_autosave()` 从未被调用，见 3.14）。
这是不可逆的数据丢失。

**建议修法**
1. `_release_tab_content` 必须把释放动作标记为"程序内部变更"，与 `EditorProxy` 已有的
   机制对齐：

```python
proxy._restoring = True            # 让 _on_scintilla_modified 提前返回
try:
    self._released_content[widget] = text
    widget.clear()
finally:
    proxy._restoring = False
proxy._modified = False
widget.setModified(False)
```
2. 更稳妥：**直接不要 clear QScintilla 控件**（`setText("")` 同样有副作用），
   改为把内容换成一个占位文档，或干脆去掉这个"内存优化"（现代机器上 1 MB 级文档不值得）。
3. `EditorProxy.save_file` 增加防御：若 `sc.text()` 为空而 `document.meta.size > 0`
   且 `provider` 有内容，拒绝写盘并报错 —— 让"清空"永远不会静默发生。
4. 增加回归测试：`tests/test_audit_interaction_state.py::TestIdleReleaseVsSave`。

---

### 3.2 【P0】「另存为」写入旧内容 —— 编辑器缓冲区与 `Document.provider` 双内容源

**状态：静态定位，未动态复现。（与 `docs/audit_data_integrity.md` 结论 B 交叉印证）**

**涉及文件:行号**
- `ui/mixins/file_ops_mixin.py:202-238`，关键行 `230: proxy.document.save(path)`
- `core/editor.py:461-526` `save_file()`；`528-552` `_sync_content_to_provider()`
- `core/editor.py:645-739` `_on_scintilla_modified()`（**不碰 provider**）
- `core/document.py:359-446` `save()`；`699-738` `_replace_full_content()`
- `core/content_provider.py:648-686` `save()`；`815-884` `_save_as_full()`（→ `read_all()`）

**机制**

全仓 grep 证明：**没有任何生产代码在编辑过程中把 Scintilla 的内容写回 provider。**

```
$ grep -n "_sync_content_to_provider\|document\.set_text\|write_text(" -r core ui app
core\editor.py:491:            self._sync_content_to_provider(text)     # 仅 save_file 调用
core\editor.py:528:    def _sync_content_to_provider(self, text: str):
core\editor.py:540:        provider.clear_dirty()
core\editor.py:546:            provider.write_block(bid, encoded[start:end])
core\document.py:677:    def set_text(self, text: str):
core\document.py:694:            self._replace_full_content(text)
```
`core/document.py:set_text` 在整个 `core/ ui/ app/` 下**没有任何调用点**
（grep `document.set_text` 只命中 `tests/` 与 `core/document.py` 自身的 `__main__`）。

于是「另存为」这条链路：

```python
202:    def _save_file_as(self):
...
224:            path, _selected = QFileDialog.getSaveFileName(
225:                self, "另存为", filepath, filters
226:            )
227:
228:            if path:
229:                # 通过 document 保存到新路径
230:                proxy.document.save(path)
```
`Document.save(path)` 用 `is_save_as` 分支（`core/document.py:403-407`）更新
`meta.filepath`，然后由 `provider.save(target)` → `_save_as_full(target)` 执行
`full_data = self.read_all()`（`core/content_provider.py:821`）——
`read_all()` 读的是 mmap + 脏块，而**脏块是空的**（没人 `write_block`），
所以拿到的是**打开文件那一刻的原始字节**。

**最小复现步骤**

```python
from PyQt5.Qsci import QsciScintilla
from core.document import Document
from core.editor import EditorProxy

open(r"D:\tmp\src.py", "w", encoding="utf-8").write("print(1)\n")

sc = QsciScintilla(); sc.setUtf8(True)
proxy = EditorProxy(sc, Document())
proxy.open_file(r"D:\tmp\src.py")

# 用户在编辑器里打字（不点保存）
sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()), b"print(2)\n")
print(repr(sc.text()))                                  # 'print(1)\nprint(2)\n'

# 复现 ui/mixins/file_ops_mixin.py:230 —— 「另存为」
proxy.document.save(r"D:\tmp\dst.py")

print(repr(open(r"D:\tmp\dst.py", encoding="utf-8").read()))
# 期望: 'print(1)\nprint(2)\n'
# 预测实际: 'print(1)\n'      ← 用户输入全部丢失
```

**原始证据（关键代码，逐字抄录）**

```python
# ui/mixins/file_ops_mixin.py:228-235
228:            if path:
229:                # 通过 document 保存到新路径
230:                proxy.document.save(path)
231:
232:                # 更新标签标题
233:                idx = self.tabs.currentIndex()
234:                if idx >= 0:
235:                    self.tabs.setTabText(idx, os.path.basename(path))
```

```python
# core/editor.py:471-494  —— 只有这条路径会同步
471:        try:
472:            # 获取文本
473:            text = self.sc.text()
...
490:            # 更新提供者内容
491:            self._sync_content_to_provider(text)
492:
493:            # 保存
494:            success = self.document.save(filepath)
```

**同一根因的其他交互（同一条发现族）**

| 功能 | 位置 | 后果 |
|---|---|---|
| 编辑器内「查找下一个」 | `ui/panels.py:443` `SearchEngine(proxy.document.provider, options)` | 查不到刚输入的文字 |
| `EditorProxy.search_next` / `highlight_all` | `core/editor.py:1446`、`1504` | 同上 |
| 编辑器内「全部替换」 | `ui/panels.py:640-653`，`652: proxy.sc.setText(proxy.document.provider.read_text())` | 用旧快照**覆盖编辑器**，未保存编辑丢失 |
| 全局搜索「全部替换」 | `ui/main_window.py:1919-1939`，`1933: w.proxy.document.reload()` + `1935: w.proxy.sc.setText(...)` | 不检查 `is_modified`，**强制丢弃已打开文件的未保存修改**，且不清理撤销栈 |
| 「另存为」 | `ui/mixins/file_ops_mixin.py:230` | 写旧内容 |

全局替换的丢弃是**无条件**的（`ui/main_window.py:1930`）：

```python
1930:                if fp and os.path.abspath(fp) in abs_paths:
1931:                    try:
1932:                        if w.proxy.document:
1933:                            w.proxy.document.reload()
1934:                        if w.proxy.sc and w.proxy.document:
1935:                            w.proxy.sc.setText(
1936:                                w.proxy.document.get_text()
1937:                            )
```
这里既没有 `is_modified` 检查，也没有 `undo_manager.clear()`。

**影响**
P0 级数据丢失；同时"查找"这类最基础的功能在存在未保存编辑时给出错误的搜索结果，
用户会以为文字不存在从而重复输入。

**建议修法**
1. **收敛为单一内容源**。最省事的正确做法：给 `EditorProxy` 加一个
   `_flush_to_provider()`，在**每次**读取 provider 之前调用，并在
   `_on_scintilla_modified` 里用防抖（例如 `QTimer` 200ms）持续同步：

```python
def _sync_provider_now(self):
    """把编辑器当前文本写回 provider（幂等）。"""
    text = self.sc.text()
    if self.document.provider and self.document.provider.read_text() != text:
        self._sync_content_to_provider(text)
```
2. `_save_file_as` 改为 `proxy.save_file(path)`（复用已有同步 + `setModified(False)` +
   `_notify_lsp_saved` + `FileSavedEvent`），而不是 `proxy.document.save(path)`。
3. 全局替换前必须 `if proxy.is_modified: 提示用户先保存或放弃`；替换后
   `proxy.document.reload()` + `sc.setText(...)` 必须包裹在
   `proxy._restoring = True` 中，并 `undo_manager.clear()`。
4. 回归测试：`tests/test_audit_interaction_state.py::TestContentSourceDuplication`
   与 `TestSaveAs`、`TestSearchAgainstStaleProvider`。

---

### 3.3 【P1】Vim 模式的 `u` / `Ctrl+R` 静默失效

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `core/vim_mode.py:85-89`（Normal 模式 `Ctrl+R` → `self.editor.redo()`）
- `core/vim_mode.py:228-231`（`u` → `self.editor.undo()`）
- `core/editor.py:344-346`（禁用内置撤销栈）
- `ui/editor_view.py:505-513`（Vim 先处理并吞掉按键）
- `ui/main_window.py:1539-1545`（`editor = proxy.sc`）
- `tests/test_vim_mode.py:16`（测试用的是**裸 QsciScintilla**）

**机制**

```python
# core/vim_mode.py:228-231
228:        if text == 'u':
229:            for _ in range(count):
230:                self.editor.undo()
231:            return True
```
```python
# core/editor.py:344-346
344:            # 禁用内置撤销栈
345:            self.sc.SendScintilla(QsciScintilla.SCI_EMPTYUNDOBUFFER)
346:            self.sc.SendScintilla(QsciScintilla.SCI_SETUNDOCOLLECTION, 0)
```
```python
# ui/main_window.py:1539-1545
1539:            editor = proxy.sc
1540:
1541:            if checked:
1542:                vim = getattr(editor, '_vim_mode', None)
1543:                if vim is None:
1544:                    vim = VimMode(editor)
1545:                    editor._vim_mode = vim
```
`SCI_SETUNDOCOLLECTION, 0` 之后 Scintilla 不再累积撤销动作，
`SCI_UNDO`/`SCI_REDO` 变成空操作。而 `handle_key` 返回 `True`，
`EditorWidget.keyPressEvent` 直接 `return`（`ui/editor_view.py:510-511`），
按键既没生效也没落到主窗口的 `proxy.undo()`。

**最小复现步骤**

```python
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeyEvent
from PyQt5.Qsci import QsciScintilla
from core.document import Document
from core.editor import EditorProxy
from core.vim_mode import VimMode

sc = QsciScintilla(); sc.setUtf8(True)
sc.setText("hello world\n"); sc.setCursorPosition(0, 0)

proxy = EditorProxy(sc, Document())      # ← 必须先建代理（它会禁用内置撤销栈）
vm = VimMode(sc); vm.set_enabled(True)

before = sc.text()
vm.handle_key(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_X, Qt.NoModifier, 'x'))
print(repr(sc.text()))                    # 'ello world\n'  ← x 生效
print(len(proxy.undo_manager.undo_stack)) # >= 1           ← 自研栈记录了

vm.handle_key(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_U, Qt.NoModifier, 'u'))
print(repr(sc.text()))
# 期望: 'hello world\n'
# 预测实际: 'ello world\n'   ← u 完全没反应
```

**为什么现有测试发现不了（覆盖盲区证据）**

`tests/test_vim_mode.py` 的 fixture：

```python
16:    editor = QsciScintilla()
17:    editor.setUtf8(True)
18:    editor.setText("hello world\nfoo bar\nbaz qux\n")
...
24:    vm = VimMode(editor)
25:    vm.set_enabled(True)
```
用的是**裸 `QsciScintilla`**（内置撤销栈是开的），而且 11 个测试
**没有任何一个测 `u` 或 `Ctrl+R`**（grep 确认）。所以"Vim × 自研撤销栈"
这个组合在测试里完全不存在。

**影响**
用户的 Vim 撤销诉求被静默丢弃；由于 Vim 的编辑（`x`/`dd`/`p`/`o`…）**确实**进了自研栈，
菜单 Ctrl+Z 又能用，行为呈现"时好时坏"，极难自行定位。

**建议修法**
1. `VimMode` 不应直接操作 Scintilla 的 undo，而应通过代理：

```python
def _undo(self):
    proxy = getattr(self.editor, 'proxy', None)
    if proxy is not None:
        proxy.undo()
    else:
        self.editor.undo()      # 无代理时（单元测试）回退
```
2. 或者让 `main_window._toggle_vim_mode` 传入 `proxy` 而不是 `sc`：
   `VimMode(proxy.sc, proxy=proxy)`。
3. `tests/test_vim_mode.py` 的 fixture 应改为经过 `EditorProxy`，
   并补 `test_vim_u_undoes_own_edit`、`test_vim_ctrl_r_redoes`。
4. 新增回归测试：`tests/test_audit_interaction_undo.py::TestVimUndo`。

---

### 3.4 【P1】撤销后合并新编辑 → 重做栈不清空，`Ctrl+Y` 产生不可达状态

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `core/undo.py:242-271` `record()`
- `core/undo.py:261-262`（合并命中即 `return`，**跳过** `_do_record`）
- `core/undo.py:273-280` `_do_record()`（**唯一**清 redo 的地方：276-277）
- `core/undo.py:324-381` `_try_merge()`
  - `334-353` `_pending_group` 时间窗合并
  - `358-379` 与栈顶命令合并（`377: return True` 前不清 redo）
- `core/commands.py:319-336` `InsertCmd.can_merge/merge_with`（`326` 硬编码 `MERGE_INTERVAL_MS`）
- `core/commands.py:619-629` `GroupCmd.can_merge/merge_with`（**无时间窗**）
- `core/editor.py:695-711` 多光标/列模式 → `GroupCmd`

**机制**

```python
# core/undo.py:255-268
255:        with self._lock:
256:            try:
257:                # 统计
258:                self.statistics.record_command()
259:
260:                # 检查是否与 pending group 合并
261:                if self._try_merge(command):
262:                    return                      # ← 提前返回
263:
264:                # 提交 pending group
265:                self._commit_pending_group()
266:
267:                # 直接记录命令
268:                self._do_record(command)
```
```python
# core/undo.py:273-280（清 redo 只在这里）
273:    def _do_record(self, command: Command):
274:        """实际记录命令"""
275:        # 清空重做栈（新操作后重做栈失效）
276:        if self.redo_stack:
277:            self.redo_stack.clear()
```
```python
# core/undo.py:358-379（与栈顶合并）
358:        # 检查是否可以与上一个命令合并
359:        if self.undo_stack:
360:            last_cmd = self.undo_stack[-1]
361:
362:            try:
363:                if last_cmd.can_merge(command):
364:                    merged = last_cmd.merge_with(command)
365:                    if merged is not None:
366:                        # 替换栈顶
367:                        self.undo_stack[-1] = merged
368:                        self.statistics.record_merge(1)
...
377:                        return True
```
```python
# core/commands.py:619-623（GroupCmd 合并无任何时间窗）
619:    def can_merge(self, other: 'Command') -> bool:
620:        """命令组可以合并另一个命令组"""
621:        return isinstance(other, GroupCmd)
```

**生产可达性**：多光标/列模式编辑在 `core/editor.py:695-711` 被包成 `GroupCmd`，
所以"两次多光标编辑永远合并"是必然的；配合一次普通编辑 + 一次 Ctrl+Z，
即可命中 `361-377` 的合并分支并留下过期 redo。

**最小复现步骤（无 GUI，确定性）**

```python
from core.undo import UndoManager
from core.commands import GroupCmd, InsertCmd

mgr = UndoManager()
mgr.record(GroupCmd([InsertCmd(0, "AAA")]))   # 多光标编辑 1 -> stack=[G1]
mgr.record(InsertCmd(0, "X"))                 # 普通编辑     -> stack=[G1, X]

mgr.undo()                                    # -> stack=[G1], redo=[X]
assert mgr.can_redo() is True

mgr.record(GroupCmd([InsertCmd(0, "Y")]))     # 多光标编辑 2 -> G1 与 G2 合并
print("can_redo =", mgr.can_redo())
# 期望: False   （内容变了，重做必须失效）
# 预测实际: True （redo 栈里还留着 X）
print([c.describe() for c in mgr.redo_stack])  # ['Insert@0: \'X\' (1 字符)']
```

**编辑器级别复现**（真 QScintilla + SCN_MODIFIED，需要放宽插入合并窗口）：

```python
import core.commands as commands
commands.MERGE_INTERVAL_MS = 10 ** 9          # 让 InsertCmd 的 200ms 窗确定命中

sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"AAA")   # stack=[A]
sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"X")     # 与 A 不相邻 -> stack=[A, X]
proxy.undo()                                     # stack=[A], redo=[X]  text="AAA"
sc.SendScintilla(sc.SCI_INSERTTEXT, 3, b"BB")    # A.can_merge -> 合并, text="AAABB"
print(proxy.can_redo())                          # 期望 False，预测 True
proxy.redo()                                     # -> "XAAABB"：历史中从未出现过的状态
```

**原始证据（grep：谁调用 `begin_group`）**

```
$ grep -n "begin_group\|begin_transaction" -r . --include=*.py
core\undo.py:383:    def begin_group(self, command: Command):
core\undo.py:811:    def begin_transaction(self):
core\undo.py:1151:    manager.begin_group(InsertCmd(0, "A"))   # __main__ 演示
core\undo.py:1163:    manager.begin_transaction()              # __main__ 演示
tests\test_undo.py:191:        mgr.begin_group(InsertCmd(0, "a"))
```
→ `begin_group` 在生产代码中**未被调用**，所以 `_pending_group` 路径
（`core/undo.py:334-353`）当前只影响 `tests/`；但**与栈顶合并**那条
（`358-379`）是生产主路径，缺陷成立。

**影响**
`can_redo()` 为 True → UI 的"重做"可用 → 用户按 Ctrl+Y 后内容变成
一个**在线性 undo/redo 历史中不可达**的状态，且**此状态会被保存**。
对自研撤销栈来说这是最核心的一致性违约。

**建议修法**
1. 把"清空 redo"上移到 `record()` 的最前面（在任何合并判断之前）：

```python
def record(self, command):
    if self._disabled or command is None:
        return
    with self._lock:
        # 任何新命令都让 redo 栈失效，无论它最终是独立记录还是被合并
        if self.redo_stack:
            self.redo_stack.clear()
        try:
            ...
```
2. 或者让 `_try_merge` 在返回 True 之前统一调用 `self.redo_stack.clear()`。
3. `GroupCmd.can_merge` 应加入时间窗（复用 `MERGE_INTERVAL_MS`），
   避免"两次相隔很久的多光标编辑被合并成一步撤销"。
4. 给 `UndoManager` 补不变式断言/测试：`record()` 之后若 `undo_stack` 长度或栈顶发生变化，
   则 `redo_stack` 必为空。
5. 回归测试：`tests/test_audit_interaction_undo.py::TestUndoRedoStackInvalidation`。

---

### 3.5 【P1】主题切换把文字色换成背景色（晨曦主题文字不可见）

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `infrastructure/theme_loader.py:627-707` `adapt_qss_colors`
- 关键顺序：`652-701` 的 `replacements` 列表；`656` `#d4d4d4`→`foreground`；
  `657` `#cccccc`→`tab_fg`；`659` `#666666`→`line_number_fg`；`678` `#333333`→`panel_bg`
- `light_clean` 定义：`436` `foreground="#333333"`；`482` `panel_bg="#f5f5f5"`；
  `478` `tab_fg="#666666"`；`443` `line_number_fg="#999999"`
- 消费方（14 个面板的 `refresh_theme`）：`ui/panels.py:793-800`、
  `ui/terminal_panel.py:127-138`、`ui/python_console.py:1467-1491`、
  `ui/directory_tree.py:495-503`、`ui/git_panel.py:85-93`、`ui/lsp_panel.py:106-113`、
  `ui/log_viewer.py:110-118`、`ui/problems_panel.py:95-103`、
  `ui/plugins_panel.py:427-435`、`ui/perf_monitor.py:116-124`、
  `ui/undo_history_panel.py:74-82`、`ui/outline_panel.py:1295-1302`、
  `ui/global_search_panel.py:734-741`、`ui/task_panel.py:84-92`

**机制（逐字代码）**

```python
# infrastructure/theme_loader.py:646-707（节选，顺序即执行顺序）
646:    # 老深色 → 主题色（按优先级，先长后短）
...
650:    replacements = [
651:        # ==== 原表 ====
652:        ('#252526', c.panel_bg),
653:        ('#1e1e1e', c.background),
654:        ('#2d2d2d', c.menubar_bg),
655:        ('#3c3c3c', c.border),
656:        ('#d4d4d4', c.foreground),
657:        ('#cccccc', c.tab_fg),
658:        ('#888888', c.line_number_fg),
659:        ('#666666', c.line_number_fg),
660:        ('#555555', c.input_border),
...
678:        ('#333333', c.panel_bg),
...
703:    for old, new in replacements:
704:        if old and new and old != new:
705:            qss = qss.replace(old, new)
```

`('#d4d4d4', c.foreground)` 在 **656**，`('#333333', c.panel_bg)` 在 **678**。
对 `light_clean`，`c.foreground == "#333333"`，所以 656 行把 `#d4d4d4`
变成 `#333333`，678 行再把它变成 `c.panel_bg == "#f5f5f5"`。
同理 `#cccccc`：657 行 → `tab_fg == "#666666"`，659 行 → `line_number_fg == "#999999"`。

`if old != new` 这个守卫**只保证"某一对"自身不互换**，无法阻止**跨条目的链式替换**。

**具体后果示例**：`ui/terminal_panel.py:115-118` 里输入框的样式是

```python
115:        self.input_edit.setStyleSheet(
116:            "background-color: #0d0d0d; color: #d4d4d4; "
117:            "border: none; font-family: Consolas; padding: 4px;"
118:        )
```
经 `refresh_theme` → `adapt_qss_colors` 后：
- `#0d0d0d` → `c.background` = `#ffffff`（白底）
- `#d4d4d4` → `#333333` → **`#f5f5f5`**（近白字）
→ 白底白字，终端输入框在晨曦主题下**不可读**。

**最小复现步骤（不需要 GUI）**

```python
from infrastructure.theme_loader import BuiltinThemes, adapt_qss_colors

theme = BuiltinThemes.light_clean()
print(adapt_qss_colors("color: #d4d4d4;", theme))
# 期望: 'color: #333333;'   (= theme.colors.foreground)
# 预测实际: 'color: #f5f5f5;'  (= theme.colors.panel_bg)  ← 与背景同色

print(adapt_qss_colors("color: #cccccc;", theme))
# 期望: 'color: #666666;'   (= tab_fg)
# 预测实际: 'color: #999999;'  (= line_number_fg)

# 其余 3 套主题不受影响（因 old == new 被 704 行的守卫跳过）：
for t in BuiltinThemes.all_themes():
    print(t.name, repr(adapt_qss_colors("color: #d4d4d4;", t)))
# 预测: dark_night 'color: #d4d4d4;' / light_clean 'color: #f5f5f5;'
#       eye_protect 'color: #2c3e2f;' / high_contrast 'color: #ffffff;'
```

**原始证据（主题取值，逐字）**

```python
# infrastructure/theme_loader.py:435-443, 478-484（light_clean）
435:            colors=ThemeColors(
436:                background="#ffffff",
437:                foreground="#333333",
...
443:                line_number_fg="#999999",
...
478:                tab_bg="#e8e8e8",
479:                tab_fg="#666666",
...
482:                panel_bg="#f5f5f5",
```

**影响**
4 套主题里只有晨曦受影响，但晨曦是默认浅色主题。14 个面板中所有硬编码
`#d4d4d4` 的文字（终端、Python 控制台、日志查看器、Git 面板、大纲……）
在浅色主题下变成近白，**功能可用但看不见**，属于"切主题后组件坏掉"的典型交互缺陷。

**建议修法**
1. **一次性映射**，避免链式：把替换实现为单遍正则 + 查表，
   而不是顺序 `str.replace`：

```python
import re
_MAP = {old.lstrip('#').lower(): attr for old, attr in replacements}
def adapt_qss_colors(qss, theme):
    c = theme.colors
    def sub(m):
        key = m.group(1).lower()
        attr = _MAP.get(key)
        if not attr:
            return m.group(0)
        return getattr(c, attr)
    return re.sub(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', sub, qss)
```
2. 或者最简单：**把 `('#333333', c.panel_bg)` 这一类"补充表"里的 old 值
   加入一个"已作为输出产生过"的黑名单**，产生过的值不再参与后续替换。
3. 增加"主题 × 对比度"回归测试：对每套主题、每个面板 QSS，
   断言文本色与背景色的相对亮度差 ≥ 阈值（WCAG AA 4.5:1）。
4. 回归测试：`tests/test_audit_interaction_theme.py::TestAdaptQssColorsChaining`。

---

### 3.6 【P1】编码切换 × 保存 → 文件被永久破坏

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `ui/mixins/status_bar_mixin.py:177-188` `_on_encoding_changed`
- `core/document.py:593-615` `change_encoding`（`607-612` 重载 provider）
- `core/content_provider.py:960-975` `LocalFileProvider.reload()`
- `core/editor.py:528-552` `_sync_content_to_provider()`（用 `provider.encode`）
- `core/content_provider.py:306-311` `encode()`

**机制**

```python
# ui/mixins/status_bar_mixin.py:177-188
177:    def _on_encoding_changed(self, encoding: str):
178:        """状态栏切换编码"""
179:        try:
180:            proxy = self.tabs.current_proxy()
181:            if proxy and proxy.document:
182:                proxy.document.change_encoding(encoding)
183:                self._update_status_for_editor()
```
```python
# core/document.py:593-615（节选）
601:        old = self.meta.encoding
602:        self.meta.encoding = encoding
603:
604:        if self.provider:
605:            self.provider.encoding = encoding
606:
607:        if reload and self.meta.filepath:
608:            try:
609:                if hasattr(self.provider, 'reload'):
610:                    self.provider.reload()
611:            except Exception:
612:                pass
```
`change_encoding` 只让 **provider** 用新编码重新解码；`EditorProxy.sc` 完全没被触碰。
而 `save_file()` 又是从 `sc.text()` 取内容、按 `provider.encoding` 重新编码：

```python
# core/editor.py:471-494（节选）
473:            text = self.sc.text()
...
491:            self._sync_content_to_provider(text)
...
494:            success = self.document.save(filepath)
```
```python
# core/content_provider.py:306-311
306:    def encode(self, text: str) -> bytes:
307:        """编码文本为字节串"""
308:        try:
309:            return text.encode(self._encoding, errors='replace')
310:        except (LookupError, UnicodeEncodeError):
311:            return text.encode(ENCODING_UTF8, errors='replace')
```

**具体损害路径**：文件本是 UTF-8，用户误以 GBK 打开 → 编辑器显示乱码
（provider 里也是乱码，两边一致，用户"看不出来有问题"）；
用户察觉后把编码切成 UTF-8 → provider 变成正确文本，**编辑器仍是乱码**；
用户此时按 Ctrl+S → 写回磁盘的是"乱码文本的 UTF-8 编码"，
**原字节永久丢失，再切回任何编码都救不回来**。

**最小复现步骤**

```python
from PyQt5.Qsci import QsciScintilla
from core.document import Document
from core.editor import EditorProxy

p = r"D:\tmp\enc.txt"
open(p, "wb").write("中文内容\n".encode("utf-8"))

sc = QsciScintilla(); sc.setUtf8(True)
proxy = EditorProxy(sc, Document())
proxy.document.open(p, encoding="gbk")   # 用错编码打开
proxy.open_file()                        # 加载进编辑器
print(repr(sc.text()))                   # 乱码

proxy.document.change_encoding("utf-8")  # 状态栏切换编码
print(repr(sc.text()))                   # 预测：仍是乱码（编辑器未刷新）
print(repr(proxy.document.get_text()))   # '中文内容\n'（provider 已正确）

proxy.save_file()                        # 用户按 Ctrl+S
print(open(p, "rb").read())
# 期望: b'\xe4\xb8\xad\xe6\x96\x87\xe5\x86\x85\xe5\xae\xb9\n'
# 预测实际: 乱码文本的 UTF-8 字节（文件损坏）
```

**影响**
不可逆的数据损坏。而且 `change_encoding` 的 `reload=True` 默认值会**丢弃**
provider 里尚未保存的编辑（因为 provider 从来就不是编辑器内容的镜像，
见 3.2）—— 两个缺陷叠加。

**建议修法**
1. `change_encoding` 之后必须重新加载编辑器文本：

```python
def change_encoding(self, encoding, reload=True):
    ...
    self.provider.reload()
    # 新增：把 provider 内容推回编辑器
    for ed in self.get_editors():
        pass
    # 更实际的写法：在 status_bar_mixin 里显式刷新
```
```python
# ui/mixins/status_bar_mixin.py
proxy.document.change_encoding(encoding)
proxy._restoring = True
try:
    proxy.sc.setText(proxy.document.get_text())
finally:
    proxy._restoring = False
proxy.sc.setModified(proxy._modified)
proxy.undo_manager.clear()      # 位置全变了，旧命令必须作废
```
2. 若文档 `is_modified`，切换编码前必须先提示"将丢弃未保存修改"。
3. 回归测试：`tests/test_audit_interaction_file_io.py::TestEncodingVsEditor`。

---

### 3.7 【P1】行尾符切换 × 保存 → 永远写 LF，设置是纯装饰

**状态：静态定位，未动态复现。（与 `docs/audit_data_integrity.md` 结论 E 同源）**

**涉及文件:行号**
- `ui/mixins/status_bar_mixin.py:191-205` `_on_eol_changed`
- `core/document.py:620-623` `set_eol()`（只改元数据）
- `core/document.py:632-666` `convert_eol()`（**死代码**）
- `core/content_provider.py:306-311` `encode()`（无 EOL 处理）
- `core/editor.py:478-491` `save_file()` 的"清理"逻辑（**主动把 CRLF 归一为 LF**）

**机制**

```python
# core/document.py:620-623
620:    def set_eol(self, eol: str):
621:        """设置行尾符（实际转换在保存时进行）"""
622:        self.meta.eol = eol
623:        self.mark_modified()
```
注释说"实际转换在保存时进行"，但**没有任何保存路径读 `meta.eol`**：

```
$ grep -n "convert_eol\|meta\.eol\|set_eol" -r . --include=*.py
core\document.py:620:    def set_eol(self, eol: str):
core\document.py:622:        self.meta.eol = eol
core\document.py:628:            return self.meta.eol
core\document.py:629:        self.meta.eol = detect_file_eol(self.meta.filepath)
core\document.py:630:        return self.meta.eol
core\document.py:632:    def convert_eol(self, target: str) -> int:      # ← 0 处调用
core\document.py:645:        current = self.meta.eol
core\document.py:660:        self.meta.eol = target
core\document.py:1175:            'eol': repr(self.meta.eol)
core\document.py:1186:            'eol': repr(self.meta.eol)
ui\status_bar_widgets.py:102:    def set_eol(self, eol):                          # 仅更新标签文字
ui\mixins\status_bar_mixin.py:196:  if hasattr(proxy.document, 'set_eol'):
ui\mixins\status_bar_mixin.py:197:      proxy.document.set_eol(eol)
```
`convert_eol`（真正会转换并写回 provider 的那个方法）**全仓 0 处调用**。

更糟的是 `save_file` 的"清理"会把 CRLF 抹掉：

```python
# core/editor.py:475-489
475:            # 应用偏好设置：清理行尾空白和末尾换行
476:            settings = QSettings("QingCao", "Editor")
477:
478:            if settings.value("trim_trailing_whitespace", True, type=bool):
479:                lines = [l.rstrip() for l in text.splitlines()]
480:                text = '\n'.join(lines)
```
`str.splitlines()` 会把 `\r\n` 拆掉，`'\n'.join` 一律用 LF 重组。

**最小复现步骤**

```python
from PyQt5.Qsci import QsciScintilla
from core.document import Document
from core.editor import EditorProxy

p = r"D:\tmp\eol.txt"
open(p, "wb").write(b"a\nb\n")

sc = QsciScintilla(); sc.setUtf8(True)
proxy = EditorProxy(sc, Document())
proxy.open_file(p)

proxy.document.set_eol("\r\n")     # 状态栏把 LF 切成 CRLF
proxy.save_file()                  # 保存

print(open(p, "rb").read())
# 期望: b'a\r\nb\r\n'
# 预测实际: b'a\nb\n'   ← 完全没变

# 再打开
proxy2 = EditorProxy(QsciScintilla(), Document()); proxy2.open_file(p)
print(repr(proxy2.document.meta.eol))   # 预测: '\n'（设置回退）
```

**影响**
状态栏显示 CRLF、文件实际是 LF，用户为 Windows/跨平台协作做的行尾设置完全无效；
Git diff 会显示整文件变更却"看不出来改了什么"。

**建议修法**
1. `_on_eol_changed` 改调 `document.convert_eol(eol)`（该方法已存在且实现正确），
   并在之后刷新编辑器文本 + 清空撤销栈。
2. 在 `save_file` 里按 `meta.eol` 做最终转换，并把"清理"的
   `'\n'.join(lines)` 改为 `meta.eol.join(lines)`。
3. `Document.save()` 里加断言：写盘字节的换行符种类必须与 `meta.eol` 一致。
4. 回归测试：`tests/test_audit_interaction_file_io.py::TestEolVsSave`。

---

### 3.8 【P1】宏回放 × 撤销 → 回放不入栈，`Ctrl+Z` 破坏内容

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `core/macro.py:529-658` `replay()`
- `core/macro.py:702-707` `_disable_scintilla_notifications()`（`SCI_SETMODEVENTMASK, 0`）
- `core/macro.py:709-718` `_enable_scintilla_notifications()`（只恢复 INSERT|DELETE）
- `core/macro.py:619-626`（只设 `proxy._modified`，不调 `document.mark_modified()`）
- `core/editor.py:645-739` `_on_scintilla_modified`（因掩码为 0 而不触发）
- `core/editor.py:344-346`（内置撤销栈已被禁用 → 没有任何撤销记录）

**机制**

```python
# core/macro.py:576-605（节选）
576:            # 禁用 Scintilla 通知（提高性能）
577:            self._disable_scintilla_notifications(proxy)
...
598:                # 回放单次
599:                for macro_cmd in macro.commands:
600:                    try:
601:                        cmd = Command.from_dict(macro_cmd.command_data)
602:                        cmd.execute(proxy.sc)
603:                        executed += 1
```
```python
# core/macro.py:702-707
702:    def _disable_scintilla_notifications(self, proxy):
703:        """禁用 Scintilla 通知以提高回放性能"""
704:        try:
705:            proxy.sc.SendScintilla(proxy.sc.SCI_SETMODEVENTMASK, 0)
706:        except Exception:
707:            pass
```
`SCI_SETMODEVENTMASK=0` 之后 Scintilla **不再发送** `SCN_MODIFIED`，
`EditorProxy._on_scintilla_modified` 的 `mod_type & (SC_MOD_INSERTTEXT|...)`
判断拿不到事件 → `undo_manager.record()` 一次都不会被调用。
而回放结束时既没有 `undo_manager.clear()`，也没有补偿性记录：

```python
# core/macro.py:616-626
616:            elapsed = (time.time() - start_time) * 1000
617:
618:            # 标记修改
619:            proxy.sc.setModified(True)
620:            if hasattr(proxy, '_modified'):
621:                proxy._modified = True
622:            if hasattr(proxy, 'modified_changed'):
623:                try:
624:                    proxy.modified_changed.emit(True)
```
于是：**缓冲区变了，撤销栈没变**。

**最小复现步骤**

```python
from PyQt5.Qsci import QsciScintilla
from core.document import Document
from core.editor import EditorProxy
from core.macro import MacroRecorder

sc = QsciScintilla(); sc.setUtf8(True); sc.setText("")
proxy = EditorProxy(sc, Document())
proxy.undo_manager.clear()
rec = MacroRecorder(undo_manager=proxy.undo_manager)

rec.start("m")
sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"AAA")     # 录进宏
rec.stop()

proxy.undo_manager.undo_stack.clear()              # 只看"回放"这一动作
proxy.undo_manager.redo_stack.clear()

sc.SendScintilla(sc.SCI_INSERTTEXT, 3, b"-")       # 手工编辑
before = sc.text()                                 # 'AAA-'
depth_before = len(proxy.undo_manager.undo_stack)  # 1

rec.replay(proxy, rec.current_macro, show_progress=False, check_cancel=False)
after = sc.text()                                  # 'AAAAAA-'
depth_after = len(proxy.undo_manager.undo_stack)   # 期望 2，预测仍是 1

print(depth_before, "->", depth_after)

proxy.undo()                                       # 用户按 Ctrl+Z
print(repr(sc.text()))
# 期望: 'AAA-'（回到回放前）
# 预测实际: 'AAAAA-'（弹出了回放之前的旧命令，按旧位置执行）
```

**影响**
宏回放**不可撤销**，且回放后第一次 Ctrl+Z 会执行一条针对旧内容位置的命令，
产生历史中不可达的状态并被保存。宏是"批处理"功能，用户回放后想撤销几乎是必然操作。

**建议修法**
1. 回放应作为一个**事务**进入撤销栈。两种做法：
   - 不要关掉通知，而是把回放期间的命令收集成 `GroupCmd` 后 `record()` 一次；
   - 或保留关通知（性能），但结束时构造

```python
if executed:
    cmds = [Command.from_dict(c.command_data) for c in macro.commands]
    proxy.undo_manager.record(GroupCmd(cmds))
```
     并保证 `_do_record` 清 redo（见 3.4 的修法）。
2. 回放前若 `undo_manager` 非空且内容已变，应当先 `mark_save_point()` 或
   在 UI 上明确提示"回放将以一步撤销记录"。
3. `_enable_scintilla_notifications` 应恢复**进入前的**掩码值，而不是写死
   `SC_MOD_INSERTTEXT|SC_MOD_DELETETEXT`。
4. 补 `document.mark_modified()` 调用，消除 `proxy._modified` 与
   `document.meta.modified` 的双真值（`INV-M3`）。
5. 回归测试：`tests/test_audit_interaction_macro.py`。

---

### 3.9 【P1】外部文件变更 × 撤销 → 重载后撤销栈未清理，旧命令位置失效

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `app/tabs.py:1344-1397` `_on_file_changed`
- `app/tabs.py:1399-1458` `_reload_file`（**核心**）
- `app/tabs.py:1415-1423`（**替换 provider 但不 close 旧的**）
- `app/tabs.py:1425-1429`（`editor.clear()` + `append()`，**未设 `_restoring`**）
- `app/tabs.py:1443-1449`（只重置 modified）

**机制**

```python
# app/tabs.py:1414-1449（节选）
1414:            # 重新打开文件
1415:            provider = LocalFileProvider()
1416:            provider.open(filepath)
1417:
1418:            # 更新 proxy 的 provider（使用新 API）
1419:            try:
1420:                if hasattr(editor, 'proxy') and editor.proxy.document:
1421:                    editor.proxy.document.provider = provider
1422:            except Exception:
1423:                pass
1424:
1425:            editor.clear()
1426:            for i in range(provider.total_blocks):
1427:                data = provider.read_block(i)
1428:                editor.append(data.decode(provider.encoding,
1429:                                            errors='replace'))
...
1443:            # 重置修改状态
1444:            try:
1445:                editor.setModified(False)
1446:                if hasattr(editor, 'proxy') and editor.proxy:
1447:                    editor.proxy._modified = False
```
三个问题：
1. **旧 provider 没 `close()`** → mmap 与文件句柄泄漏（Windows 上会锁文件）。
2. `editor.clear()` / `append()` 未设 `proxy._restoring` → 这一整批重载动作
   被 `_on_scintilla_modified` 记录进撤销栈（污染），同时把 `_modified` 置 True
   又在 1445-1447 强行改回 False（期间还发出了 `modified_changed(True)`）。
3. **`undo_manager` 从未被清理**，而栈内所有命令的 `pos` 都相对旧内容。

**最小复现步骤**

```python
from app.tabs import TabManager
p = r"D:\tmp\ext.txt"
open(p, "w", encoding="utf-8").write("AAAA\nBBBB\n")

tabs = TabManager()
proxy = tabs.open_file(p)
widget = tabs.widget(0)
sc = proxy.sc

sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"ZZ")   # 两次编辑
sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"YY")
print(len(proxy.undo_manager.undo_stack))        # >= 1

open(p, "w", encoding="utf-8").write("totally different\n")  # 外部改文件
tabs._reload_file(p, widget)                     # 用户点"是，重新加载"
print(repr(sc.text()))                           # 'totally different\n'
print(len(proxy.undo_manager.undo_stack))
# 期望: 0（重载后必须清空）
# 预测实际: >= 1（旧命令仍在，位置相对旧内容）

proxy.undo()                                     # 用户以为能撤销"重载"
print(repr(sc.text()))                           # 内容被意外破坏
```

**影响**
外部修改（Git 切换分支、格式化工具、同步盘）后重载 → 一次 Ctrl+Z 就把文件内容
改成"新内容的第 N 个字节被删掉"这类无意义状态，且会被保存。
另外 provider 泄漏会阻止后续外部写入（Windows）。

**建议修法**
```python
def _reload_file(self, filepath, editor):
    proxy = getattr(editor, 'proxy', None)
    old_provider = proxy.document.provider if proxy and proxy.document else None
    if proxy:
        proxy._restoring = True
    try:
        ...  # 现有重载逻辑
    finally:
        if proxy:
            proxy._restoring = False
            proxy.undo_manager.clear()      # 位置基线变了
            proxy._modified = False
            proxy.sc.setModified(False)
            proxy.document.mark_saved()
    if old_provider is not None:
        try:
            old_provider.close()            # 释放 mmap / 文件句柄
        except Exception:
            pass
```
4. 回归测试：`tests/test_audit_interaction_state.py::TestExternalChangeVsUndo`。

---

### 3.10 【P1】另存为 × LSP → URI / 文档状态不同步

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `ui/mixins/file_ops_mixin.py:230`（触发点）
- `core/editor.py:218` `self._lsp_uri`、`1895` 首次设置
- `core/editor.py:750-768` `_sync_lsp_document`（`761-766`：`self._lsp_uri or ...path_to_uri(...)`）
- `core/editor.py:770-780` `_notify_lsp_saved`（`775-777`：同样 `self._lsp_uri or ...`）
- `core/editor.py:2018-2028` `request_completion`（`2025`：**直接用 `document.filepath`**）
- `core/editor.py:1849-1921` `toggle_lsp`（只在 toggle 时 `did_open`/`did_close`）

**机制（同一份文档出现两个不同 URI）**

```python
# core/editor.py:750-768
750:    def _sync_lsp_document(self):
...
761:            self.lsp_client.did_change(
762:                self._lsp_uri or LspClient.path_to_uri(
763:                    self.document.filepath or ""
764:                ),
765:                self.sc.text(),
766:            )
```
```python
# core/editor.py:2018-2028
2018:    def request_completion(self):
2019:        """请求 LSP 补全"""
2020:        if not self.lsp_client or not self.document.filepath:
2021:            return
2022:
2023:        try:
2024:            line, col = self.sc.getCursorPosition()
2025:            uri = "file:///" + self.document.filepath.replace("\\", "/")
2026:            self.lsp_client.request_completion(uri, line, col)
```
另存为本身会更新 `document.filepath`（`core/document.py:403-407`），
但 `EditorProxy._lsp_uri` 不会更新。于是：
- `did_change` / `did_save` 发往**旧 URI**（服务器认为旧文件在持续变化）；
- `request_completion` 用**新 URI**（服务器从未收到该文档的 `did_open`）→ 补全失败；
- 旧 URI 从未 `did_close`，新 URI 从未 `did_open`。
- `did_save` 完全没被触发（因为 `_save_file_as` 绕过 `EditorProxy.save_file`，
  `core/editor.py:501` 的 `_notify_lsp_saved` 不会执行）。

**最小复现步骤**

```python
from PyQt5.Qsci import QsciScintilla
from core.document import Document
from core.editor import EditorProxy
from core.lsp_client import LspClient

open(r"D:\tmp\a.py", "w", encoding="utf-8").write("x = 1\n")
sc = QsciScintilla(); sc.setUtf8(True)
proxy = EditorProxy(sc, Document()); proxy.open_file(r"D:\tmp\a.py")

sent = {}
class FakeLsp:
    def did_save(self, uri, text=None): sent['save'] = uri
    def did_change(self, uri, text):    sent['change'] = uri
    def did_close(self, uri):           sent['close'] = uri

proxy.lsp_active = True
proxy.lsp_client = FakeLsp()
proxy._lsp_uri = LspClient.path_to_uri(proxy.document.filepath)

proxy.document.save(r"D:\tmp\b.py")      # 复现 另存为
proxy._notify_lsp_saved()

print(sent['save'], "vs", LspClient.path_to_uri(r"D:\tmp\b.py"))
# 期望两者相同
# 预测实际: sent['save'] 指向 a.py
```

**影响**
另存为后：补全彻底失效、诊断停留在旧文件、语言服务器句柄泄漏。
对 `.py` 用户（这是编辑器的主力场景）表现为"补全突然不工作了"。

**建议修法**
1. 在 `Document.save()` 的 `is_save_as` 分支（`core/document.py:403-407`）里发出
   一个信号（例如 `saved_as(old_path, new_path)`），由 `EditorProxy` 订阅并执行：

```python
def _on_document_saved_as(self, old, new):
    if self.lsp_client and self._lsp_uri:
        try:
            self.lsp_client.did_close(self._lsp_uri)
        except Exception:
            pass
        self._lsp_uri = LspClient.path_to_uri(new)
        self.lsp_client.did_open(
            self._lsp_uri, self._lsp_language_id(), self.sc.text())
```
2. `request_completion` 统一改用 `self._lsp_uri`（或用 `LspClient.path_to_uri`
   而不是手工拼 `"file:///"`，避免路径编码差异）。
3. `_save_file_as` 改为走 `proxy.save_file(path)`（同时修好 3.2 与 3.11）。
4. 回归测试：`tests/test_audit_interaction_file_io.py::TestSaveAsVsLsp`。

---

### 3.11 【P2】另存为 × 修改标记 / 文件监听器

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `ui/mixins/file_ops_mixin.py:228-235`（不调 `setModified(False)`）
- `core/editor.py:496-518`（`save_file` 才做这些事）
- `app/tabs.py:1318-1342`（watcher 以**旧路径**为键）

**机制**

```python
# core/editor.py:496-518（save_file 里的正确做法）
496:            if success:
497:                self._modified = False
498:                self.sc.setModified(False)
499:
500:                # P0-2: 通知语言服务器已保存
501:                self._notify_lsp_saved(filepath)
...
511:                # 发射事件
512:                try:
513:                    bus.emit_event(FileSavedEvent(
```
`_save_file_as` 直接调 `proxy.document.save(path)`，上述 5 件事**一件都没做**：
`sc.setModified(False)`、`_notify_lsp_saved`、`FileSavedEvent`、
末尾空白/换行规范化、`_sync_content_to_provider`。

watcher 也没迁移：`app/tabs.py:528` `self._setup_file_watcher(filepath, editor)`
用**旧**路径注册；`_reload_file`/`_on_file_changed` 都以该路径为键。
另存为后，编辑器仍在监听旧文件，新文件的外部变更不再通知。

**最小复现步骤**

```python
open(r"D:\tmp\src.py", "w", encoding="utf-8").write("print(1)\n")
sc = QsciScintilla(); sc.setUtf8(True)
proxy = EditorProxy(sc, Document()); proxy.open_file(r"D:\tmp\src.py")
sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"# c\n")
print(proxy.is_modified)              # True
proxy.document.save(r"D:\tmp\dst.py") # 另存为
print(proxy.is_modified)
# 期望: False（文件已保存）
# 预测实际: True（标签继续显示 '*'）
```

**影响**
标签永久显示 `*`；`save_autosave`（若可用）会为已保存文件生成备份；
用户被"未保存"提示反复打扰；外部变更检测指向错误的文件。

**建议修法**：`_save_file_as` 改为 `proxy.save_file(path)`，
并同步调用 `tabs._remove_file_watcher(old)` + `tabs._setup_file_watcher(new, editor)`。

---

### 3.12 【P2】插件热重载 × 菜单 / 工具栏 / 快捷键

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `app/plugins.py:559-611` `add_menu`
- `app/plugins.py:617-628` `_find_or_create_menu`
- `app/plugins.py:1516-1565` `cleanup()`
  - `1536-1542` 子菜单只 `deleteLater()`
  - `1526-1534` 动作靠 `action.parent().removeAction(action)`
- `app/plugins.py:641-680` `add_toolbar_action`（`676` 塞进 `_registered_actions`）
- `app/plugins.py:685-708` `register_shortcut`
- `infrastructure/plugin_loader.py:1168-1204` `reload_plugin`
- `infrastructure/plugin_loader.py:1339-1381` `_on_directory_changed`

**机制（缺陷不是"重复叠加"，而是"整项消失"）**

`add_menu` 复用于菜单时**按文本查找**，而 `cleanup()` 用的是**延迟删除**：

```python
# app/plugins.py:592-602
592:            # 逐级创建子菜单
593:            for sub_name in parts[1:-1]:
594:                sub_menu = None
595:                for act in menu.actions():
596:                    if act.menu() and act.text() == sub_name:
597:                        sub_menu = act.menu()        # ← 可能命中"待删除"的旧子菜单
598:                        break
599:                if sub_menu is None:
600:                    sub_menu = menu.addMenu(sub_name)
601:                    self._registered_menus.append(sub_menu)
602:                menu = sub_menu
```
```python
# app/plugins.py:1536-1542
1536:        # 清理子菜单
1537:        for menu in self._registered_menus:
1538:            try:
1539:                menu.deleteLater()                   # ← 只是排队删除
1540:            except Exception:
1541:                pass
1542:        self._registered_menus.clear()
```
热重载在**同一个调用栈**里完成 `cleanup()` → `activate()`：
旧子菜单对象还活着（`deleteLater` 尚未处理），于是新的 `QAction`
被加进这个"即将被销毁的容器"；控制权回到事件循环后，
旧子菜单连同刚加进去的菜单项一起被销毁 → **菜单项消失**。

另外两处不对称（**影响较轻，必须与上面的"菜单项消失"区分开**）：

- `add_menu` 单段路径时用 `_find_or_create_menu("工具")` 创建**顶级菜单**，
  但**不记录进 `_registered_menus`** → cleanup 后空菜单残留
  （`app/plugins.py:579-586`、`626`）。这是**确定**的状态残留，但只是外观问题。
- 工具栏动作的 parent 是主窗口（`app/plugins.py:667` `QAction(text, self.win)`），
  所以 `cleanup()` 里的 `action.parent().removeAction(action)`（1529-1530）
  作用在 QMainWindow 上，**无法**把按钮从 QToolBar 移除。
  **但** `action.deleteLater()` 会销毁该 QAction，QToolBar 会随之把它从
  自己的动作列表里剔除，所以**实际观察不到重复**。
  我把对应测试写成**预期通过**的对照组，就是为了标出这个区别：
  这是"实现不严谨但被 Qt 兜住"的潜在隐患，不是当前可观测的缺陷。
  只有将来有人把 `deleteLater()` 去掉（例如改用 `setVisible(False)`）
  才会变成真实缺陷。

**最小复现步骤**

```python
from PyQt5.QtCore import QEvent
from PyQt5.QtWidgets import QMainWindow
from app.plugins import PluginAPI

win = QMainWindow()

def count():
    for a in win.menuBar().actions():
        if a.text().startswith("工具") and a.menu():
            for s in a.menu().actions():
                if s.text() == "我的插件" and s.menu():
                    return len([x for x in s.menu().actions()
                                if x.text() == "执行"])
    return 0

api1 = PluginAPI(win, permissions=[], plugin_name="demo")
api1.add_menu("工具/我的插件/执行", lambda: None)
print("首次:", count())            # 1

api1.cleanup()                     # 等价于 unload_plugin
api2 = PluginAPI(win, permissions=[], plugin_name="demo")
api2.add_menu("工具/我的插件/执行", lambda: None)

win.parent()  # noqa
from PyQt5.QtWidgets import QApplication
QApplication.instance().sendPostedEvents(None, QEvent.DeferredDelete)
print("热重载后:", count())
# 期望: 1
# 预测实际: 0
```

**影响**
用户开启热重载后改插件源码，插件菜单项静默消失（不是重复），
必须重启编辑器才能恢复；`plugin.json` 里 `hot_reload: true` 的承诺不成立。

**建议修法**
1. `cleanup()` 立即断开父子关系，而不是只排队删除：

```python
for sub in self._registered_menus:
    try:
        act = sub.menuAction()
        if act is not None and act.parent() is not None:
            act.parent().removeAction(act)
        sub.setParent(None)
        sub.deleteLater()
    except Exception:
        pass
```
2. `add_menu` 复用于菜单时应过滤掉 `sub.parent() is None`（已被摘除）的对象。
3. `_find_or_create_menu` 创建的顶级菜单也要登记，cleanup 时若为空则移除。
4. `add_toolbar_action` 应记录容器 `(toolbar, action)`，cleanup 时
   `toolbar.removeAction(action)`。
5. 回归测试：`tests/test_audit_interaction_plugin.py::TestHotReloadMenus`。

---

### 3.13 【P2】插件 `unsubscribe` × 事件订阅（映射表不完整）

**状态：静态定位，未动态复现。**

**涉及文件:行号** `app/plugins.py:772-815`（`subscribe`）与 `817-836`（`unsubscribe`）

**机制**

```python
# app/plugins.py:817-836
817:    def unsubscribe(self, event_name: str, callback: Callable):
818:        """取消订阅"""
819:        signal_map = {
820:            'file_opened': bus.file_opened,
821:            'file_saved': bus.file_saved,
822:            'file_closed': bus.file_closed,
823:            'editor_changed': bus.editor_changed,
824:            'cursor_moved': bus.cursor_moved,
825:            'selection_changed': bus.selection_changed,
826:        }
827:        signal = signal_map.get(event_name)
828:        if signal:
829:            try:
830:                signal.disconnect(callback)
```
`subscribe` 的支持列表（`app/plugins.py:788-804`）有 **15** 项，
`unsubscribe` 只有 **6** 项。缺 `file_modified`、`tab_changed`、`tab_added`、
`tab_removed`、`project_opened`、`project_closed`、`macro_started`、
`macro_stopped`、`theme_changed`。
对缺失项 `unsubscribe` **静默什么都不做**（不报错、不提示）。

**最小复现步骤**

```python
from PyQt5.QtWidgets import QMainWindow
from app.plugins import PluginAPI

win = QMainWindow()
api = PluginAPI(win, permissions=[], plugin_name="demo")
def cb(*a, **k): pass

api.subscribe("tab_changed", cb)
print(len(api._event_connections))     # 1
api.unsubscribe("tab_changed", cb)
print(len(api._event_connections))
# 期望: 0
# 预测实际: 1（订阅仍然挂着）
```

**影响**
插件在 `deactivate()` 里用 `unsubscribe` 清理订阅时，回调在插件卸载后仍被触发
（回调对象属于已被卸载的模块）→ 报错或操纵已销毁的 UI。
注意 `cleanup()` 走的是 `_event_connections`（`842-849`），**这条路径是正确的**，
所以缺陷只在插件自己调用 `unsubscribe` 时暴露。

**建议修法**：把 `signal_map` 提取为模块级常量 `PLUGIN_EVENT_SIGNALS`，
`subscribe` / `unsubscribe` 共用同一份，消除不对称。

---

### 3.14 【P1】自动保存 × 未保存内容（定时器从未启动）

**状态：静态定位，未动态复现。（与 `docs/audit_data_integrity.md` 结论 C 交叉印证）**

**涉及文件:行号**
- `app/session.py:147-150` `start_autosave()`
- `app/session.py:116-118`（定时器构造与连接）
- `app/session.py:156-171` `_autosave_tick()`（唯一会调 `save_autosave` 的地方）
- `app/session.py:782-878` `save_autosave()`
- `ui/main_window.py:208` `self.session = SessionManager()`（**没有** `start_autosave()`）
- `main.py:1096-1100`（正常退出时删除自动备份）

**机制**

```
$ grep -n "start_autosave|_autosave_timer|SessionManager\(" -r . --include=*.py
app\session.py:147:    def start_autosave(self):
app\session.py:150:            self._autosave_timer.start()
app\session.py:154:    def stop_autosave(self):
app\session.py:116:        self._autosave_timer = QTimer(self)
app\session.py:117:        self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
app\session.py:118:        self._autosave_timer.timeout.connect(self._autosave_tick)
ui\main_window.py:208:            self.session = SessionManager()
```
`start_autosave()` **全仓 0 处调用** → `_autosave_tick` 永不触发 →
`save_autosave()`（唯一把未保存内容写入 `backup/autosave/` 的函数）永不执行。
而 `check_and_recover_crash` 依赖这个目录：

```python
# main.py:1095-1100
1095:        # 清理自动备份（正常退出后不再需要）
1096:        try:
1097:            if hasattr(window, 'session') and window.session:
1098:                window.session.clear_autosave()
```
正常退出还会把仅有的备份删掉。

**影响**
崩溃/断电时没有任何未保存内容备份，崩溃恢复路径无文件可恢复；
`docs` / README 里宣传的"自动保存"实际不生效。

**建议修法**：在 `MainWindow.__init__` 建好 `self.session` 后立即
`self.session.start_autosave()`；并补一条集成测试断言
`session._autosave_timer.isActive()`。

---

### 3.15 【P2】会话恢复 × 未保存标记 / 退出对话框

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `app/session.py:266` `file_info['modified'] = proxy.is_modified`（**被采集**）
- `app/session.py:550-702` `restore()`（**从未使用 `modified`，也不恢复内容**）
- `app/session.py:217-329` `_collect_session_data`（**不保存文本内容**）
- `ui/main_window.py:2293-2309`（退出对话框只有 Discard / Cancel，**没有 Save**）

**机制**

`_collect_session_data` 采集了 `modified` 字段，但 `restore()` 只做
`tab_widget.open_file(filepath)` + 光标/滚动/书签/折叠恢复（`596-660`），
既没有内容，也没有把 `modified` 应用回去。所以：
- 会话 JSON 里 `modified: true` 的文件，恢复后内容 = **磁盘内容**，标记 = **干净**；
- 用户上次未保存的编辑内容**不在会话文件里**（只在未被生成的 autosave 里）。

退出对话框：

```python
# ui/main_window.py:2301-2305
2301:                reply = QMessageBox.question(
2302:                    self, "未保存的修改", msg,
2303:                    QMessageBox.Discard | QMessageBox.Cancel,
2304:                    QMessageBox.Cancel
2305:                )
```
用户在"放弃全部修改"与"取消退出"之间**没有"保存"选项**。

**最小复现（逻辑层，不依赖运行）**：写一个 `session.json` 含
`{"files":[{"filepath": "...", "modified": true}]}`，调 `restore()`，
断言恢复后的 `proxy.is_modified is False`（预测）而期望是 `True` 或内容被恢复。

**影响**
"关掉再开"这条最常见的路径上，用户的未保存修改在没有任何内容级备份的情况下消失，
而恢复后的界面暗示"文件是干净的"。

**建议修法**
1. 在 `MainWindow.__init__` 调用 `session.start_autosave()`（见 3.14），
   使内容备份真实存在。
2. `restore()` 中若 `file_info['modified']` 为真，应优先从
   `backup/autosave/<name>.tmp` 恢复内容并 `setModified(True)`。
3. 退出对话框增加 `QMessageBox.Save`，并对每个文件给出"保存/放弃/取消"三选。

---

### 3.16 【P2·疑似】崩溃恢复 × TabManager 注册 / 修改标记

**状态：疑似，静态定位，未动态复现（后半部分无法从静态代码确定，见"不确定"说明）。**

**涉及文件:行号**
- `app/session.py:1086-1098`

**确定的部分**

```python
# app/session.py:1069-1098（节选）
1069:                    # 用内存 provider 加载
1070:                    provider = MemoryProvider()
1071:                    provider.open(initial_text=content)
1072:
1073:                    # 用 EditorWidget 或 fallback
1074:                    if EditorWidget is not None:
1075:                        editor = EditorWidget(provider=provider)
...
1086:                    # 添加标签
1087:                    if hasattr(tabs, 'addTab'):
1088:                        idx = tabs.addTab(editor, title)      # ← 绕过 TabManager.open_file
1089:                        tabs.setCurrentIndex(idx)
...
1093:                    # 标记为已修改
1094:                    try:
1095:                        if hasattr(editor, 'proxy') and editor.proxy:
1096:                            editor.proxy.sc.setModified(True)  # ← 只动 Scintilla
```
- 恢复出来的标签用的是 `tabs.addTab(...)`，**没有**进入 `TabManager._editors`、
  没有文件监听器、没有 `_last_active` 记录、`document.filepath` 为 `None`。
- 恢复只设 `sc.setModified(True)`，**从不设 `proxy._modified`**。

**不确定的部分（诚实标注）**
`EditorProxy.is_modified` 读的是 `self._modified`（`core/editor.py:2107-2110`），
而 `self._modified` 的更新入口是 `sc.modificationChanged` 信号
（`core/editor.py:338-340` → `782-791`）。
`QsciScintilla.setModified(True)` 是否会发出 `modificationChanged(True)`，
我在本次审计中**无法验证**（需要运行 Qt，而 shell 不可用），
因此"恢复的标签看起来是干净的、不会被保存"这一后果列为**疑似**。

**影响（确定部分）**：恢复标签与 TabManager 的其他状态（编辑器列表、
关闭历史、监听器）不一致，`TabManager.get_all_tabs_info()`、`save_all()`、
`close_all_tabs()` 等按 `_editors`/`widget` 遍历的逻辑对该标签的行为不一致。

**建议修法**：改为给 `TabManager` 增加
`add_recovered_tab(text, title, original_path)` 方法，内部统一走
`EditorWidget` 构造 + `addTab` + `self._editors.append` +
`proxy._modified = True` + `_last_active` 记录 +
`proxy.modified_changed.emit(True)`。

**回归测试**：`tests/test_audit_interaction_state.py` 可扩展；
本报告未提供（需要构造 autosave 目录，见第 5 节）。

---

### 3.17 【P2】搜索栏 × 标签切换（匹配计数与高亮不随标签变化）

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `ui/panels.py:531` `_update_match_count`（只在搜索动作里被调）
- `ui/panels.py:497-529` `_do_highlight` / `_clear_highlight`（作用于 `current_proxy()`）
- `ui/main_window.py:1755-1807` `_on_tab_changed`（**完全不碰 `self.search_bar`**）
- `ui/main_window.py:309` `self.tabs.currentChanged.connect(self._on_tab_changed)`

**机制**
搜索高亮是指示器，存在各自的 `QsciScintilla` 上（所以切标签后旧标签的高亮保留、
新标签没有高亮 —— 这本身是合理的）。但**计数标签是全局的**：

```
$ grep -n "_update_match_count" -r ui
ui\panels.py:447:                self._update_match_count(0, 0, False)
ui\panels.py:454:                self._update_match_count(0, 0, False)
ui\panels.py:492:            self._update_match_count(1, result.count, True)
ui\panels.py:513:            self._update_match_count(count, count, count > 0)
ui\panels.py:529:        self._update_match_count(0, 0, False)
ui\panels.py:531:    def _update_match_count(self, current: int, total: int, found: bool):
```
`_on_tab_changed` 里没有任何对搜索栏的调用，所以切到另一个标签后，
"1/37"这样的计数仍然显示上一个标签的结果，而当前标签一处高亮都没有。

**最小复现步骤**
1. 在标签 A 搜索一个在 A 中出现 37 次的词 → 计数显示 "1/37"。
2. 切到标签 B（内容里没有该词）。
3. 观察：计数仍是 "1/37"，但 B 中无任何高亮。

**影响** 纯显示层不一致，误导用户认为当前文件有 37 处匹配。

**建议修法**：`_on_tab_changed` 中调用
`if self.search_bar: self.search_bar._clear_highlight()`，
或让 SearchBar 订阅 `bus.tab_changed` 并重新对当前编辑器执行高亮+计数。

---

### 3.18 【P2】主题应用 × 编辑器偏好（"高亮当前行"被强制打开）

**状态：静态定位，未动态复现。**

**涉及文件:行号**
- `infrastructure/theme_loader.py:927` `editor.setCaretLineVisible(True)`
- `ui/editor_view.py:269-272`（偏好 `show_current_line`）

**机制**

```python
# infrastructure/theme_loader.py:926-928
926:            # 当前行高亮
927:            editor.setCaretLineVisible(True)
928:            editor.setCaretLineBackgroundColor(QColor(colors.current_line))
```
```python
# ui/editor_view.py:269-272
269:        self.setCaretLineVisible(
270:            self.prefs.get("show_current_line", True)
271:        )
272:        self.setCaretLineBackgroundColor(QColor("#f0f0f0"))
```
用户在首选项里关掉"高亮当前行"，一旦切换主题就会被重新打开，
且**不会再被同步**（`apply_preferences` 只在首选项保存时调用，
`ui/editor_view.py:1212-1241`）。UI 复选框与编辑器实际状态不一致。

**最小复现步骤**

```python
from PyQt5.Qsci import QsciScintilla
from infrastructure.theme_loader import BuiltinThemes, ThemeLoader

sc = QsciScintilla()
sc.setCaretLineVisible(False)          # 用户设置
ThemeLoader().apply(sc, BuiltinThemes.light_clean())
print(sc.caretLineVisible())
# 期望: False
# 预测实际: True
```

**建议修法**：`ThemeLoader.apply` 不应改动与颜色无关的可见性开关；
若确实要对齐，应从 `editor.prefs` 读 `show_current_line` 而不是硬编码 `True`。

---

### 3.19 【P2】LSP 诊断 × URI（跨文件/跨标签绘制）

**状态：静态定位，未动态复现。**

**涉及文件:行号** `core/editor.py:1951-1996`

**机制**

```python
# core/editor.py:1951-1962
1951:    def _on_lsp_diagnostics(self, uri: str, diagnostics: List[Dict]):
1952:        """LSP 诊断结果回调"""
1953:        try:
1954:            # 清除旧诊断
1955:            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
1956:            self.sc.SendScintilla(
1957:                QsciScintilla.SCI_SETINDICATORCURRENT,
1958:                INDICATOR_LSP_ERROR
1959:            )
1960:            self.sc.SendScintilla(
1961:                QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length
1962:            )
1963:
1964:            # 绘制新诊断
1965:            for diag in diagnostics:
```
`uri` 参数**从头到尾没有被使用**，也没有与 `self._lsp_uri` 比较。
只要某个 `LspClient` 把诊断发到这个代理上，任何来源的诊断都会被绘制。
当前每个 `EditorProxy` 持有自己的 `LspClient`（`core/editor.py:1869`），
所以这更像一个**潜在**通道；但在另存为后（3.10）旧 URI 的诊断会持续到达，
或未来共享 LspClient 时就会变成真实的跨标签泄漏。

**最小复现步骤**

```python
proxy._lsp_uri = "file:///D:/tmp/a.py"
proxy._on_lsp_diagnostics(
    "file:///D:/tmp/other.py",
    [{"range": {"start": {"line": 0, "character": 0},
                "end":   {"line": 0, "character": 1}},
      "message": "x", "severity": 1}],
)
print(sc.SendScintilla(getattr(sc, "SCI_INDICATORVALUEAT", 2082), 2, 0))
# 期望: 0（不属于本文档的诊断不应绘制）
# 预测实际: 非 0
```

**建议修法**：方法首行加
`if self._lsp_uri and uri != self._lsp_uri: return`。

---

## 4. 测试覆盖盲区（哪些交互完全没有测试）

我用 `grep` 逐个确认了现有 28 个测试文件的覆盖范围。

### 4.1 完全没有测试的交互

| 交互 | 现状证据 |
|---|---|
| **Vim × 自研 UndoManager** | `tests/test_vim_mode.py:16` 用**裸 `QsciScintilla`**（内置撤销栈是开的），11 个测试里**没有 `u`/`Ctrl+R`**。生产路径是 `EditorProxy`（内置撤销栈被禁用）。 |
| **撤销栈 × 命令合并 × redo 失效** | `tests/test_undo.py` 有 `test_begin_end_group`(185)、命令合并、深度限制，但**没有**"合并后 redo 必须失效"这类断言；也从不构造"undo 之后再编辑"的序列。 |
| **另存为 × 内容一致性** | 全仓 grep `_save_file_as` 只命中 `ui/main_window.py:407`（菜单接线）与实现处，**没有任何测试**。 |
| **编辑器内容 × provider 同步** | 没有任何测试断言 `proxy.document.provider.read_text() == proxy.sc.text()`。 |
| **空闲释放 × 保存** | `_release_tab_content` / `_check_idle_tabs` 在 `tests/` 下 **0 引用**。 |
| **外部文件变更 × 撤销** | `_reload_file` / `_on_file_changed` 在 `tests/` 下 **0 引用**（`tests/test_document.py` 只测 `Document._on_file_changed` 的 mtime 路径）。 |
| **宏回放 × 撤销** | `tests/` 下**没有任何宏测试文件**（grep `MacroRecorder` 只命中 `core/macro.py` 自身）。 |
| **主题 × 组件颜色** | 全仓 grep `adapt_qss_colors` 只命中实现与 14 个面板，**`tests/` 下 0 引用**；没有任何主题测试文件（`tests/` 无 `test_theme*`）。 |
| **主题切换 × 偏好** | 同上。 |
| **编码切换 × 保存** | `tests/test_document.py` 有 `change_encoding` 相关用例（`doc.set_text` 路径），但**没有**"切换编码后编辑器文本必须同步"或"再保存不得损坏"的断言。 |
| **行尾切换 × 保存** | grep `set_eol` / `convert_eol` 在 `tests/` 下 **0 引用**。 |
| **LSP × 另存为 / 重命名** | `tests/test_lsp_did_open.py`、`test_lsp_integration.py`、`test_lsp_real_server.py` 覆盖 `did_open`/`did_change`/真服务器，但**没有**文件路径变更场景。 |
| **LSP 诊断 × URI 隔离** | 没有测试断言"外来 URI 的诊断不得绘制"。 |
| **插件热重载 × 菜单/工具栏/快捷键** | `tests/test_plugin_updater_close.py` 只测插件更新器关闭；**没有** `PluginAPI` 菜单计数的往返测试。 |
| **`unsubscribe` 完整性** | `tests/test_plugin_permissions.py` 只测权限；没有 subscribe/unsubscribe 对称性测试。 |
| **自动保存定时器是否启动** | 无测试。 |
| **会话恢复 × 修改标记** | `tests/test_e2e.py` 有会话相关用例，但没有断言 `modified` 字段被应用。 |
| **崩溃恢复 × TabManager 注册** | `tests/` 下 `check_and_recover_crash` / `_recover_files` 0 引用。 |
| **搜索栏 × 标签切换** | `tests/test_searchbar_next_prev.py`、`test_search.py`、`test_search_performance.py` 都在单文档上测，**没有**切标签场景。 |

### 4.2 有测试但**测错对象**的（比没测更危险）

| 测试 | 问题 |
|---|---|
| `tests/test_vim_mode.py:16` | 用裸 `QsciScintilla`，与生产用的 `EditorProxy` 环境（内置撤销栈已禁用）**不同构**，因此掩盖了 3.3。 |
| `tests/test_search.py` / `test_searchbar_next_prev.py` | 直接用 `MemoryProvider` 灌文本再搜，所以永远搜得到；而生产里 provider 是**过期**的，掩盖了 3.2。 |
| `tests/test_undo.py:185-220` | 手工 `begin_group` + `record` + `end_group`，只验证"组内合并成一条"，**从未验证 redo 失效**，掩盖了 3.4。 |

### 4.3 现有的 262 passed 为什么没有拦住这些

因为它们**几乎全是单功能、单对象测试**：每个测试只构造一个 Provider / 一个
EditorProxy / 一个面板，从不构造"两个功能同时活跃"的状态
（`EditorProxy` + 主题切换 / `TabManager` + 空闲定时器 / `PluginAPI` + cleanup + 再次注册）。
本报告新增的 6 个文件正是针对这一点。

---

## 5. 未覆盖 / 不确定（如实列出）

### 5.1 完全未覆盖（本次没做，也没写测试）

1. **撤销 × LSP 重命名（rename）** —— 未审计。需要运行语言服务器并使用
   `WorkspaceEdit` 回写文本；本次无法执行，也没有读 `core/refactor_session.py`
   与 LSP rename 的接线代码，**不做任何结论**。
2. **撤销 × 格式化（formatter）** —— 未审计。`core/formatter.py` 与
   `ui/main_window` 的格式化动作接线没有读完，**不做结论**。
3. **撤销 × 代码片段展开 / 自动配对 / 折叠 / 缩进彩虹** —— 未审计。
4. **minimap × 标签切换 × 大文件释放** —— `_release_tab_content` 清空内容后
   minimap 的 `set_editor` 不会被重新触发（`ui/main_window.py:1789-1795` 只在
   切标签时设置），因此释放+恢复后 minimap 可能显示空内容。**我读到了相关代码
   但未完整验证恢复路径**，列为**未确认**。
5. **Git 面板 × 外部变更 / 另存为** —— 未审计。
6. **配置同步（`app/sync.py`）× 运行中的编辑器状态** —— 未审计。
   `apply_synced_data`（`app/sync.py:857`）会改配置，是否会让已打开的编辑器
   与新配置不一致，我没有读该函数，**不做结论**。
7. **终端面板 × 主题 / 关闭** —— 只读了 `refresh_theme`，未审计进程生命周期。
8. **多窗口（`ui/detached_window.py`、`_new_window`）× 会话 / 插件 / 撤销** —— 未审计。
   只注意到 `ui/detached_window.py:36` 也调 `self.editor.proxy.save_file()`。
9. **`collab.py` / `file_merge.py` / `refactor_session.py` 的交互** —— 未审计。

### 5.2 已定位但结论强度有限（"疑似"）

1. **3.16**：`QsciScintilla.setModified(True)` 是否发出 `modificationChanged`
   进而更新 `proxy._modified` —— 需要运行才能确定；因此"恢复标签看起来干净"
   只是**疑似**。
2. **3.19**：LSP 诊断跨标签在当前"每代理一个 LspClient"的架构下是否**真的**会被
   触发 —— 我确认了缺少 URI 校验（确定），但没有确认实际有跨文件诊断到达
   （需要跑真语言服务器）。因此定为 P2 而非 P1。
3. **3.12**：删除时机的细节（`deleteLater` 与 `menuAction` 的父子关系）是 Qt
   语义推断。我确认了"cleanup 用延迟删除 + add_menu 复用已存在子菜单"这两条
   事实；"新菜单项被一起销毁"是**基于 Qt 文档的推断**，未运行验证。
4. **`adapt_qss_colors` 的 3 位色替换风险**：表里有 `('#888', ...)`、`('#666', ...)`、
   `('#555', ...)`，理论上会误伤 `#888xxx` 这类 4/8 位十六进制值。
   我 grep 了仓内所有 `*.py` 与 `*.qss`，**没有找到** `#(888|666|555)[0-9a-fA-F]`
   形式的值，所以这条**在当前代码库中不成立**，仅作为未来风险记录。
   真正成立的是 3.5 的链式替换。

### 5.3 交叉印证说明

- 3.2（另存为写入旧内容）与 `docs/audit_data_integrity.md` 结论 B 完全一致 ——
  两名审计员独立阅读同一条调用链得到同一结论，可信度更高。
- 3.7（保存时的行尾改写）与 `docs/audit_data_integrity.md` 结论 E 部分重合：
  该报告从"数据往返"角度发现 `save_file` 主动改写字节；我从"用户切换 EOL 是否生效"
  角度发现 `meta.eol` 无人读取。两者互补。
- 3.14（自动保存定时器未启动）与 `docs/audit_data_integrity.md` 结论 C 一致 ·
  该报告称之为 P0（未保存内容 100% 丢失），我按"自动保存×未保存标记"的交互
  视角定为 P1；**该报告的定级更严重，请以它为准**。

---

## 6. 本次交付的测试文件（全部未运行）

| 文件 | 覆盖 | 预期失败的用例数 |
|---|---|---|
| `tests/test_audit_interaction_undo.py` | 3.3、3.4 | 5 失败 / 1 通过（共 6） |
| `tests/test_audit_interaction_state.py` | 3.1、3.2、3.9 | 10 失败（共 10） |
| `tests/test_audit_interaction_theme.py` | 3.5、3.18 | 4 失败 / 1 通过（共 5） |
| `tests/test_audit_interaction_file_io.py` | 3.6、3.7、3.10、3.19 | 7 失败（共 7） |
| `tests/test_audit_interaction_macro.py` | 3.8 | 3 失败（共 3） |
| `tests/test_audit_interaction_plugin.py` | 3.12、3.13 | 2 失败 / 3 通过（共 5） |

> 「预期通过」的用例是**故意**放进去的对照组：它们验证缺陷的边界
> （例如工具栏项与快捷键项在热重载后**确实**正常、`cleanup()` 的
> 事件解绑**确实**正确、混合编辑后撤销栈**确实**能回到空文档）。
> 如果这些对照组也失败，说明要么我的分析错了，要么测试自身有 bug ——
> 这是设计上的自我纠错信号。


运行方式（需要有 shell 权限的会话）：

```powershell
cd D:\QingCaoEditor
python -m pytest tests/test_audit_interaction_undo.py tests/test_audit_interaction_state.py `
                 tests/test_audit_interaction_theme.py tests/test_audit_interaction_file_io.py `
                 tests/test_audit_interaction_macro.py tests/test_audit_interaction_plugin.py -v
```

**重要**：这些文件我从未执行过。它们**可能包含笔误**（fixture 名称、API 参数、
Qt 常量导出情况都需要实跑校验）。请把它们当作"待验证的假设"，不是"已验证的结论"。
若某个用例因为测试自身的 bug 而失败，请以第 3 节的**静态证据（文件:行号 + 代码片段）**
为判断依据 —— 那部分是真实的代码事实。

同时提醒：**在修复前不要把这 6 个文件并入常规 CI**，
否则 `python -m pytest tests -q` 会从 262 passed 变成大量 failed
（这正是本审计的结论，但需要人先确认）。

---

## 附录 A：本报告结论的静态证据索引

| 结论 | 关键文件:行号 |
|---|---|
| 3.1 空闲释放 × 保存清空文件 | `app/tabs.py:72,202-205,1463-1488,1490-1528,1581-1603` · `core/editor.py:645-739,461-526` · `core/content_provider.py:688-782`（截断 749-750） |
| 3.2 另存为写旧内容 | `ui/mixins/file_ops_mixin.py:202-238`（230） · `core/editor.py:461-552` · `core/content_provider.py:648-686,815-884` |
| 3.2 查找/替换基于过期 provider | `ui/panels.py:443,640-653` · `core/editor.py:1446,1504` · `ui/main_window.py:1919-1939` |
| 3.3 Vim u/Ctrl+R 失效 | `core/vim_mode.py:88,230` · `core/editor.py:344-346` · `ui/editor_view.py:505-513` · `ui/main_window.py:1539-1545` · `tests/test_vim_mode.py:16` |
| 3.4 合并不清 redo | `core/undo.py:242-280,324-381` · `core/commands.py:319-336,619-629` · `core/editor.py:695-711` |
| 3.5 主题 QSS 链式替换 | `infrastructure/theme_loader.py:627-707`（656/657/659/678） · `436,443,478,482` · 14 个 `refresh_theme` |
| 3.6 编码切换 × 保存 | `ui/mixins/status_bar_mixin.py:177-188` · `core/document.py:593-615` · `core/content_provider.py:306-311,960-975` |
| 3.7 行尾切换 × 保存 | `ui/mixins/status_bar_mixin.py:191-205` · `core/document.py:620-623,632-666` · `core/editor.py:475-491` |
| 3.8 宏回放不入栈 | `core/macro.py:529-658,619-626,702-718` · `core/editor.py:645-739,344-346` |
| 3.9 外部变更 × 撤销 | `app/tabs.py:1344-1458`（1415-1423,1425-1429,1443-1449） |
| 3.10 另存为 × LSP | `core/editor.py:218,750-780,1895,2018-2028` · `ui/mixins/file_ops_mixin.py:230` |
| 3.11 另存为 × 标记/监听 | `ui/mixins/file_ops_mixin.py:228-235` · `core/editor.py:496-518` · `app/tabs.py:528,1318-1342` |
| 3.12 热重载 × 菜单 | `app/plugins.py:559-628,641-680,685-708,1516-1565` · `infrastructure/plugin_loader.py:1086-1204,1339-1381` |
| 3.13 unsubscribe 不完整 | `app/plugins.py:772-836` |
| 3.14 自动保存未启动 | `app/session.py:116-118,147-171,782-878` · `ui/main_window.py:208` · `main.py:1096-1100` |
| 3.15 会话 × 修改标记 | `app/session.py:217-329,550-702` · `ui/main_window.py:2293-2309` |
| 3.16 崩溃恢复 × 注册 | `app/session.py:1069-1098` |
| 3.17 搜索栏 × 切标签 | `ui/panels.py:447-531` · `ui/main_window.py:309,1755-1807` |
| 3.18 主题 × 当前行偏好 | `infrastructure/theme_loader.py:927` · `ui/editor_view.py:269-272,1212-1241` |
| 3.19 诊断 × URI | `core/editor.py:1951-1996` |

## 附录 B：本次审计使用的方法与限制

- **工具**：`read`（逐行读源码）、`grep`（正则搜索 + 全仓引用统计）、`glob`（文件枚举）、
  `write`（写测试与报告）。**未使用任何可执行通道**（不可用，见第 0 节）。
- **方法**：对每个交互，先定位两端的入口函数，再沿调用链核对
  "A 产生的状态变化是否被 B 感知"，最后用 `grep` 确认关键函数/字段的
  调用点数量（0 调用点 = 死代码或未接线）。
- **限制**：
  1. 无运行输出，所有行为均为**代码推导的预测**；
  2. 无法确认 Qt/QScintilla 的运行时语义（`setModified` 是否发信号、
     `deleteLater` 与 `menuAction` 的精确交互、`SCI_CLEARALL` 是否一定发
     `SCN_MODIFIED`）—— 这些直接影响 3.12 / 3.16 的最终结论；
  3. 未审计的模块见 5.1，其中 **LSP rename × 撤销** 与 **格式化 × 撤销**
     是任务明确要求排查但我未能完成的两项，属于本次审计的**已知缺口**。
