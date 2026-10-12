# 数据完整性审计报告 —— 青草编辑器 (QingCaoEditor)

- 审计对象：`D:\QingCaoEditor`（PyQt5 代码编辑器，Python 3.11.9 / Windows）
- 审计范围：文件读写、编码、保存、崩溃恢复、配置持久化链路
- 审计员角色：数据完整性审计员（独立于开发方）
- 报告日期：本次会话
- 报告文件：`docs/audit_data_integrity.md`（UTF-8）

---

## 0. 关于"实证"的诚实声明（请先读这一节）

**本次审计未能执行任何 shell 命令，因此本报告中不存在任何真实运行输出。**

审计会话的 `pwsh` 工具在**进程启动阶段**即失败，与命令内容无关：

```
Error: SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)
```

已尝试过的全部路径（全部失败，非未尝试）：

| 尝试 | 参数 | 结果 |
|---|---|---|
| 1 | `Get-Location; Get-ChildItem -Force`（默认 sandbox） | `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\QingCaoEditor)` |
| 2 | `echo hello`（默认 sandbox） | 同上 |
| 3 | `echo hello`（`workdir=C:\Users\Administrator\AppData\Local\Temp`） | 同上（沙箱仍尝试对工作区根目录授权） |
| 4 | `echo hello`（`run_in_background=true`） | 后台作业 `pwsh-1006` 同样 `status: failed`，同一错误 |
| 5 | `python --version`（`sandbox_permissions="danger-full-access"`） | `the user rejected escalating this command ... it stays denied` |

根因判断（**推断，未验证**）：沙箱在 spawn 子进程前调用 `SetNamedSecurityInfoW` 授予
`D:\QingCaoEditor` 写权限，当前账户对该目录不具备 `WRITE_DAC`，得到 Win32 5（拒绝访问）；
而本会话的提权审批被策略关闭（`Approval prompts are disabled in this session`），
因此**没有任何绕过途径**。这是环境缺陷，不是命令写错。

**由此产生的报告性质变化，必须让读者知道：**

- 本报告的**全部结论来自静态代码审计**（`read` / `grep` 工具，逐行核对调用链）。
- 所有涉及运行行为的内容一律标注为 **「静态判定，未执行」**。
- 第 3 节的往返一致性矩阵中的"实测"列**全部为 `未执行`**；同表的"静态预判"列是
  代码推导的**预测**，不是观测值。请勿把预测当作实测引用。
- 为了让有 shell 权限的会话能一键复现，我编写了
  [audit_data_integrity_harness.py](tests/audit_data_integrity_harness.py)
  （覆盖 A 往返矩阵 / B 块边界 / C 外部修改 / D 失败注入 / E 崩溃恢复）。
  **该脚本本身也从未被执行过**，可能存在自身的 bug；它的价值是"待跑"，不是"已跑"。
- 由于无法运行，**"未复现"与"确认存在"在本报告中是两种不同强度的结论**，
  我在每条发现里都明确标注了属于哪一种。

---

## 1. 结论摘要（按严重度排序）

### 结论 A — P0：打开任何 > 64 KiB 的多字节文本，字符只要跨块边界就必然损坏，且保存后不可逆
`EditorProxy._load_content` 对每个 64 KiB 块**独立调用 `decode()`**，再逐块 `append` 到
QScintilla；`decode()` 使用 `errors='replace'`。任何跨 `k*65536` 边界的多字节字符都被
拆成两半、各自替换为 U+FFFD。对 UTF-8 中文（3 字节/字）来说，某个给定块边界落在字符中间的
概率约 2/3。用户随后保存时，编辑器内容被重新编码写回 → 原字节**永久消失**。
证据：`core/editor.py:426-440`、`core/content_provider.py:299-304`、`core/content_provider.py:581-582`。
**静态判定，未执行**（复现脚本 B1）。

### 结论 B — P0：「另存为」写入的是**上一次保存时的旧内容**，而不是编辑器里的当前内容
`ui/mixins/file_ops_mixin.py:230` 调用 `proxy.document.save(path)`，**绕过了**
`EditorProxy.save_file()` 里的 `_sync_content_to_provider()`。
`Document.save()` → `LocalFileProvider.save(new_path)` → `_save_as_full()` → `read_all()`
读的是 mmap 里的**原始磁盘字节**（因为编辑期间 provider 的脏块为空）。
随后 `Document.save()` 把 `meta.filepath` 改成新路径、`meta.modified=False`、**删除草稿**、
并发出 `saved` 信号。结果：新文件内容是（未编辑的）原始文件，程序状态却宣布"已保存"。
用户接着关标签页 → 编辑内容全部丢失。
证据：`ui/mixins/file_ops_mixin.py:202-238`、`core/document.py:359-446`、
`core/content_provider.py:648-686`、`core/content_provider.py:815-896`。
**静态判定，未执行**（复现脚本 C 扩展项，见第 5 节遗漏说明）。

### 结论 C — P0：崩溃后未保存内容 100% 丢失 —— 自动备份定时器从未启动
`SessionManager.start_autosave()` 在全仓库**没有任何调用点**（grep 确认只有定义处
`app/session.py:147`）。`save_autosave()` 只被 `_autosave_tick()` 调用，而 `_autosave_tick`
只由那个从未启动的定时器触发。主窗口的 2 分钟定时器 `_session_timer`
（`ui/main_window.py:241-243`）走的是 `_autosave_session()`，它只调用 `session.save()`
（仅保存文件名/光标，**不含任何正文**）。
`core/document.py` 的 60 秒草稿定时器写的是**provider 的旧内容**而非编辑器内容，且**没有任何
代码读取 `.draft` 文件**。
因此崩溃（尤其 `os._exit` / 段错误，`sys.excepthook` 与 `atexit` 都不触发）后，
`main.py:1004-1019` 去找的 `backup/autosave/meta.json` 永远不会存在。
证据：`app/session.py:147-171`、`ui/main_window.py:1998-2015`、`core/document.py:1015-1052`。
**静态判定（grep 全仓 + 调用链核对），未执行**（复现脚本 E）。

