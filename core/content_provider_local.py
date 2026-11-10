# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""本地文件提供者（v2.24 拆出）。"""
from core.content_provider_base import ContentProvider
from core.content_provider_common import *  # noqa: F401,F403,F405


class LocalFileProvider(ContentProvider):
    """
    本地文件提供者。

    使用 mmap 实现高效的大文件访问，支持：
    - 分块读取
    - 脏块缓冲
    - 原子保存
    - 自动编码检测
    - BOM 处理
    - 行尾符检测
    - 只读保护
    """

    def __init__(self, block_size: int = DEFAULT_BLOCK_SIZE):
        super().__init__()
        self._block_size = max(MIN_BLOCK_SIZE,
                               min(block_size, MAX_BLOCK_SIZE))

        # 文件句柄
        self._file: Optional[io.BufferedRandom] = None
        self._mmap: Optional[mmap.mmap] = None

        # 缓存已加载的块
        self._loaded_blocks: set = set()

    # --------------------------------------------------------
    # 打开文件
    # --------------------------------------------------------
    def open(self, source: str, encoding: Optional[str] = None,
             readonly: bool = False, detect_encoding: bool = True,
             block_size: Optional[int] = None) -> bool:
        """
        打开本地文件。

        参数:
            source: 文件路径
            encoding: 指定编码（None 则自动检测）
            readonly: 是否以只读模式打开
            detect_encoding: 是否自动检测编码
            block_size: 覆盖默认块大小

        返回:
            是否成功

        异常:
            FileNotFoundError: 文件不存在
            PermissionDeniedError: 权限不足
        """
        # 关闭之前的文件
        if self.is_open:
            self.close()

        if not os.path.exists(source):
            raise FileNotFoundError(f"文件不存在: {source}")

        if not os.path.isfile(source):
            raise FileNotFoundError(f"路径不是文件: {source}")

        self._filepath = os.path.abspath(source)

        if block_size:
            self._block_size = max(MIN_BLOCK_SIZE,
                                   min(block_size, MAX_BLOCK_SIZE))

        # 检查权限
        try:
            st = os.stat(self._filepath)
            self._readonly = readonly or not os.access(self._filepath, os.W_OK)
            # 记住"磁盘上是否可写"，用于需要写入时把映射升级为读写
            self._can_write = os.access(self._filepath, os.W_OK)
            self._size = st.st_size
            self._mtime = st.st_mtime
        except PermissionError as e:
            raise PermissionDeniedError(f"无法访问文件: {e}")

        # 打开文件句柄
        #
        # 关键（Windows 文件锁定缺陷）：
        #   原先在文件可写时用 `'r+b'` + `mmap.ACCESS_WRITE`，并且**一直
        #   持有**该映射。Windows 上写模式的内存映射会**独占锁定文件** ——
        #   于是编辑器一打开文件，其它程序（git、构建工具、另一个编辑器）
        #   就再也无法修改它，直到本编辑器关闭该文件。
        #
        #   这直接让"外部文件变更检测/三方合并"失去意义：那种情况**永远
        #   不会发生**。实测：打开文件后 `Path.write_text()` 抛
        #   `OSError: [Errno 22] Invalid argument`。
        #
        #   现在**默认只读打开**（共享读，不阻断外部写入）；只有真正需要
        #   就地写入脏块时才由 `_ensure_writable()` 升级为读写映射，
        #   且写入完成后即可释放（见 `release_write_handle()`）。
        try:
            self._file = open(self._filepath, 'rb')
        except PermissionError as e:
            raise PermissionDeniedError(f"无法打开文件: {e}")

        # 创建 mmap（默认只读 —— 不锁文件）
        #
        # 只对**大文件**建映射（与 `read_block` / `_ensure_handle` 一致）。
        # 小文件直接 read() 的开销可忽略，而且**不建立映射就不会锁住文件**
        # —— Windows 上即使只读映射也会阻止外部程序覆盖写，那会让
        # "外部变更检测 / 三方合并"永远不会触发。
        if self._size > MMAP_MIN_SIZE:
            try:
                self._mmap = mmap.mmap(
                    self._file.fileno(), 0, access=mmap.ACCESS_READ
                )
            except (ValueError, OSError) as e:
                # 空文件或无法映射
                self._mmap = None

        # 计算总块数
        self._total_blocks = max(
            1,
            (self._size + self._block_size - 1) // self._block_size
        )

        # 检测编码和行尾符
        self._detect_encoding_and_eol(encoding, detect_encoding)

        # 初始化状态
        self._dirty_blocks.clear()
        self._loaded_blocks.clear()
        self._state = FileState.READONLY if self._readonly else FileState.OPENED

        return True

    # --------------------------------------------------------
    # 编码与行尾符检测
    # --------------------------------------------------------
    def _detect_encoding_and_eol(self, forced_encoding: Optional[str],
                                 detect: bool):
        """检测编码和行尾符"""
        # 读取文件头部样本
        sample_size = min(4096, self._size)
        sample = b''

        if sample_size > 0:
            if self._mmap:
                sample = self._mmap[:sample_size]
            elif self._file:
                self._file.seek(0)
                sample = self._file.read(sample_size)
                self._file.seek(0)

        # 1. BOM 检测
        self._has_bom = False
        for bom, enc in BOMS.items():
            if sample.startswith(bom):
                self._encoding = enc
                self._has_bom = True
                break

        # 2. 指定编码
        if not self._has_bom and forced_encoding:
            self._encoding = forced_encoding

        # 3. 自动检测
        elif not self._has_bom and detect:
            self._encoding = self._detect_encoding(sample)
            # 3b. ASCII 必须验证**整个文件**（P0-A 相关修复）
            #
            # 缺陷背景（实测）：采样只有 4096 字节，若前 4KB 全是 ASCII
            # 而后面才是中文，chardet 会高置信度地判成 ascii。随后
            #   decode(errors='replace') → 汉字变 U+FFFD
            #   encode(errors='replace') → U+FFFD 变 '?'（ascii 下不可编码）
            # 于是**一保存整个文件的中文全部被销毁**。
            #
            # 因此：只有当 ASCII 声明在整个文件上都成立时才接受它。
            if self._encoding == ENCODING_ASCII and self._size > len(sample):
                if self._has_non_ascii_beyond(sample):
                    # 在后续内容上重新检测（含非 ASCII 字节，chardet 能识别）
                    tail = self._read_verify_bytes()
                    self._encoding = self._detect_encoding(tail)

        # 4. 行尾符检测
        self._eol = self._detect_eol(sample)

    def _detect_encoding(self, sample: bytes) -> str:
        """
        自动检测编码。

        优先使用 chardet，其次使用简单启发式规则。
        """
        if not sample:
            return ENCODING_UTF8

        # 尝试使用 chardet
        try:
            import chardet
            result = chardet.detect(sample)
            if result and result.get('confidence', 0) > 0.7:
                enc = result['encoding']
                if enc:
                    # 规范化编码名
                    enc = enc.lower().replace('_', '-')
                    if enc == 'ascii':
                        return ENCODING_ASCII
                    return enc
        except ImportError:
            pass
        except Exception:
            pass

        # 简单启发式规则
        # 1. 尝试 UTF-8
        try:
            sample.decode('utf-8')
            return ENCODING_UTF8
        except UnicodeDecodeError:
            pass

        # 2. 尝试 GBK
        try:
            sample.decode('gbk')
            return ENCODING_GBK
        except UnicodeDecodeError:
            pass

        # 3. 尝试 Latin-1（永远成功）
        return ENCODING_LATIN1

    # 验证 ASCII 声明时要扫描的最大字节数（避免大文件全量扫描拖慢打开）
    _ASCII_VERIFY_LIMIT = 32 * 1024 * 1024

    def _read_verify_bytes(self) -> bytes:
        """读取用于编码复检的字节（跳过已采样的头部）

        优先返回**含非 ASCII 字节**的那一小段，这样 chardet 才能据此
        判出真实编码；全部都是 ASCII 时返回空 bytes。
        """
        try:
            if self._size <= self._ASCII_VERIFY_LIMIT:
                if self._mmap:
                    return bytes(self._mmap[:])
                if self._file:
                    pos = self._file.tell()
                    self._file.seek(0)
                    data = self._file.read()
                    self._file.seek(pos)
                    return data
        except Exception:
            pass

        # 大文件：分块扫描，返回第一个含非 ASCII 字节的块
        chunk = 256 * 1024
        try:
            src = self._mmap
            if src is not None:
                for off in range(0, self._size, chunk):
                    part = bytes(src[off:off + chunk])
                    if not part.isascii():        # C 实现，见下方说明
                        return part
                return b''
            if self._file:
                pos = self._file.tell()
                self._file.seek(0)
                for _ in range(0, self._size, chunk):
                    part = self._file.read(chunk)
                    if not part:
                        break
                    if not part.isascii():        # C 实现，见下方说明
                        return part
                self._file.seek(pos)
        except Exception:
            pass
        return b''

    def _has_non_ascii_beyond(self, sample: bytes) -> bool:
        """检查采样之后的文件内容里是否存在非 ASCII 字节

        ★ 性能缺陷（大文件打开 4~12s 的**真正根因**，cProfile 实测）：

            原实现用 `any(b > 127 for b in part)` 判断。这是**纯 Python
            逐字节生成器**：每字节一次生成器迭代 + 比较。对 10MB 文件，
            `_ASCII_VERIFY_LIMIT` 是 32MB，因此会扫描整个文件
            —— 实测 **2080 万次生成器调用、约 11 秒**，
            而 QScintilla 真正的 `setText` 只要 **0.22 秒**。

        修复：`bytes.isascii()` 是 CPython 的 **C 实现**（3.7+），
        语义完全等价（所有字节 < 128），速度快 2~3 个数量级。
        """
        try:
            if self._mmap:
                start = len(sample)
                end = min(self._size, start + self._ASCII_VERIFY_LIMIT)
                part = bytes(self._mmap[start:end])
                return not part.isascii()
            if self._file:
                pos = self._file.tell()
                self._file.seek(len(sample))
                remaining = min(self._size - len(sample),
                                self._ASCII_VERIFY_LIMIT)
                found = False
                while remaining > 0:
                    part = self._file.read(min(256 * 1024, remaining))
                    if not part:
                        break
                    remaining -= len(part)
                    if not part.isascii():        # C 实现，见下方说明
                        found = True
                        break
                self._file.seek(pos)
                return found
        except Exception:
            pass
        # 检测失败时保守认为"可能存在非 ASCII"，避免误判为 ascii
        return True

    def _detect_eol(self, sample: bytes) -> str:
        """检测行尾符"""
        if not sample:
            return EOL_LF

        crlf_count = sample.count(b'\r\n')
        lf_count = sample.count(b'\n') - crlf_count
        cr_count = sample.count(b'\r') - crlf_count

        if crlf_count >= lf_count and crlf_count >= cr_count:
            return EOL_CRLF
        elif cr_count > lf_count:
            return EOL_CR
        return EOL_LF

    # --------------------------------------------------------
    # 块读取
    # --------------------------------------------------------
    def read_block(self, block_id: int) -> bytes:
        """
        读取指定块。

        参数:
            block_id: 块索引（从 0 开始）

        返回:
            块的字节内容（**完整字符对齐**，不会以半个多字节字符结尾）

        注意（P0-A 修复）：
            原先固定按 `block_id * block_size` 切分，横跨边界的 UTF-8
            字符会被解码成 U+FFFD 并在保存时永久损坏原文件。
            现在使用 `_aligned_block_bounds()` 返回的字符对齐边界。
        """
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")

        if block_id < 0 or block_id >= self._total_blocks:
            return b''

        # 优先返回脏块
        if block_id in self._dirty_blocks:
            return bytes(self._dirty_blocks[block_id])

        # 字符对齐边界（多字节编码下避免跨块损坏；单字节编码下等同于原偏移）
        if self._needs_boundary_alignment():
            bounds = self._aligned_block_bounds()
            if block_id < len(bounds):
                start, end = bounds[block_id]
            else:
                start = block_id * self._block_size
                end = min(start + self._block_size, self._size)
        else:
            start = block_id * self._block_size
            end = min(start + self._block_size, self._size)

        if start >= self._size:
            return b''

        # 按需重建句柄/映射（release_mmap 之后仍能快速读取）
        #
        # 只对**大文件**建立映射：小文件直接读更快，而且不留驻映射就
        # 不会锁住文件（Windows 上映射会阻止外部程序覆盖写）。
        # 这是"外部变更检测/三方合并"能真正触发的前提。
        if self._size <= MMAP_MIN_SIZE:
            if self._file is None or self._file.closed:
                self._ensure_handle()
            if self._file:
                try:
                    self._file.seek(start)
                    data = self._file.read(end - start)
                    self._loaded_blocks.add(block_id)
                    return data
                except (ValueError, OSError):
                    pass
        else:
            if self._file is None or self._mmap is None:
                self._ensure_handle()

        # mmap 读取
        if self._mmap:
            try:
                data = self._mmap[start:end]
                self._loaded_blocks.add(block_id)
                return data
            except (ValueError, OSError):
                pass

        # 回退到文件读取
        if self._file:
            try:
                self._file.seek(start)
                data = self._file.read(end - start)
                self._loaded_blocks.add(block_id)
                return data
            except Exception as e:
                print(f"[LocalFileProvider] 读取失败: {e}")

        return b''

    # --------------------------------------------------------
    # 块写入
    # --------------------------------------------------------
    def write_block(self, block_id: int, data: bytes) -> bool:
        """
        写入指定块（写入脏块缓冲区，不立即落盘）。

        参数:
            block_id: 块索引
            data: 新的字节内容

        返回:
            是否成功
        """
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")

        if self._readonly:
            return False

        if block_id < 0 or block_id >= self._total_blocks:
            return False

        self._dirty_blocks[block_id] = bytearray(data)
        self._state = FileState.MODIFIED

        # 内存限制：脏块过多时提示
        if len(self._dirty_blocks) > MAX_LOADED_BLOCKS:
            print(f"[LocalFileProvider] 警告: 脏块数量过多 "
                  f"({len(self._dirty_blocks)})")

        return True

    def write_text(self, text: str, block_id: int = 0):
        """写入文本到指定块（便捷方法）"""
        self.write_block(block_id, self.encode(text))

    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------
    def save(self, filepath: Optional[str] = None) -> bool:
        """
        持久化内容到磁盘。**始终使用原子写入**（临时文件 + fsync + 替换），
        因此中途失败（磁盘满、断电、进程被杀）都不会损坏原文件。

        参数:
            filepath: 另存为路径（None 则覆盖原文件）

        返回:
            是否成功

        修复记录（P1-D，原实现与 docstring 不符）：
            原 docstring 声称"使用原子写入（临时文件 + 重命名）避免中途失败
            损坏文件"，但实际只有"另存为不同路径"才走 `_save_as_full()`；
            常规覆盖保存走的是 `_save_dirty_blocks()` —— 那是**原地写**：
                open(target, 'r+b') -> seek/write -> truncate(new_size)
            没有任何临时文件或备份副本。

            更严重的是上层 `EditorProxy._sync_content_to_provider()` 在保存前
            会把**全部块**标脏，所以每次 Ctrl+S 实际上都是"整文件原地重写"。
            一旦在写盘过程中失败，原文件已被截断/覆盖，用户数据无法回退。

            现在无条件走 `_save_as_full()`。代价是每次都重写整个文件
            （本来也是这样），换来的是"要么全成、要么原文件不动"。
        """
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")

        if self._readonly:
            raise PermissionDeniedError("文件为只读")

        if not self._dirty_blocks and filepath is None:
            # 无修改，无需保存
            return True

        target = filepath or self._filepath
        if not target:
            return False

        target = os.path.abspath(target)

        try:
            # 统一走原子全量写入（含 mkstemp + fsync + os.replace）
            return self._save_as_full(target)

        except Exception as e:
            print(f"[LocalFileProvider] 保存失败: {e}")
            return False

    def _save_dirty_blocks(self, target: str) -> bool:
        """仅写入脏块（原地更新）。

        A4 修复：先释放 mmap 再开文件。

        原实现在写完脏块后才 mmap.flush()，但在写入过程中
        mmap 仍持有文件映射。Windows 上 open('r+b') 会因
        文件被 mmap 锁定而抛 PermissionError。Linux/macOS
        允许，但 flush 语义也不可靠。

        A5 修复（数据损坏）：
            原实现只按块 seek+write，**从不截断文件**。当新
            内容比原文件短时，新内容之后会残留旧字节，重新
            打开文件会看到"已删除的内容又回来了"。
            例如把 55890 字节的文件删到 12 字节后保存，
            文件仍是 55890 字节（新内容 + 旧尾部）。

            修复方法：按脏块内容计算出真实长度 new_size，
            写完后若 new_size < 原大小则 f.truncate(new_size)，
            并用 new_size 覆盖 self._size，保证内存状态与磁盘
            一致后重建 mmap。

        修复流程：
            1. 先 mmap.flush() + mmap.close()，释放文件锁
            2. open('r+b') 写脏块 + 按新长度截断
            3. 重新建立 mmap（保持 provider 可读）
        """
        # ---- 1. 释放 mmap ----
        if self._mmap:
            try:
                self._mmap.flush()
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None

        # 落盘后的真实长度（脏块覆盖范围的最大末尾）
        new_size = 0
        for block_id, data in self._dirty_blocks.items():
            new_size = max(
                new_size, block_id * self._block_size + len(data)
            )

        # ---- 2. 写脏块 + 截断 ----
        try:
            # 使用可写文件句柄
            with open(target, 'r+b') as f:
                for block_id, data in self._dirty_blocks.items():
                    offset = block_id * self._block_size
                    f.seek(offset)
                    f.write(bytes(data))

                # A5: 内容变短时必须截断，否则旧字节残留在尾部。
                # 注意：必须用磁盘上的真实大小比较，不能用
                # self._size —— 编辑器在保存前会先调用
                # _replace_full_content()，那里已经把 self._size
                # 改成了新长度，用它比较会漏掉截断。
                try:
                    on_disk = os.fstat(f.fileno()).st_size
                except Exception:
                    on_disk = self._size
                if new_size < on_disk:
                    f.truncate(new_size)

                f.flush()
                os.fsync(f.fileno())

            # 更新状态
            self._dirty_blocks.clear()
            self._state = (FileState.READONLY if self._readonly
                           else FileState.OPENED)

            # 更新 mtime / size（size 以磁盘实际大小为准）
            self._size = new_size
            self._total_blocks = max(
                1,
                (new_size + self._block_size - 1) // self._block_size
            )
            try:
                self._mtime = os.path.getmtime(target)
                self._size = os.path.getsize(target)
            except Exception:
                pass

            # ---- 3. 重建 mmap ----
            self._reopen_mmap()

            return True

        except Exception as e:
            print(f"[LocalFileProvider] 脏块保存失败: {e}")
            # 失败时也要尽量恢复 mmap 状态
            self._mmap = None
            self._reopen_mmap()
            return False

    def release_mmap(self):
        """释放内存映射（保留文件描述符与全部状态）

        为什么需要（Windows 文件锁定）：
            即使只读的 `mmap` 也会**阻止文件被另一进程覆盖写**（`open(w)`
            截断会失败，报 `OSError: [Errno 22] Invalid argument`）。
            于是"编辑器打开着某个文件"就足以让 git / 构建工具 / 其它编辑器
            无法修改它 —— 外部变更检测与三方合并永远不会触发。

            因此把映射做成**可释放**的：读取时存在（快），需要让外部程序
            写入（保存后、检测变更前、重新加载后）就释放；`read_block()`
            在无映射时会回退到文件读取，所以释放后功能完全不受影响。

        注意：文件描述符也一起释放 —— Windows 上"读句柄"同样会阻止
        `open(path, 'w')` 截断。

        安全说明：小文件（<= `MMAP_MIN_SIZE`）本就不建立映射，因此本方法
        对它们只关句柄；大文件才需要真正解开映射。映射的显式 `close()`
        在 Qt 事件循环下曾经引发段错误（0xC0000005），所以这里改为
        **丢弃引用**，由 CPython 的 mmap 析构器安全回收（析构本身是安全的，
        危险的是与 Qt 视图生命周期交织时的提前显式关闭）。
        """
        self._mmap = None
        fh = self._file
        self._file = None
        if fh is not None:
            try:
                if not getattr(fh, 'closed', True):
                    fh.close()
            except Exception:
                pass

    def _ensure_handle(self) -> bool:
        """确保文件句柄与 mmap 可用（按需重建）

        `release_mmap()` 之后调用本方法即可恢复快速读取路径。
        重建使用**只读**模式（写模式会锁文件，见 `open` 的说明）。
        """
        if not self._filepath or not os.path.exists(self._filepath):
            return False
        try:
            if self._file is None or self._file.closed:
                self._file = open(self._filepath, 'rb')
            # 只对大文件建映射：小文件不留驻映射，避免锁住文件
            # （Windows 上映射会阻止外部程序覆盖写）。
            if (self._mmap is None and self._size > MMAP_MIN_SIZE):
                try:
                    self._mmap = mmap.mmap(
                        self._file.fileno(), 0, access=mmap.ACCESS_READ
                    )
                except (ValueError, OSError) as e:
                    logger.debug("重建 mmap 失败: %s", e)
            return True
        except Exception as e:
            logger.debug("重建文件句柄失败: %s", e)
            return False

    def _reopen_mmap(self):
        """重建 mmap（A4 新增，供 _save_dirty_blocks 内部调用）。

        在关闭 mmap 写盘后调用，保持 provider 后续读操作可用。

        A5 修复：调用前先显式把 self._mmap 置 None，避免
        0 长度文件（self._size <= 0 提前返回）时残留已关闭的
        mmap 对象，导致后续 read_block 对已关闭映射取值。
        """
        if not self._file:
            return

        # 已关闭的 mmap 必须先丢弃
        if self._mmap is not None:
            try:
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None

        if self._size <= 0:
            return
        try:
            # 一律只读映射：写映射会独占锁住文件（Windows），使外部程序
            # 无法修改已打开的文件 —— 那样"外部变更"永远不会发生。
            # 写入路径不依赖写映射（见 `_save_as_full` 的原子替换）。
            self._mmap = mmap.mmap(
                self._file.fileno(), 0, access=mmap.ACCESS_READ
            )
        except (ValueError, OSError):
            self._mmap = None

    def _apply_eol(self, data: bytes) -> bytes:
        """按用户显式设置的行尾符转换（保存时调用）

        缺陷背景（INV-E1，已由审计测试复现）：
            `Document.set_eol()` 只改 `meta.eol` + 标脏，其 docstring 声称
            "实际转换在保存时进行"，但**保存路径从不做转换**；
            `Document.convert_eol()` 在生产代码里**零调用**；
            `encode()` 也不碰行尾。于是用户在状态栏把 LF 切成 CRLF、
            保存后磁盘上仍是 LF —— 设置完全不生效。

        ⚠️ 只在 `_eol_explicit` 为真时转换（关键）：
            `_eol` 在打开文件时由探测得出，而探测**并不可靠** ——
            例如整篇没有换行的文件，`crlf_count(0) >= lf_count(0)` 成立，
            会默认取 CRLF。若无条件按 `_eol` 转换，这种文件的保存会把
            **原文根本没有的换行**改写掉（实测曾让 `'short\n'` 变成
            `'short\r\n'`，破坏了"保存不改动内容"的不变量）。
            因此只有用户**显式切换过**行尾才转换。

        实现说明（为什么在文本层而非字节层转换）：
            - 文本层转换对**任何**编码都正确；字节层替换会在 UTF-16 等
              编码下破坏数据（其中换行是 0x000A 两字节）。
            - 编码仍统一走 `self.encode()`，保证与保存路径一致。
        """
        if not getattr(self, '_eol_explicit', False):
            return data
        try:
            target = self._eol or EOL_LF
        except Exception:
            return data
        if target == EOL_LF:
            # 用户显式选了 LF：也需要把内容里的 CRLF 归一为 LF
            target = EOL_LF
        try:
            text = self.decode(data)
        except Exception:
            return data
        normalized = text.replace('\r\n', '\n').replace('\r', '\n')
        if target == EOL_CRLF:
            converted = normalized.replace('\n', '\r\n')
        elif target == EOL_CR:
            converted = normalized.replace('\n', '\r')
        elif target == EOL_LF:
            converted = normalized
        else:
            return data
        if converted == text:
            return data
        return self.encode(converted)

    def _replace_with_retry(self, tmp_path: str, target: str,
                            attempts: int = 10, base_delay: float = 0.02):
        """用重试的方式把临时文件替换为目标文件（Windows 必需）

        ★ 真实缺陷（混合场景压测实测发现）：

            连续"打开 → 编辑 → 保存"时，`os.replace(tmp, target)` 会**间歇性**
            抛 `PermissionError: [WinError 5] 拒绝访问`，保存直接失败。
            实测频率不低（6 轮里 1~4 轮失败），且**与文件监视器、
            自动保存无关**（两者都关掉后仍复现）—— 属于 Windows 上
            临时性共享冲突（杀毒软件/索引服务/搜索索引会在文件刚写入时
            短暂持有句柄）。

            失败时数据没丢（脏块保留、`save_file()` 返回 False），
            但用户按 Ctrl+S 会**静默失败**，这是不可接受的。

            修复：短退避重试（10 次 × 递增 20ms，总计约 1.1 秒）。
            这是 Windows 上处理"临时性共享冲突"的标准做法 ——
            不掩盖权限问题（持续失败仍会抛出并返回 False），
            只吸收毫秒级的瞬态占用。
        """
        last_error = None
        for i in range(max(1, attempts)):
            try:
                os.replace(tmp_path, target)
                if i:
                    print("[LocalFileProvider] 保存重试第 %d 次成功" % i)
                return True
            except PermissionError as e:
                last_error = e
                time.sleep(base_delay * (i + 1))
            except OSError as e:
                # Windows 上"共享冲突"有时表现为 WinError 32
                if getattr(e, "winerror", None) == 32:
                    last_error = e
                    time.sleep(base_delay * (i + 1))
                else:
                    raise
        if last_error is not None:
            raise last_error
        return False

    def _save_as_full(self, target: str) -> bool:
        """另存为完整文件（原子写入）"""
        import tempfile

        try:
            # 读取所有内容（含脏块）
            full_data = self.read_all()

            # 按文档设置的行尾符转换后再落盘（INV-E1 修复）
            full_data = self._apply_eol(full_data)

            # A5 修复：os.replace/rename 会替换 inode，而
            # self._file 仍指向旧 inode（POSIX 下即已被删除的
            # 文件），后续 mmap 重建会映射到旧内容。
            # 因此在替换前先释放 mmap + 文件句柄。
            if self._mmap:
                try:
                    self._mmap.flush()
                    self._mmap.close()
                except Exception:
                    pass
                self._mmap = None

            if self._file:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None

            # 写入临时文件
            dirpath = os.path.dirname(target)
            os.makedirs(dirpath, exist_ok=True)

            fd, tmp_path = tempfile.mkstemp(
                dir=dirpath, prefix='.qingcao_save_', suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(full_data)
                    f.flush()
                    os.fsync(f.fileno())

                # 原子重命名（带瞬态占用重试，见 `_replace_with_retry`）
                self._replace_with_retry(tmp_path, target)

            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise

            # 更新状态
            self._dirty_blocks.clear()
            self._filepath = target
            self._state = FileState.OPENED
            self._total_blocks = max(
                1,
                (len(full_data) + self._block_size - 1) // self._block_size
            )
            try:
                self._mtime = os.path.getmtime(target)
                self._size = os.path.getsize(target)
            except Exception:
                pass

            # A5: 重新打开新 inode 并重建 mmap，保证后续读取正确
            self._reopen_file_handle()
            self._reopen_mmap()

            return True

        except Exception as e:
            print(f"[LocalFileProvider] 另存为失败: {e}")
            # 尽量恢复可用状态
            try:
                self._reopen_file_handle()
                self._reopen_mmap()
            except Exception:
                pass
            return False

    def _reopen_file_handle(self) -> bool:
        """重新打开文件句柄（另存为替换 inode 后使用）。

        返回:
            是否成功重新打开
        """
        if not self._filepath:
            return False
        try:
            # 始终只读打开：写模式下 Windows 会独占锁住文件，
            # 使外部程序（git / 构建工具 / 其它编辑器）无法修改它，
            # 从而让"外部变更检测"永远失效。写入走
            # `_save_as_full` 的临时文件 + 原子替换，不需要写模式句柄。
            self._file = open(self._filepath, 'rb')
            return True
        except Exception as e:
            print(f"[LocalFileProvider] 重开文件句柄失败: {e}")
            self._file = None
            return False

    # --------------------------------------------------------
    # 关闭
    # --------------------------------------------------------
    def close(self):
        """关闭文件并释放资源"""
        # 关闭 mmap
        if self._mmap:
            try:
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None

        # 关闭文件句柄
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

        # 清空状态
        self._dirty_blocks.clear()
        self._loaded_blocks.clear()
        self._state = FileState.CLOSED

    # --------------------------------------------------------
    # 文件变更检测
    # --------------------------------------------------------
    def check_external_change(self) -> bool:
        """
        检查文件是否被外部程序修改。

        返回:
            True 表示文件已被外部修改
        """
        if not self._filepath or not os.path.exists(self._filepath):
            return False

        try:
            current_mtime = os.path.getmtime(self._filepath)
            return abs(current_mtime - self._mtime) > 0.001
        except Exception as e:
            # 不能把"检查失败"当成"没被改过"（fail-open）：
            # 那样外部篡改会被静默忽略，用户下次保存就覆盖掉别人的修改。
            # 这里改为**保守判定为已变更**（fail-safe），并把原因打出来。
            print(f"[LocalFileProvider] 外部变更检查失败（保守判定为已变更）: {e}")
            return True

    def reload(self) -> bool:
        """重新加载文件内容"""
        if not self._filepath:
            return False
        filepath = self._filepath
        encoding = self._encoding
        readonly = self._readonly

        self.close()
        try:
            self.open(filepath, encoding=encoding, readonly=readonly,
                      detect_encoding=False)
            return True
        except Exception as e:
            print(f"[LocalFileProvider] 重新加载失败: {e}")
            return False

    # --------------------------------------------------------
    # 文件信息
    # --------------------------------------------------------
    def get_file_info(self) -> Dict[str, Any]:
        """获取文件详细信息"""
        info = self.get_info()
        info.update({
            'file_size': self._size,
            'file_size_mb': round(self._size / 1024 / 1024, 2),
            'mtime': self._mtime,
            'is_large': self._size > LARGE_FILE_THRESHOLD,
            'is_huge': self._size > HUGE_FILE_THRESHOLD,
            'loaded_blocks': len(self._loaded_blocks),
            'readonly_reason': (
                '用户指定' if self._readonly and not os.access(
                    self._filepath or '', os.W_OK
                ) else '文件权限' if self._readonly else None
            ),
        })
        return info

    def get_readonly_status(self) -> bool:
        """返回是否只读"""
        return self._readonly

    def set_readonly(self, readonly: bool) -> bool:
        """设置只读状态"""
        if not self._filepath:
            return False

        if readonly:
            self._readonly = True
            self._state = FileState.READONLY
            return True

        # 尝试切换为可写
        if not os.access(self._filepath, os.W_OK):
            return False

        self._readonly = False
        if self._state == FileState.READONLY:
            self._state = FileState.OPENED
        return True


# ============================================================
# 内存提供者
# ============================================================
