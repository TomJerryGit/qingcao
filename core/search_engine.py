# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""搜索/文件搜索（v2.24 拆出）。"""

from core.search_common import *  # noqa: F401,F403,F405


class SearchEngine:
    """
    单文件搜索引擎。

    支持:
    - 正则表达式匹配
    - 大小写敏感/不敏感
    - 全词匹配
    - 多线程并行搜索
    - Hyperscan 加速（如可用）
    - 结果超时与取消
    - 增量返回（流式）
    """

    def __init__(self, provider, options: Optional[SearchOptions] = None):
        """
        参数:
            provider: 内容提供者（ContentProvider）
            options: 搜索选项
        """
        self.provider = provider
        # P7：未显式传入 options 时，从 Preferences 取 search_threads /
        # use_hyperscan / search_timeout，而不是硬编码默认值。
        self.options = options or SearchOptions.from_preferences()

        # 取消标志
        self._cancel_event = threading.Event()

        # 统计
        self.statistics = SearchStatistics()

        # 编译后的正则
        self._regex: Optional[re.Pattern] = None
        self._hyperscan_db = None

        # 行索引缓存（P2-9：用于 _position_to_line_col 加速）
        # 存储每一行（0-based）的起始**字符**位置。
        # index[0] 恒为 0；index[i+1] = 第 i 行末尾换行符的字符位置 + 1。
        # 惰性构建：首次调用 _position_to_line_col 时构建。
        self._line_offsets: Optional[List[int]] = None
        self._line_index_lock = threading.Lock()

        # 行文本表缓存（A6 修复：消除 _get_line_text 的 O(n²) 行为）
        # 存储每行 text[start:end] 的字符切片边界（不含换行符）。
        # 惰性构建一次并复用，避免"每个匹配都重读整个文件"。
        self._line_table: Optional[List[Tuple[int, int]]] = None
        self._line_table_lock = threading.Lock()
        # A6: 行起始位置表（含末尾哨兵）+ 解码后全文缓存
        self._line_offsets_full: Optional[List[int]] = None
        self._text_cache: Optional[str] = None

    # --------------------------------------------------------
    # 编译
    # --------------------------------------------------------
    def compile(self) -> bool:
        """
        编译搜索模式。

        返回:
            是否成功
        """
        if not self.options.pattern:
            return False

        try:
            pattern_str = self.options.build_pattern()
            flags = self.options.to_regex_flags()
            self._regex = re.compile(pattern_str, flags)

            # 尝试编译 Hyperscan
            if HYPERSCAN_AVAILABLE and self.options.use_hyperscan and self.options.is_regex:
                try:
                    self._compile_hyperscan(pattern_str, flags)
                except Exception:
                    self._hyperscan_db = None

            return True

        except re.error as e:
            print(f"[SearchEngine] 正则编译失败: {e}")
            return False
        except Exception as e:
            print(f"[SearchEngine] 编译失败: {e}")
            return False

    def _compile_hyperscan(self, pattern: str, flags: int):
        """编译 Hyperscan 数据库"""
        hs_flags = hyperscan.HS_FLAG_SOM_LEFTMOST
        if not (flags & re.IGNORECASE):
            hs_flags |= hyperscan.HS_FLAG_CASELESS
        if flags & re.MULTILINE:
            hs_flags |= hyperscan.HS_FLAG_MULTILINE
        if flags & re.DOTALL:
            hs_flags |= hyperscan.HS_FLAG_DOTALL

        db = hyperscan.Database()
        db.compile(
            expressions=[pattern.encode("utf-8")],
            ids=[0],
            flags=[hs_flags],
        )
        self._hyperscan_db = db

    # --------------------------------------------------------
    # 取消控制
    # --------------------------------------------------------
    def cancel(self):
        """取消当前搜索"""
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self._cancel_event.is_set()

    def reset_cancel(self):
        """重置取消标志"""
        self._cancel_event.clear()

    # --------------------------------------------------------
    # 搜索入口
    # --------------------------------------------------------
    def search(self) -> SearchResult:
        """
        执行搜索（同步）。

        返回:
            SearchResult
        """
        result = SearchResult(pattern=self.options.pattern)
        start_time = time.time()

        self.reset_cancel()

        try:
            # 编译
            if not self.compile():
                result.error = "搜索模式编译失败"
                return result

            # 检查提供者
            if not self.provider or not self.provider.is_open:
                result.error = "提供者未打开"
                return result

            # 执行搜索
            if self.options.threads > 1 and not self.options.is_regex:
                self._search_multi_threaded(result)
            else:
                self._search_single_threaded(result)

            # 记录耗时
            result.elapsed_ms = (time.time() - start_time) * 1000
            result.cancelled = self.is_cancelled()

        except Exception as e:
            result.error = str(e)
            print(f"[SearchEngine] 搜索失败: {e}")

        # 记录统计
        self.statistics.record(result)

        return result

    def search_streaming(self, callback: Callable[[SearchMatch], bool]) -> SearchResult:
        """
        流式搜索（每找到一个匹配调用一次回调）。

        参数:
            callback: 处理匹配的回调，返回 False 可停止搜索

        返回:
            SearchResult（不包含所有匹配，仅统计信息）
        """
        result = SearchResult(pattern=self.options.pattern)
        start_time = time.time()

        self.reset_cancel()

        try:
            if not self.compile():
                result.error = "搜索模式编译失败"
                return result

            if not self.provider or not self.provider.is_open:
                result.error = "提供者未打开"
                return result

            # 流式搜索
            for match in self.iter_matches():
                if self.is_cancelled():
                    result.cancelled = True
                    break

                result.total_matches += 1

                if callback:
                    try:
                        if not callback(match):
                            break
                    except Exception as e:
                        print(f"[SearchEngine] 回调异常: {e}")

            result.elapsed_ms = (time.time() - start_time) * 1000

        except Exception as e:
            result.error = str(e)

        self.statistics.record(result)
        return result

    def iter_matches(self) -> Iterator[SearchMatch]:
        """
        迭代所有匹配（生成器）。

        P1-1 修复：原分块逻辑把"字节偏移 + 字符偏移"混用，
        导致含中文文件搜索位置错误。改为一次性读取全文，
        匹配位置统一换算：字节偏移 + 字符偏移双写。

        性能：O(N) 正则扫描，大文件也能接受。
        """
        if not self._regex:
            return

        # 一次性读取全文（避免分块的偏移换算问题）
        try:
            text = self.provider.read_text()
        except Exception:
            return

        if not text:
            return

        encoding = self.provider.encoding or "utf-8"
        count = 0

        # 缓存上一次匹配的字节位置，避免每次重算前缀
        last_char_end = 0
        last_byte_end = 0

        for m in self._regex.finditer(text):
            if self.is_cancelled():
                return
            if count >= self.options.max_results:
                return

            char_start = m.start()
            char_end = m.end()

            # 字符偏移 -> 字节偏移（增量计算）
            if char_start >= last_char_end:
                byte_start = last_byte_end + len(
                    text[last_char_end:char_start].encode(encoding, errors="replace")
                )
            else:
                # finditer 是顺序的，正常不会走这里
                byte_start = len(text[:char_start].encode(encoding, errors="replace"))

            byte_end = byte_start + len(
                text[char_start:char_end].encode(encoding, errors="replace")
            )

            last_char_end = char_end
            last_byte_end = byte_end

            # 范围过滤（用字节偏移）
            if byte_start < self.options.start_pos:
                continue
            if self.options.end_pos >= 0 and byte_start >= self.options.end_pos:
                return

            match = self._build_match(
                byte_start,
                byte_end,
                char_start,
                char_end,
                m,
                text,
            )
            yield match
            count += 1

    # --------------------------------------------------------
    # 单线程搜索
    # --------------------------------------------------------
    def _search_single_threaded(self, result: SearchResult):
        """单线程搜索"""
        for match in self.iter_matches():
            if self.is_cancelled():
                result.cancelled = True
                break
            if not result.add_match(match):
                break

    # --------------------------------------------------------
    # 多线程搜索
    # --------------------------------------------------------
    def _search_multi_threaded(self, result: SearchResult):
        """多线程搜索（P1-1: 已废弃多线程分块）

        说明:
            原实现把文件分块并行搜索，但匹配位置需要"全局字
            节偏移"，分块后跨块偏移换算极其复杂且容易出错。
            改为单线程一次性搜索；正则扫描本身是 O(N)，
            分块对性能提升有限。
        """
        self._search_single_threaded(result)

    def _search_range(self, start_block: int, end_block: int) -> List[SearchMatch]:
        """P1-1: _search_range 已废弃。

        保留方法名以兼容外部可能的调用，但不再使用。
        """
        return []

    # --------------------------------------------------------
    # 匹配构建
    # --------------------------------------------------------
    def _build_match(
        self, byte_start: int, byte_end: int, char_start: int, char_end: int, re_match, text: str
    ) -> SearchMatch:
        """构建 SearchMatch 对象（P1-1: 双写字节/字符偏移）"""
        # 用字符偏移计算行列
        line, col = self._position_to_line_col(char_start)

        line_text = self._get_line_text(line)

        # 上下文预览（text 内部是字符偏移）
        context = self._make_context(text, char_start, char_end)

        groups = tuple(g for g in re_match.groups()) if re_match.groups() else ()

        return SearchMatch(
            start=byte_start,
            end=byte_end,
            char_start=char_start,
            char_end=char_end,
            text=re_match.group(0),
            line=line,
            col=col,
            line_text=line_text,
            context=context,
            groups=groups,
        )

    # --------------------------------------------------------
    # 行索引（P2-9 性能优化）
    # --------------------------------------------------------
    def _build_line_index(self) -> List[int]:
        """构建行起始字符位置索引

        A6 修复历史（重要教训）:
            1. 先修复了 `_get_line_text` 的 O(n²) 行为（每匹配重读全文）。
            2. 随后发现 `_build_match` 会同时走 `_position_to_line_col`
               与 `_get_line_text`，于是尝试"合并两份索引"，把本方法
               改为 `return self._ensure_line_index()[:-1]`。
            3. **这个合并引入了新的 13× 退化**：切片的 `index[:-1]`
               每次都会拷贝整个行起始表。实测 1 MB（19 065 行）：

                   _position_to_line_col  169.54 µs/次
                   其中列表拷贝           182.98 µs/次
                   纯 bisect                0.60 µs/次

               1 MB 有 19 065 个匹配 → 约 3.5 s 全花在拷贝上
               （合并前 0.268 s）。

            4. 现在改为：**直接返回缓存的索引，不做任何切片/拷贝**。
               索引末尾的哨兵（= 全文长度）不会影响
               `_position_to_line_col` 的 bisect —— 因为
               `position` 作为 `finditer` 的偏移必然 `< len(text)`，
               `bisect_right` 永远不会选中哨兵。

        返回:
            List[int]，索引数组（末尾可能含 len(text) 哨兵）。
        """
        index = self._ensure_line_index()
        return index if index else [0]

    def _position_to_line_col(self, position: int) -> Tuple[int, int]:
        """
        将字符位置转换为 (行, 列)。

        参数:
            position: 字符偏移（0-based）

        返回:
            (行号（1-based）, 列号（0-based））

        修复说明（P2-9）:
            - 原实现每次调用都会从头读取文件到 position，
              复杂度 O(position)，多个匹配时总复杂度 O(N × file_size)。
            - 现在改用惰性构建的行索引 + 二分查找：
              * 首次调用 O(file_size) 构建索引；
              * 之后每次调用 O(log lines)。
        """
        try:
            index = self._build_line_index()

            if not index:
                return (1, 0)

            if position <= 0:
                return (1, 0)

            # 二分查找：找到最大的 i 使 index[i] <= position
            import bisect

            line_idx = bisect.bisect_right(index, position) - 1
            if line_idx < 0:
                line_idx = 0

            col = position - index[line_idx]
            # line 是 1-based
            return (line_idx + 1, col)
        except Exception:
            return (1, 0)

    def _read_text_up_to(self, position: int) -> str:
        """
        [已弃用] 读取指定位置之前的文本。

        保留作为兼容接口。P2-9 后 _position_to_line_col 不再使用此方法，
        而是使用 _build_line_index 构建的索引。

        警告：对超大文件，此方法可能产生显著内存开销。新代码不应调用。
        """
        if position <= 0:
            return ""

        block_size = self.provider.block_size
        end_block = position // block_size

        chunks = []
        for bid in range(end_block + 1):
            if bid == end_block:
                # 最后一块只取到 position
                data = self.provider.read_block(bid)
                offset_in_block = position - bid * block_size
                data = data[:offset_in_block]
            else:
                data = self.provider.read_block(bid)

            try:
                chunks.append(data.decode(self.provider.encoding, errors="replace"))
            except Exception:
                pass

        return "".join(chunks)

    def _get_line_text(self, line: int) -> str:
        """获取指定行的文本（1-based 行号）

        A6 修复（严重性能缺陷）：
            原实现每次调用都执行

                text = self.provider.read_text()
                lines = text.splitlines()

            即**读取并切分整个文件**。而它被 `_build_match` 在
            **每一个匹配**上调用一次，于是复杂度从 O(N) 退化为
            O(匹配数 × 文件大小) ≈ O(N²)。

            实测（1 行 50 字符的重复文本，纯文本搜索 "quick"）：

                16 KB   0.031 s     297 匹配
                64 KB   0.426 s    1191 匹配
                256 KB  9.799 s    4766 匹配
                1 MB    > 25 s 未完成
                10 MB   > 15 min 无输出

            这使"大文件搜索"在实际使用中不可用。

            现在改为：**只构建一次**行偏移表（复用已有的 `text`
            解码结果，不额外读盘），之后每行取值都是二分查找 +
            O(行长) 切片。
        """
        try:
            index = self._ensure_line_index()
            if index is None:
                return ""

            # 定位所属行（1-based -> 0-based）
            if line < 1:
                return ""
            line_idx = line - 1
            if line_idx >= len(index) - 1:
                # 超出最后一行（原实现对越界返回 ""）
                return ""

            start = index[line_idx]
            end = index[line_idx + 1]

            text = self._text_cache
            if text is None:
                text = self.provider.read_text()
                self._text_cache = text

            if start < 0 or start > len(text):
                return ""

            # 去掉行尾换行符（保留原始内容语义）
            line_text = text[start:end]
            if line_text.endswith("\r\n"):
                return line_text[:-2]
            if line_text.endswith("\n") or line_text.endswith("\r"):
                return line_text[:-1]
            return line_text

        except Exception:
            return ""

    def _ensure_line_index(self) -> Optional[List[int]]:
        """构建（并缓存）行起始位置表，末尾追加全文长度哨兵。

        A6 修复：这是本项目**唯一的权威行索引**。

        `index[i]` 是第 i 行（0-based）的起始字符位置，
        `index[i+1]` 即第 i 行的结束位置（不含换行符），
        因此按行取文本只需 `text[index[i]:index[i+1]]` 一次切片，
        不需要额外的"行文本表"。

        末尾哨兵 = 全文长度，用于给最后一行（可能没有换行结尾）
        提供结束位置；它不会干扰 bisect（见 `_build_line_index`）。

        构建时顺带缓存 `_text_cache`，避免再次解码全文。
        """
        # 快速路径：已构建（无锁读，命中率最高）
        index = self._line_offsets_full
        if index is not None:
            return index

        with self._line_table_lock:
            # double-check
            index = self._line_offsets_full
            if index is not None:
                return index

            try:
                text = self.provider.read_text()
            except Exception:
                return None

            self._text_cache = text

            index = [0]
            pos = text.find("\n")
            while pos >= 0:
                index.append(pos + 1)
                pos = text.find("\n", pos + 1)

            # 末尾哨兵：最后一行（无换行结尾时）的结束位置
            if index[-1] != len(text):
                index.append(len(text))

            self._line_offsets_full = index
            return index

    def _make_context(
        self, text: str, start: int, end: int, max_len: int = CONTEXT_PREVIEW_LENGTH
    ) -> str:
        """生成匹配的上下文预览"""
        try:
            # 找到行边界
            line_start = text.rfind("\n", 0, start)
            line_start = line_start + 1 if line_start >= 0 else 0

            line_end = text.find("\n", end)
            line_end = line_end if line_end >= 0 else len(text)

            line_text = text[line_start:line_end]

            # 如果太长，截取匹配附近
            if len(line_text) > max_len:
                match_center = start - line_start
                half = max_len // 2
                ctx_start = max(0, match_center - half)
                ctx_end = min(len(line_text), match_center + half)

                prefix = "..." if ctx_start > 0 else ""
                suffix = "..." if ctx_end < len(line_text) else ""

                return prefix + line_text[ctx_start:ctx_end] + suffix

            return line_text
        except Exception:
            return ""

    # --------------------------------------------------------
    # 替换
    # --------------------------------------------------------
    def replace_all(self, replacement: str, result: Optional[SearchResult] = None) -> int:
        """
        替换所有匹配（在提供者中）。

        注意：此方法直接修改提供者的内容，但不会立即保存。

        参数:
            replacement: 替换文本（支持正则反向引用 \1 \2 等）
            result: 可选的搜索结果（None 则先执行搜索）

        返回:
            替换的数量
        """
        if not self._regex:
            if not self.compile():
                return 0

        if result is None:
            result = self.search()

        if result.is_empty:
            return 0

        # 从后往前替换，避免位置偏移
        count = 0
        for match in reversed(result.matches):
            try:
                # 计算替换文本
                if self.options.is_regex:
                    # 使用捕获组替换
                    re_match = self._regex.match(match.text)
                    if re_match:
                        new_text = re_match.expand(replacement)
                    else:
                        new_text = replacement
                else:
                    new_text = replacement

                # 更新提供者内容（P1-1: 用字符偏移）
                self._replace_range(match.char_start, match.char_end, new_text)
                count += 1

            except Exception as e:
                print(f"[SearchEngine] 替换失败: {e}")
                continue

        return count

    def _replace_range(self, start: int, end: int, new_text: str):
        """
        替换指定范围的文本。

        由于 ContentProvider 是块结构，需要特殊处理。
        """
        try:
            # 读取全部内容
            text = self.provider.read_text()

            # 替换
            new_content = text[:start] + new_text + text[end:]

            # 写回提供者
            encoded = self.provider.encode(new_content)
            block_size = self.provider.block_size
            total_blocks = max(1, (len(encoded) + block_size - 1) // block_size)

            # 清空并重写
            self.provider.clear_dirty()

            for bid in range(total_blocks):
                bstart = bid * block_size
                bend = min(bstart + block_size, len(encoded))
                self.provider.write_block(bid, encoded[bstart:bend])

            # 更新块数
            if hasattr(self.provider, "_total_blocks"):
                self.provider._total_blocks = total_blocks
            if hasattr(self.provider, "_size"):
                self.provider._size = len(encoded)

        except Exception as e:
            print(f"[SearchEngine] 替换范围失败: {e}")

    # --------------------------------------------------------
    # 信息查询
    # --------------------------------------------------------
    def get_pattern(self) -> str:
        """获取搜索模式"""
        return self.options.pattern

    def get_options(self) -> SearchOptions:
        """获取搜索选项"""
        return self.options

    def is_compiled(self) -> bool:
        """是否已编译"""
        return self._regex is not None

    def __repr__(self) -> str:
        return (
            f"<SearchEngine pattern={self.options.pattern!r} "
            f"regex={self.options.is_regex} "
            f"compiled={self.is_compiled()}>"
        )


# ============================================================
# 多文件搜索引擎（全局搜索）
# ============================================================


class FileSearcher(QObject):
    """
    多文件搜索引擎（在项目中查找）。

    支持:
    - 目录递归遍历
    - 文件类型过滤
    - 多线程并行搜索
    - 结果分批推送
    - 搜索取消
    - 进度报告

    信号:
        search_started(str, int): 搜索开始（pattern, 文件数）
        file_result(str, list): 单个文件结果（路径, 匹配列表）
        search_progress(int, int): 进度（已搜索文件数, 总文件数）
        search_finished(SearchResult): 搜索完成
        search_error(str): 搜索错误
    """

    search_started = pyqtSignal(str, int)
    file_result = pyqtSignal(str, list)
    search_progress = pyqtSignal(int, int)
    search_finished = pyqtSignal(object)
    search_error = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 当前搜索状态
        self._searching: bool = False
        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        # 统计
        self.statistics = SearchStatistics()

    @property
    def is_searching(self) -> bool:
        """是否正在搜索"""
        return self._searching

    # --------------------------------------------------------
    # 搜索入口
    # --------------------------------------------------------
    def search(
        self,
        root_dir: str,
        options: SearchOptions,
        file_filter: str = "*.*",
        exclude_dirs: Optional[List[str]] = None,
        include_hidden: bool = False,
    ) -> SearchResult:
        """
        执行多文件搜索（异步）。

        参数:
            root_dir: 根目录
            options: 搜索选项
            file_filter: 文件过滤（如 "*.py" 或 "*.py;*.txt"）
            exclude_dirs: 排除的目录名列表
            include_hidden: 是否包含隐藏文件

        返回:
            SearchResult（异步执行，实际结果通过信号返回）
        """
        if self._searching:
            result = SearchResult(pattern=options.pattern)
            result.error = "搜索正在进行中"
            return result

        self._cancel_event.clear()
        self._searching = True

        # 收集文件列表
        try:
            files = self._collect_files(root_dir, file_filter, exclude_dirs, include_hidden)
        except Exception as e:
            self._searching = False
            result = SearchResult(pattern=options.pattern)
            result.error = f"收集文件失败: {e}"
            return result

        # 启动后台线程
        self._worker = threading.Thread(
            target=self._do_search,
            args=(files, options),
            daemon=True,
        )
        self._worker.start()

        # 返回空结果（实际结果通过信号）
        return SearchResult(pattern=options.pattern)

    def search_sync(
        self,
        root_dir: str,
        options: SearchOptions,
        file_filter: str = "*.*",
        exclude_dirs: Optional[List[str]] = None,
        include_hidden: bool = False,
    ) -> SearchResult:
        """
        同步执行多文件搜索。

        参数同上，返回完整结果。
        """
        start_time = time.time()
        result = SearchResult(pattern=options.pattern)
        result.skipped_large = 0

        try:
            files = self._collect_files(root_dir, file_filter, exclude_dirs, include_hidden)

            for filepath in files:
                if self._cancel_event.is_set():
                    result.cancelled = True
                    break

                try:
                    if os.path.getsize(filepath) >= SEARCH_LARGE_FILE_LIMIT:
                        result.skipped_large += 1
                        continue
                except Exception:
                    pass
                file_matches = self._search_file(filepath, options)
                if file_matches:
                    result.file_results[filepath] = file_matches
                    for m in file_matches:
                        result.add_match(m)

            result.elapsed_ms = (time.time() - start_time) * 1000

        except Exception as e:
            result.error = str(e)

        self.statistics.record(result)
        return result

    def cancel(self):
        """取消搜索"""
        self._cancel_event.set()

    def _do_search(self, files: List[str], options: SearchOptions):
        """后台搜索线程"""
        start_time = time.time()
        result = SearchResult(pattern=options.pattern)
        result.skipped_large = 0

        try:
            self.search_started.emit(options.pattern, len(files))

            total = len(files)
            for i, filepath in enumerate(files):
                if self._cancel_event.is_set():
                    result.cancelled = True
                    break

                # 大文件跳过（v2.17.x）
                try:
                    if os.path.getsize(filepath) >= SEARCH_LARGE_FILE_LIMIT:
                        result.skipped_large += 1
                        continue
                except Exception:
                    pass
                # 搜索单个文件
                file_matches = self._search_file(filepath, options)

                if file_matches:
                    result.file_results[filepath] = file_matches
                    for m in file_matches:
                        result.add_match(m)

                    # 发射文件结果
                    self.file_result.emit(filepath, file_matches)

                # 进度
                self.search_progress.emit(i + 1, total)

            result.elapsed_ms = (time.time() - start_time) * 1000

        except Exception as e:
            result.error = str(e)
            self.search_error.emit(str(e))

        finally:
            self._searching = False
            self.statistics.record(result)
            self.search_finished.emit(result)

    def _search_file(self, filepath: str, options: SearchOptions) -> List[SearchMatch]:
        """搜索单个文件"""
        matches = []

        try:
            # 检查文件大小
            if os.path.getsize(filepath) > MAX_FILE_SIZE:
                return matches

            # 检查是否二进制
            if self._is_binary(filepath):
                return matches

            # 创建临时提供者
            from core.content_provider import LocalFileProvider

            provider = LocalFileProvider()
            provider.open(filepath, detect_encoding=True)

            try:
                engine = SearchEngine(provider, options)
                result = engine.search()

                # 调整行号（相对于文件）
                matches = result.matches

            finally:
                provider.close()

        except Exception:
            pass

        return matches

    def _collect_files(
        self,
        root_dir: str,
        file_filter: str,
        exclude_dirs: Optional[List[str]],
        include_hidden: bool,
    ) -> List[str]:
        """收集符合条件的文件"""
        files = []

        if not os.path.isdir(root_dir):
            return files

        exclude_dirs = exclude_dirs or [
            ".git",
            ".svn",
            ".hg",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".idea",
            ".vscode",
        ]

        # 解析文件过滤
        patterns = self._parse_filter(file_filter)

        for dirpath, dirnames, filenames in os.walk(root_dir):
            # 排除目录
            dirnames[:] = [
                d
                for d in dirnames
                if d not in exclude_dirs and (include_hidden or not d.startswith("."))
            ]

            for filename in filenames:
                if not include_hidden and filename.startswith("."):
                    continue

                if patterns and not self._match_filter(filename, patterns):
                    continue

                full_path = os.path.join(dirpath, filename)
                files.append(full_path)

        return files

    @staticmethod
    def _parse_filter(file_filter: str) -> List[str]:
        """解析文件过滤字符串"""
        if not file_filter or file_filter == "*.*" or file_filter == "*":
            return []

        patterns = []
        for part in file_filter.split(";"):
            part = part.strip()
            if part:
                patterns.append(part)
        return patterns

    @staticmethod
    def _match_filter(filename: str, patterns: List[str]) -> bool:
        """检查文件名是否匹配过滤条件"""
        import fnmatch

        for pattern in patterns:
            if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                return True
        return False

    @staticmethod
    def _is_binary(filepath: str, sample_size: int = 1024) -> bool:
        """检查是否为二进制文件"""
        try:
            with open(filepath, "rb") as f:
                sample = f.read(sample_size)
            return b"\x00" in sample
        except Exception:
            return True


# ============================================================
# 替换引擎
# ============================================================