### 结论 D — P0：Ctrl+S 是"就地覆盖 + 截断"，不是原子写；断电压根没有安全网
`LocalFileProvider.save()` 只有在**目标路径与原路径不同**时才走 `_save_as_full()`
（临时文件 + `os.replace`）。而 `EditorProxy.save_file()` 每次保存都会先
`clear_dirty()` 再**写满全部块**（`core/editor.py:528-552`），所以最常见的
"编辑已有文件后 Ctrl+S"必然走 `_save_dirty_blocks()`：直接 `open(target,'r+b')`、
按偏移写入、`truncate()`、最后才 `fsync`。写入过程中断电或写盘失败 → 半截文件，
**原文件已被覆盖，没有任何备份副本**。
注意 `core/content_provider.py:652` 的 docstring 自称"使用原子写入（临时文件 + 重命名）
避免中途失败损坏文件"，与 `_save_dirty_blocks` 的实现**直接矛盾**。
证据：`core/content_provider.py:648-686, 688-782, 815-896`。
**静态判定，未执行**（复现脚本 D）。

### 结论 E — P1：默认开启的"保存时清理"会改写用户的字节 —— CRLF→LF、去行尾空白、补末尾换行
`core/editor.py:476-484`：

```python
settings = QSettings("QingCao", "Editor")
if settings.value("trim_trailing_whitespace", True, type=bool):
    lines = [l.rstrip() for l in text.splitlines()]   # 顺带把所有行尾统一成 \n
    text = '\n'.join(lines)
if settings.value("insert_final_newline", True, type=bool):
    if text and not text.endswith('\n'):
        text += '\n'
```

默认值确实为 `True`（`app/preferences.py:137-138`）。于是：
CRLF 文件保存一次后全文变成 LF；行尾空白（Markdown 硬换行 `  `、reST、Makefile、
**Python 三引号字符串内部的尾随空格**）被静默删除；原本没有末尾换行的文件被加上换行。
`document.meta.eol` 仍然记录 CRLF，与磁盘上的 LF 不一致。
证据：`core/editor.py:473-491`、`app/preferences.py:137-138`。
**静态判定，未执行**（复现脚本 A 的 `editor` 路径 + 隔离验证）。

### 结论 F（附加，同类重要性）— P1：保存失败被吞掉，UI 仍然提示"已保存"
`ui/mixins/file_ops_mixin.py:194-196`：

```python
proxy.save_file()
self.status_bar.showMessage("已保存", 2000)
```

返回值被忽略。`_save_file_as`（同文件 230 行）同样忽略 `document.save(path)` 的返回值。
只读文件、目录无写权限、磁盘写满、Windows 共享冲突等情况下，用户会看到"已保存"。
（缓解因素：`EditorProxy.save_file` 失败时不发 `modified_changed(False)`，标题栏的
修改标记会保留；但状态栏在骗人。）
**静态判定，未执行**（复现脚本 D）。

---

## 2. 逐项发现（含触发条件、后果、修法）

### P0-1 逐块独立 decode 导致跨块多字节字符损坏

- **位置**：`core/editor.py:414-440`（加载）、`core/editor.py:442-459`（延迟加载）、
  `core/content_provider.py:299-304`（`decode` 用 `errors='replace'`）、
  `core/content_provider.py:561-606`（`read_block` 边界）、
  `core/content_provider.py:47`（`DEFAULT_BLOCK_SIZE = 64*1024`）
- **证据（静态代码）**：

  ```python
  # core/editor.py:436-440  「小文件一次性加载」
  for i in range(total):
      data = provider.read_block(i)
      text = provider.decode(data)      # ← 每个 64KB 块单独解码
      self.sc.append(text)
  ```

  ```python
  # core/content_provider.py:299-304
  def decode(self, data: bytes) -> str:
      try:
          return data.decode(self._encoding, errors='replace')   # ← 半个字符 → U+FFFD
  ```
- **预期**：加载后的编辑器文本应等于 `整文件字节.decode(encoding)`。
- **静态判定**：当 `65536 % n != 0`（n 为该字符的字节长度）且字符跨越块边界时，
  编辑器文本中出现 U+FFFD，与预期不等。**未执行，未复现。**
- **触发条件**：文件 > 64 KiB（UTF-16 的代理对在 4 字节跨界时同理），
  中存在跨 `k * block_size` 边界的多字节字符。
- **数据损失后果**：字符在屏幕上显示为 `�`；用户一旦保存，
  `_sync_content_to_provider` → `provider.encode(text)`（`errors='replace'`）把 U+FFFD
  写成 `EF BF BD`（UTF-8）或 `3F`（GBK），**原字节不可逆地消失**。
  文件越大、中文越密，命中率越高。
- **建议修法**：不要再对块做解码。改为
  `text = provider.decode(b''.join(provider.read_block(i) for i in range(total)))`，
  或提供 `provider.iter_text_chunks()`：用增量解码器
  （`codecs.getincrementaldecoder(encoding)(errors='strict')`）跨块保持状态，
  并让 `read_block` 的边界按编码对齐（见 P0-1b）。
- **同类问题 P0-1b**：`read_block` 的排序语义要求调用方**按序拼接**，
  但 `_load_content` 把每块单独解码后 `append`，等于假设"块边界 = 字符边界"，
  这个假设对 UTF-8/GBK/UTF-16/Big5/Shift_JIS 全部不成立。

---

### P0-2 「另存为」写入旧内容并清除脏标记

- **位置**：`ui/mixins/file_ops_mixin.py:202-238`（尤其 230 行）、
  `core/document.py:359-446`、`core/content_provider.py:678-679` 与 `815-896`
- **证据（静态调用链）**：

  ```
  _save_file_as()
    └─ proxy.document.save(path)          # file_ops_mixin.py:230  ← 绕过 proxy.save_file()
         └─ Document.save(path)           # core/document.py:359
              └─ provider.save(target)    # core/document.py:394
                   └─ target != self._filepath → _save_as_full(target)   # content_provider.py:678
                        └─ full_data = self.read_all()   # content_provider.py:821 ← mmap 原始字节
  ```

  对比 Ctrl+S 路径：`_save_file` → `proxy.save_file()` →
  `core/editor.py:491 _sync_content_to_provider(text)` → 才 `document.save()`
  （`core/editor.py:494`）。**只有 Ctrl+S 会把编辑器内容写进 provider。**
- **预期**：另存为应写出编辑器当前内容；实际（静态判定）写出 provider 中上一次同步的字节。
- **未执行，未复现。**
- **触发条件**：打开一个文件 → 修改（**不保存**）→ 文件菜单"另存为" → 选择新路径。
- **数据损失后果**：
  1. 新文件内容是**未编辑的旧内容**，但用户以为保存成功了；
  2. `core/document.py:404-409` 把 `meta.filepath` 指向新文件、`meta.modified=False`；
  3. `core/document.py:427` 调用 `delete_draft()`，把唯一的草稿删掉；
  4. 此后关闭标签页/程序，`closeEvent`（`ui/main_window.py:2293-2309`）因为
     `is_modified == False` **不会提示未保存**，编辑内容静默消失。
- **加重情节**：`DocumentModel.save_all()`（`core/document.py:1459-1473`）直接调
  `doc.save()`，同样是旧内容路径。（`app/tabs.py:1581-1603` 的 `save_all`
  用的是 `proxy.save_file()`，这条是对的。）
- **建议修法**：`_save_file_as` 改为
  `proxy.save_file(path)`（`EditorProxy.save_file` 已经支持 `filepath` 参数），
  或在 `Document.save()` 开头无条件先做一次 `_sync_editor_to_provider()`；
  并给 `Document.save()` 增加"目标不同则不得清除 modified 标记"的断言。

---

### P0-3 崩溃自动备份功能完全未接线

- **位置**：`app/session.py:147-150`（`start_autosave` 无调用者）、
  `app/session.py:156-171`（`_autosave_tick`）、`app/session.py:782-874`（`save_autosave`）、
  `ui/main_window.py:241-243` + `1998-2015`（定时器只存 session.json）、
  `main.py:1004-1019`（启动时查找 `backup/autosave/meta.json`）、
  `core/document.py:1015-1052`（草稿写的是旧内容、无读取方）
- **证据（静态 grep 结果，全仓库）**：
  `start_autosave` 仅 1 处命中 —— `app/session.py:147` 的 `def` 本身；
  `save_autosave` 的调用者只有 `app/session.py:168`（在 `_autosave_tick` 内）。
- **预期**：崩溃重启后能恢复崩溃前未保存的编辑器内容。
- **静态判定**：`backup/autosave/` 目录永远不会被创建，因此
  `check_and_recover_crash()`（`app/session.py:924-930`）在 `meta.json` 检查处直接
  `return 0`。**未执行，未复现。**（脚本 E 会实际打印 `meta.json 存在=False`。）
- **触发条件**：任何崩溃 / 断电 / 任务管理器强杀，且存在未保存修改。
- **数据损失后果**：未保存内容全部丢失，且用户不会收到"有可恢复内容"的提示。
- **附带缺陷（P1）**：`core/document.py:1043` 的草稿写的是
  `self.get_text()` = `provider.read_text()`。由于 `EditorProxy` 只在
  `save_file()` 里同步内容（`core/editor.py:491`），编辑期间 provider 一直是**旧字节**，
  所以草稿内容是"上次保存时的磁盘内容"，不是用户正在编辑的内容。
  并且 `_save_draft` 不重启定时器，而 `mark_modified()`（`core/document.py:502-503`）
  只在"第一次修改"时启动它 → **草稿最多只会写一次**。
  最后，全仓库没有任何代码读取 `*.draft`（grep `draft` 只命中 `delete_draft`）。
- **建议修法**：
  1. 在 `MainWindow.__init__` 或 `deferred_init` 中调用 `self.session.start_autosave()`；
  2. 让 `_session_timer` 同时调用 `session.save_autosave(...)`，或在
     `_autosave_session()` 内追加 `self.session.save_autosave(self.tabs, self)`；
  3. `core/document.py` 的草稿应写 `editor.proxy.sc.text()`（或在 `_on_scintilla_modified`
     里增量同步 provider），并让 `_save_draft` 结束时重启定时器；
  4. 实现草稿读取（或用 `save_autosave` 完全取代 `_save_draft`，删除死代码）。

---

### P0-4 保存不是原子的

- **位置**：`core/content_provider.py:688-782`（`_save_dirty_blocks`）、
  `core/content_provider.py:648-686`（`save` 的分派）、
  `core/content_provider.py:815-896`（`_save_as_full`，唯一原子路径）
- **证据（静态代码）**：

  ```python
  # core/content_provider.py:732-753
  with open(target, 'r+b') as f:                 # ← 直接打开原文件
      for block_id, data in self._dirty_blocks.items():
          f.seek(block_id * self._block_size)
          f.write(bytes(data))                   # ← 原地逐块覆盖
      ...
      if new_size < on_disk:
          f.truncate(new_size)                   # ← 原地截断
      f.flush()
      os.fsync(f.fileno())                       # ← 到这里才落盘
  ```

  而 docstring（652 行）写的是"使用原子写入（临时文件 + 重命名）避免中途失败损坏文件"。
- **触发条件**：编辑已有文件后 Ctrl+S（因为 `_sync_content_to_provider` 会把全部块标脏，
  所以**每一次 Ctrl+S 都是整文件重写**）；此过程中断电、蓝屏、进程被杀、
  `fsync` 因磁盘满/IO 错误失败。
- **数据损失后果**：文件处于"新内容前缀 + 旧内容尾部"或长度已被 `truncate` 的混合状态，
  **没有可回退的副本**。WAL/日记文件系统只能保证元数据一致性，不能保证内容。
- **未执行，未复现。**
- **建议修法**：让 `save()` 无条件走原子路径 —— `mkstemp` 到同目录 → 写入完整新内容 →
  `flush` + `fsync` → 在 Windows 上用 `os.replace` 覆盖目标 → 对目录 `fsync`（POSIX）。
  仅在"文件极大且只有少量脏块"时才考虑原地写，且必须先写 `path.bak` 侧车副本。
  文档字符串与实现必须二选一改掉。

---

### P1-1 默认的保存期文本规范化改变用户字节（CRLF / 行尾空白 / 末尾换行）

- **位置**：`core/editor.py:476-491`；默认值 `app/preferences.py:137-139`
- **证据**：

  ```python
  # core/editor.py:478-484
  if settings.value("trim_trailing_whitespace", True, type=bool):
      lines = [l.rstrip() for l in text.splitlines()]   # splitlines 会吃掉 \r\n / \r / \n
      text = '\n'.join(lines)                           # ← 行尾一律变 LF
  if settings.value("insert_final_newline", True, type=bool):
      if text and not text.endswith('\n'):
          text += '\n'
  ```

- **预期**（往返一致性要求）：只改动用户实际编辑的位置，其余字节不变。
- **静态判定**：CRLF 文件必失败；有行尾空白的文件必失败；无末尾换行的文件必失败。
  `trim_trailing_whitespace` 是**用户可见开关**（`app/preferences.py:724-729`），
  但默认开启且首次安装的用户不知道。
- **触发条件**：打开任何 CRLF / 带尾随空白 / 无末尾换行的文件并按 Ctrl+S。
- **数据损失后果**：
  - 语义级：Python 三引号字符串、Makefile（`\` 续行后不能有空格）、
    Markdown 硬换行（行尾两个空格）、YAML 块标量内的尾随空格被改写；
  - 工程级：整个文件在 Git 中显示为全量改写，污染 blame/history；
  - 元数据不一致：`meta.eol` 仍是 `\r\n`，磁盘是 `\n`，
    下次"转换行尾符"会做一次无意义的全文件重写。
- **未执行，未复现。**
- **建议修法**：
  1. 两个开关默认改为 `False`（至少"保存时自动执行"应默认关闭并在首选项中明确提示）；
  2. 行尾策略应遵循 `document.meta.eol`：
     `text.replace('\r\n','\n').replace('\r','\n')` 后按 `meta.eol` 还原，
     而不是无条件 `'\n'.join`；
  3. `l.rstrip()` 应改为"仅在开启时应答式清理"，并且禁止作用于字符串字面量内部
     （至少要做到"保存后给出可见提示：已清理 N 行尾随空白"）。

---

### P1-2 外部修改被静默覆盖，且变更检测信号没有任何消费者

- **位置**：`core/content_provider.py:944-958`（`check_external_change`）、
  `core/document.py:984-1010`（`_on_file_changed` → `external_change_detected.emit`）、
  `core/content_provider.py:732-753`（保存前无任何校验）
- **证据（grep 全仓）**：`external_change_detected` 只有 2 处命中 ——
  `core/document.py:189`（docstring）与 `core/document.py:198`（信号定义）
  及 `:1007`（emit）。**没有任何 `connect()`。**
- **预期**：打开文件 → 外部程序改写 → 编辑器保存时，应提示冲突（重新加载/覆盖/另存）。
- **静态判定**：保存会直接按脏块偏移覆盖外部修改，**无 mtime 校验、无备份、无提示**；
  数据静默丢失。**未执行，未复现。**
- **附加缺陷**：
  - `check_external_change` 只比较 mtime（容差 0.001 s），内容变化但 mtime 相同
    （FAT/exFAT 2 秒精度、`touch -r`、某些 sync 工具）会漏检；
  - 模块 docstring（`core/content_provider.py:24`）声称"文件变更检测（mtime/hash）"，
    但 `self._hash`（`:156`）**从未被赋值**，hash 检测不存在；
  - `Document._on_file_changed` 里 `self.external_change_detected.emit(path)` 即使有消费者，
    也只在 QFileSystemWatcher 有效时触发（网络盘/某些容器不可靠）。
- **未执行，未复现。**
- **建议修法**：保存前比对 `(mtime, size, sha256)` 三元组，不一致则弹冲突对话框
  （提供的选项至少要有"另存为"和"以我的版本覆盖"）；把 `external_change_detected`
  接到 `MainWindow`；日志/自动保存等无人值守写入前也应做同样校验。

---

### P1-3 保存失败被吞掉，状态栏误报"已保存"

- **位置**：`ui/mixins/file_ops_mixin.py:181-199`（`_save_file`）、
  `ui/mixins/file_ops_mixin.py:202-238`（`_save_file_as`）
- **证据**：

  ```python
  # file_ops_mixin.py:194-196
  else:
      proxy.save_file()                               # ← 返回值被丢弃
      self.status_bar.showMessage("已保存", 2000)      # ← 无条件宣称成功

  # file_ops_mixin.py:228-235（原文照抄）
  if path:
      # 通过 document 保存到新路径
      proxy.document.save(path)                       # ← 返回值同样被丢弃

      # 更新标签标题
      idx = self.tabs.currentIndex()
      if idx >= 0:
          self.tabs.setTabText(idx, os.path.basename(path))   # 标题照样改
  ```
- **触发条件**：目标文件只读、父目录无写权限、磁盘满、Windows 共享冲突、
  文件被外部删除、`_save_as_full` 的 `os.replace` 遇到占用。
- **数据损失后果**：用户以为已保存，关标签页时被 `closeEvent` 判定为"未修改"
  （另存为路径）或被状态栏误导（Ctrl+S 路径），从而丢失编辑。
- **未执行，未复现。**
- **建议修法**：检查 `save_file()` / `save()` 的返回值，失败时走 `_show_error(...)`，
  并让 `Document.save()` 在失败时保持 `meta.modified = True`（`core/document.py:437`
  已经这样做了，但 `_save_file_as` 路径下 `meta.filepath` 已被改掉，需要回滚）。

---

### P1-4 保存时 `errors='replace'` 静默替换无法编码的字符

- **位置**：`core/content_provider.py:306-311`（`encode`）、
  `core/editor.py:534`（`_sync_content_to_provider` 调用 `encode`）、
  `core/document.py:708`（`_replace_full_content` 调用 `encode`）
- **证据**：

  ```python
  def encode(self, text: str) -> bytes:
      try:
          return text.encode(self._encoding, errors='replace')   # ← 变 '?' 无声
  ```
- **触发条件**：文件被检测为 GBK/Big5/Shift_JIS/ASCII 等窄编码，用户在编辑器里
  输入了该编码无法表示的字符（emoji、生僻字、或从别处粘贴的 Unicode）。
- **数据损失后果**：字符变成 `?`（`0x3F`），没有任何警告；因为保存成功，
  撤销栈也会被清空，原字符无法找回。
- **同类 P1-4b（解码侧）**：`decode` 用 `errors='replace'`，遇到无法解码的字节会
  变成 U+FFFD。对于"大部分是合法 GBK、夹杂少量非法字节"的文件
  （编码检测只看前 4096 字节，`core/content_provider.py:469`），
  打开时损坏显示、保存时把 `EF BF BD` 写回磁盘 → **原字节永久丢失**。
  检测顺序（`_detect_encoding`，`:499-541`）先试 UTF-8，若样本恰好是合法 UTF-8
  而文件其余部分是 GBK，也会走同一路径。
- **未执行，未复现。**
- **建议修法**：`encode`/`decode` 用 `errors='strict'`，把
  `UnicodeEncodeError`/`UnicodeDecodeError` 上抛到保存/打开流程，
  弹窗提示"文件包含无法用 <编码> 表示的字符，请选择 UTF-8 或取消"；
  编码检测应扫描全文或至少多段采样，并在检测置信度低时让用户确认。

---

### P1-5 崩溃上报器不保存任何用户数据，且报告路径相对于 CWD

- **位置**：`core/crash_reporter.py:28-118`、`core/crash_reporter.py:103`（默认 `output_dir="data/crashes"`）、
  `main.py:371-383`（`show_crash_dialog(None, ...)`，未传 `output_dir`）、
  `main.py:410`（`sys.excepthook = exception_hook`）
- **证据（静态）**：
  - `save_crash_report(ctx, output_dir="data/crashes")` 使用相对路径；
    若进程 CWD 不是项目根目录（例如从开始菜单/文件关联启动），
    报告会写到别处，甚至因目录不可写而只打印一行 `[CrashReporter] 保存失败`；
  - `collect_context` 只记录**文件路径列表**（`open_files`），不含任何正文；
  - 全仓库**没有 `faulthandler`**（grep 0 命中），
    因此段错误 / `os._exit` / C 层崩溃**完全不会**产生崩溃报告；
  - `sys.excepthook` 只覆盖主线程未捕获的 Python 异常。
- **数据损失后果**：崩溃时没有任何"未保存正文"落盘（见 P0-3），
  崩溃报告也只是诊断信息，不能用于恢复。
- **未执行，未复现。**
- **建议修法**：`faulthandler.enable(file=open(crash_fd,'w'))` 启动即开；
  在 `exception_hook` 里**先**把所有 modified 的编辑器缓冲区各写一份到
  `data/recovery/<timestamp>/`，再弹报告对话框；`output_dir` 用 `DATA_DIR` 绝对路径；
  报告写盘改为 mkstemp + `os.replace`（当前 `json.dump` 直接截断写，
  二次崩溃会留下半个 JSON）。

---

### P1-6 会话恢复与自动备份的编码/路径不正确，且恢复后立即删除备份

- **位置**：`app/session.py:782-874`（写备份）、`app/session.py:1055-1071`（读备份）、
  `app/session.py:1009-1014`（恢复后 rmtree）
- **证据**：

  ```python
  # 写：app/session.py:844-849
  with open(backup_path, 'w', encoding='utf-8') as f:
      f.write(content)                                  # content = proxy.sc.text()
      if original:
          f.write(f"\n\n###QINGCAO_ORIGINAL_PATH:{original}###")
  ```

  ```python
  # 读：app/session.py:1055-1057, 1067, 1070-1071
  with open(backup_path, encoding='utf-8', errors='replace') as f:
      content = f.read()
  ...
  content = content[:idx].rstrip()            # ← 尾随空白/空行被删掉
  ...
  provider = MemoryProvider()
  provider.open(initial_text=content)         # ← 默认 encoding='utf-8'
  ```

  ```python
  # 恢复后：app/session.py:1009-1014
  if restored > 0:
      shutil.rmtree(auto_save_dir, ignore_errors=True)
  ```
- **问题清单**：
  1. **尾部空白丢失**：`content[:idx].rstrip()` 会吃掉原文末尾的空行/缩进，
     与崩溃前内容不逐字节相等；
  2. **编码丢失**：备份固定写 UTF-8，恢复固定按 UTF-8 读，
     且 `MemoryProvider` 无 `filepath`，恢复出的文档**无法以原编码存回原路径**；
     原文里的 CRLF 也已在 `sc.text()` 阶段变成 LF；
  3. **标记串冲突**：若用户正文本身包含 `###QINGCAO_ORIGINAL_PATH:`，
     正文会被从该处截断（`content.find(...)` 未从末尾查找）；
  4. **恢复后立刻删除备份**：恢复内容只活在内存 provider 里；
     若用户在保存前再次崩溃，备份已不存在 → 数据永久消失；
     更严重的是 `QMessageBox.Discard`（`app/session.py:989-994`）分支会
     `rmtree` 整个备份目录 —— "丢弃"按钮同时销毁了用户唯一的副本；
  5. `check_and_recover_crash` 依赖交互式 `QMessageBox`，无自动化路径。
- **未执行，未复现。**
- **建议修法**：备份里记录 `encoding` / `eol` / `has_bom` / `原始路径` / `内容哈希`，
  用长度前缀或末行 JSON 存元数据而不是正文内嵌标记；
  恢复后**保留**备份直到用户成功保存（或做"已恢复"标记 + N 天保留）；
  `Discard` 应先移动到 `backup/trash/` 而不是 `rmtree`；
  恢复出的文档应保留原路径建议值，允许"另存为原文件"。

---

### P2 级发现（不直接丢字节，但影响持久化可靠性）

| # | 位置 | 问题 | 后果 | 建议 |
|---|---|---|---|---|
| P2-1 | `app/preferences.py:339-378` | `set()` / `_flush()` 调用 `QSettings.sync()` 后**从不检查 `settings.status()`** | 配置写盘失败（只读 INI、磁盘满、路径不可写）被静默忽略，重启后设置回退，用户配对/主题等设置"莫名其妙丢了" | `sync()` 后检查 `status()`，`QSettings.AccessError/FormatError` 时提示并落日志 |
| P2-2 | `app/preferences.py:297-337` | `get()` 只对 `list/dict` 默认值做 JSON 容错；`panel_layout`/`recent_files`/`plugins_enabled`/`keybindings_custom` 等**存 JSON 字符串**的键原样返回 | 损坏的 JSON 字符串被上层 `json.loads` 抛出；或写入时用 `json.dumps`、读取时拿到旧格式 → 静默用默认值覆盖用户数据 | 为这些键加 `json` 类型标记或统一的 `get_json()`；损坏时备份原值再回退 |
| P2-3 | `app/config_manager.py:84-92` | `import_config` 循环 `setValue` 后不检查状态；`keybindings.json` 用 `open('w')` **非原子**覆写 | 导入过程中失败 → 快捷键配置半截 JSON；下次启动解析失败被静默忽略（`app/config_manager.py:45-46`） | 写临时文件 + `os.replace`；导入前备份现有 keybindings.json |
| P2-4 | `main.py:115-149` 与 `app/preferences.py:273-283` | 有**两套**便携模式实现：`main.py:setup_portable_mode()`（按 `portable.txt`/`portable`/`.portable` 检测）与 `Preferences(portable=...)`（**默认 `False`，`get_preferences()` 也不传**） | 便携模式只通过 `QSettings.setDefaultFormat` 生效（全局副作用）；若某处 QSettings 在 `setup_portable_mode()` 之前构造，或 `Preferences` 用默认构造，就会读写到注册表而不是 `data/` | 统一为一个 `is_portable()` 来源；`get_preferences()` 里传入检测结果；`Preferences.__init__` 打印实际 `settings.fileName()` 便于排查 |
| P2-5 | `ui/main_window.py:2293-2309` | 退出确认对话框只有 **Discard / Cancel**，没有 "Save" | 用户唯一的非取消选择是"放弃所有修改"；配合 P0-3（无崩溃备份）等于强制丢弃 | 增加 "保存全部并退出"/"逐个确认" 选项 |
| P2-6 | `app/tabs.py:440-455` | 二进制检测用"前 1024 字节含 `\x00`" | **UTF-16 文本文件一律被判为二进制**并弹警告；`.txt` 的 UTF-16 文件在本编辑器中体验受损 | 先做 BOM / 编码探测，UTF-16/32 排除在二进制判定之外 |
| P2-7 | `app/tabs.py:470-473` + `core/document.py:257-264` | `tabs.open_file` 先建一个 `LocalFileProvider` 并 `provider.open(filepath)`，随后 `Document.open()` **又建一个**并替换 `document.provider`；`EditorWidget.prov` 仍指向第一个 | 第一个 provider 的**文件句柄 + ACCESS_WRITE mmap 永不释放**（`EditorWidget.prov` 全仓无 `.close()`），每开一个文件泄漏一对句柄；Windows 下还可能让 `os.replace` 到该路径失败 | `TabManager.open_file` 不要预建 provider（交给 `Document.open`），或让 `EditorWidget` 复用 `document.provider` 并在 `closeEvent` 里释放 |
| P2-8 | `core/content_provider.py:666-668` | `save()` 在 `not self._dirty_blocks and filepath is None` 时直接 `return True`，但 `Document.save()` 永远传 target（非 None），所以该分支形同虚设；反之，**只脏一部分块时 `_save_dirty_blocks` 会把文件截断到最后一个脏块的末尾** | 任何"只写块 N"的调用方都会截断文件（脚本 B4 专门测这条）。当前仓库内所有调用方都写满全部块，因此是**潜伏缺陷**而非现网缺陷 | `_save_dirty_blocks` 应显式比较"新总长度 vs 磁盘长度"，并在长度变化时走原子整写；给 `save()` 加断言"脏块集合必须连续覆盖 [0, last]" |
| P2-9 | `core/content_provider.py:489-494` | BOM 检测**优先于**用户指定的 `forced_encoding`（`if not self._has_bom and forced_encoding`） | 用户无法用"以 XXX 编码重新打开"覆盖一个带 BOM 的文件；UTF-16 文件被强制为 `utf-16-le` 后，文本开头多出一个不可见的 U+FEFF，用户删掉它就会丢掉 BOM | BOM 只作为默认建议，显式指定编码时应尊重用户选择 |
| P2-10 | `core/content_provider.py:465-497` | `_detect_eol` 直接在原始字节上统计 `\r\n`/`\n`/`\r` | 对 UTF-16 文件完全失效（`0D 00 0A 00` 里 `\r\n` 计数为 0）；且 `_eol` 在保存路径上**从未被使用**（`encode` 不做行尾转换） | 按编码解码后再检测行尾；保存时按 `meta.eol` 还原行尾（与 P1-1 的修法合并） |
| P2-11 | `core/document.py:1015-1052` | 草稿写到 `backup/drafts/`（`os.path.dirname(os.path.dirname(__file__))`），而 `main.py:103` 预建的是 `data/drafts/` | 两个目录长期并存，无人清理；草稿只增不减（保存成功才删，且 `delete_draft` 用 `meta.filepath` 算哈希，另存为后哈希变了 → 旧草稿成孤儿） | 统一目录常量；启动时清理超过 N 天的孤儿草稿 |

---

## 3. 往返一致性矩阵

> **重要**：本节的"实测"列**全部为 `未执行`**。审计会话无法运行任何进程（见第 0 节）。
> "静态预判"列是逐行读代码推导的**预测结果**，不是观测结果。
> 待跑的脚本：`tests/audit_data_integrity_harness.py --only A`。

### 3.1 经真实编辑器路径（`EditorWidget` → `EditorProxy.save_file` → `provider.save`），偏好为出厂默认（`trim_trailing_whitespace=True`, `insert_final_newline=True`）

| 编码 / 行尾 | 改开头 | 改结尾 | 中间插入 | 删除大段 | 只追加 | 清空 |
|---|---|---|---|---|---|---|
| UTF-8 / LF | 静态预判 **FAIL**（尾随空白被 `rstrip`、补末尾换行）· 实测 `未执行` | 静态预判 **FAIL**（同左）· 实测 `未执行` | 静态预判 **FAIL**（同左）· 实测 `未执行` | 静态预判 **FAIL**（同左）· 实测 `未执行` | 静态预判 **FAIL**（同左）· 实测 `未执行` | 静态预判 **PASS**（唯一边界情形）· 实测 `未执行` |
| UTF-8 / CRLF | 静态预判 **FAIL**（全部行尾变 LF）· 实测 `未执行` | 同上 · 实测 `未执行` | 同上 · 实测 `未执行` | 同上 · 实测 `未执行` | 同上 · 实测 `未执行` | 静态预判 **PASS** · 实测 `未执行` |
| UTF-8-BOM / LF | **FAIL**（尾随空白/末尾换行）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL**（`''.encode('utf-8-sig') == b''`，BOM 被删）· 实测 `未执行` |
| UTF-8-BOM / CRLF | **FAIL**（CRLF→LF + 空白）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL**（BOM 被删）· 实测 `未执行` |
| GBK / LF | **FAIL**（空白/末尾换行）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| GBK / CRLF | **FAIL**（CRLF→LF）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| UTF-16LE+BOM / LF | **FAIL**（空白/末尾换行）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL**（`''.encode('utf-16-le')==b''`，BOM 丢失）· 实测 `未执行` |
| 混合行尾（CRLF+LF）· UTF-8 | **FAIL**（行尾被统一为 LF）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| 无末尾换行 · UTF-8 | **FAIL**（补 `\n`）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| 空文件 | **PASS**（静态推导：`total_blocks=max(1,0)=1`，`write_block(0,b'')`，`truncate(0)`，结果 0 字节）· 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| 仅 BOM（`EF BB BF`） | **FAIL**（BOM-only 文件保存后变 0 字节）· 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` | **FAIL** · 实测 `未执行` |

### 3.2 仅经 provider 路径（不经编辑器的 trim/行尾规范化）

| 编码 / 行尾 | 改开头 | 改结尾 | 中间插入 | 删除大段 | 只追加 | 清空 |
|---|---|---|---|---|---|---|
| UTF-8 / LF | 静态预判 **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| UTF-8 / CRLF | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| UTF-8-BOM / LF | 静态预判 **PASS**（`utf-8-sig` 编码器自动补 BOM，`b'\xef\xbb\xbf'` + 内容）· 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | **FAIL**（内容非空→有 BOM；内容为空→`b''`，BOM 丢失）· 实测 `未执行` |
| GBK / LF、GBK / CRLF | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` | **PASS** · 实测 `未执行` |
| UTF-16LE+BOM / LF | 静态预判 **PASS**（`utf-16-le` 把 U+FEFF 还原成 `FF FE`）· 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | **FAIL**（BOM 丢失）· 实测 `未执行` |
| 含非法编码字节的文件 | **FAIL**（`errors='replace'` → U+FFFD 写回）· 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` | 同 · 实测 `未执行` |

### 3.3 为什么"3.2 大面积 PASS"仍未通过审计

3.2 只是 `LocalFileProvider` 的 API 行为；**产品里没有任何用户操作会走这条纯路径**
（`app/tabs.py` 的打开/保存一律经过 `EditorWidget` + `EditorProxy`）。
把 3.2 的 PASS 当作"编辑器往返正常"是本项目最容易犯的误判。
`tests/test_save_truncate.py` 覆盖的正是 3.2 这一层，所以它通过并不代表用户不会丢数据。

---

## 4. 未覆盖 / 不确定

### 4.1 因环境限制完全未覆盖的项

| 项目 | 状态 | 试了什么 |
|---|---|---|
| **全部运行时实证（A/B/C/D/E 五组）** | **未执行** | 5 种 `pwsh` 调用方式（默认、显式提权、改 workdir、后台作业、只读探测）全部在进程启动前失败；提权被自动拒绝。见第 0 节表格 |
| 往返矩阵的真实字节比对 | 未执行 | 已写好 `tests/audit_data_integrity_harness.py --only A`，含"关掉 trim/final-newline 的隔离验证"作为对照 |
| 块边界实际损坏样本 | 未执行 | 脚本 B1/B2 会构造"3 字节汉字的第 1 字节落在 `block_size-1`"并对比逐块解码 vs 整块解码 |
| 只脏块 0 导致的截断 | 未执行 | 脚本 B4（预测：3×4096 字节文件写后再保存变成 10 字节） |
| 外部修改后保存的真实结果 | 未执行 | 脚本 C（预测：外部内容被静默覆盖；`external_change_detected` 无消费者） |
| 失败注入（只读 / `msvcrt.locking` 独占 / 目录不存在） | 未执行 | 脚本 D（预测：原文件完好，但 `_save_file` 会误报"已保存"） |
| 崩溃恢复端到端（`os._exit(1)` + 重启） | 未执行 | 脚本 E 用子进程 `os._exit(1)` 后检查 `backup/autosave/meta.json`（预测：**不存在**，因为 `start_autosave()` 从未被调用） |
| `QSettings` 写盘失败（只读 INI / 磁盘满） | 未执行 | 需要 shell 造只读文件；已定位为 P2-1（无 `status()` 检查） |
| 断电 / 写盘中断（原子性） | **无法运行时验证**，只能静态判定 | 真断电无法在受控环境复现；建议用 `Process Monitor`/`fsync` 故障注入或 `diskpart` 离线模拟 |
| `chardet` 实际检测结果分布 | 未执行 | 需运行；依赖是否安装会影响检测分支（`core/content_provider.py:509-523`） |
| 大文件（>10 MiB）异步加载期保存的截断 | 未执行 | 脚本未覆盖（需生成 >10 MiB 样本 + 事件循环时序）；**代码路径已确认存在，见 P0-1 附近的加载分支** |

### 4.2 我明确"未能复现"的断言（不要当作已确认缺陷）

以下三条是我在静态阅读中高度怀疑、但**既没有运行验证、也没有现网报告佐证**的：

1. **结论 B（另存为写旧内容）** —— 调用链我逐行核对过
   （`file_ops_mixin.py:230` → `document.py:394` → `content_provider.py:678` → `:821`），
   逻辑上成立；但我无法运行 `QFileDialog`，也没找到覆盖该路径的现有测试
   （`tests/test_document.py:631` 的 `doc.save(target)` 是直接对 provider 操作，
   走的不是 UI 路径）。**标记为：静态判定成立，未复现。**
2. **结论 C（自动备份未接线）** —— 这是 grep 结论，确定性较高
   （`start_autosave` 零调用点）；但"零调用"也可能是我搜索范围的盲区
   （例如运行时 `getattr` 动态调用）。我额外 grep 了 `autosave`、`_autosave_tick`、
   `save_autosave`，均未发现动态调度。**标记为：静态判定成立，未复现。**
3. **P2-7（provider 句柄泄漏）** —— `EditorWidget.prov` 我在全仓只找到
   赋值处与 `tools/health_check.py` 的注释；若 `EditorWidget` 有自定义
   `closeEvent`/`__del__` 释放 `self.prov`，结论会不成立。我 grep 了
   `self.prov`，未见 `self.prov.close()`。**标记为：静态判定成立，未复现。**

### 4.3 未审计到的相邻区域（超出本次范围，建议后续跟进）

- `core/search.py` 的 `ReplaceEngine._replace_range`（`core/search.py:1041-1074`）与
  `ui/main_window.py:1890-1917` 的跨文件替换：它直接 `provider.save(filepath)`，
  而该文件可能同时被某个标签页打开（两个 provider、两个 mmap），
  存在"全局替换结果被标签页后续保存覆盖"的竞态，未展开审计。
- `core/snapshot.py`、`core/file_merge.py`、`app/sync.py`（云同步/合并）的持久化路径。
- `plugins/*` 的写盘行为。
- `core/secure_storage.py`（凭据存储）。
- `dist/`（打包产物里的同名文件可能与源码不一致；本次只审计了源码树）。

---

## 5. 建议的修复优先级与回归测试

1. **立刻**（P0-1）：`EditorProxy._load_content` 去掉逐块 decode。
   回归：新增"64 KiB 边界处放一个中文/emoji，打开→保存→字节比对"测试。
2. **立刻**（P0-2）：`_save_file_as` 改调 `proxy.save_file(path)`。
   回归：UI 级测试"打开→改→另存为→断言新文件含改动、旧文件不变、`is_modified` 语义正确"。
3. **立刻**（P0-4）：`save()` 无条件原子写。
   回归：monkeypatch 让第 3 次 `write()` 抛 `OSError`，断言原文件字节不变。
4. **立刻**（P0-3）：接线 `start_autosave()`；把 `save_autosave` 挂到 `_autosave_session`。
   回归：子进程 `os._exit(1)` → 重启 → 断言恢复内容与崩溃前**逐字节相等**（含 CRLF 和末尾空行）。
5. **本迭代**（P1-1 / P1-3 / P1-4）：默认关闭保存期规范化；保存失败必须报错；
   `encode/decode` 改 `errors='strict'` 并把异常翻译成用户可见的对话框。
6. **本迭代**（P1-2）：保存前 mtime+size+hash 校验 + 冲突对话框。
7. 把 `tests/audit_data_integrity_harness.py` 接入 CI（它是可执行规格，
   跑通后应转为正式测试，并删除 `--only` 依赖）。

---

## 附录 A：本报告结论的静态证据索引

| 结论 | 关键位置 |
|---|---|
| P0-1 逐块解码 | `core/editor.py:426-440`、`core/content_provider.py:299-304`、`:561-606`、`:47` |
| P0-2 另存为写旧内容 | `ui/mixins/file_ops_mixin.py:230`、`core/document.py:359-446`、`core/content_provider.py:678-679`、`:815-896` |
| P0-3 崩溃备份未接线 | `app/session.py:147-171`、`:782-874`、`ui/main_window.py:241-243`、`:1998-2015`、`main.py:1004-1019`、`core/document.py:1015-1052` |
| P0-4 非原子保存 | `core/content_provider.py:648-686`、`:688-782`（尤其 `:732-753`）、`:652`（docstring 与实现矛盾） |
| P1-1 保存期规范化 | `core/editor.py:473-491`、`app/preferences.py:137-139` |
| P1-2 外部修改静默覆盖 | `core/content_provider.py:944-958`、`core/document.py:984-1010`、`:198`（信号无消费者） |
| P1-3 保存失败误报 | `ui/mixins/file_ops_mixin.py:181-199`、`:202-238` |
| P1-4 `errors='replace'` | `core/content_provider.py:299-311`、`core/editor.py:534`、`core/document.py:708` |
| P1-5 崩溃上报器 | `core/crash_reporter.py:28-118`、`:103`、`main.py:371-383`、`:410`（无 `faulthandler`） |
| P1-6 会话/自动备份编码与删除 | `app/session.py:844-849`、`:1055-1071`、`:1009-1014`、`:989-994` |
| P2 各项 | 见第 2 节 P2 表格 |

## 附录 B：本次为实证准备的脚本

`tests/audit_data_integrity_harness.py`（**尚未执行**）

- `--only A`：往返一致性矩阵（provider 路径 + 真实编辑器路径 + 关闭规范化后的隔离验证）
- `--only B`：块边界（`blocksize±1`、逐块解码 vs 整块解码、只脏块 0 的截断）
- `--only C`：外部修改 / 外部删除后保存
- `--only D`：只读文件 / `msvcrt` 独占锁 / 不存在的目录 + UI 误报核对
- `--only E`：子进程 `os._exit(1)` 模拟崩溃 + 备份目录检查

运行前置：

```powershell
chcp 65001
$env:QT_QPA_PLATFORM = "offscreen"
python tests\audit_data_integrity_harness.py --verbose
```

脚本已知的自身风险（因为没跑过，必须声明）：
`roundtrip_provider` 里对 `prov._size/_total_blocks` 的私有字段赋值、
`roundtrip_editor` 里对期望字节的构造、以及 `section_E` 中未调用
`check_and_recover_crash`（因其需要交互式 `QMessageBox`），
都可能需要在首次运行时修正；请把首次运行的原始输出**原样**贴回来，
我会据此把"静态预判"改成"实测结论"。

---

*报告结束。本报告不含任何虚构的运行输出；所有无法执行的条目均已显式标注为 `未执行` / `未复现`。*
