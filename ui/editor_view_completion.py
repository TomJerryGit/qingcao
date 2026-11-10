# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""自动补全职责（v2.24 拆出）。"""

from ui.editor_view_common import *  # noqa: F401,F403,F405


class EditorCompletionMixin:
    def _setup_autocompletion(self):
        """
        配置自动补全，并接管候选来源。

        P10 之前:
            setAutoCompletionSource(AcsAll) —— 走 QScintilla 内置弹窗，
            只补"当前文档里出现过的单词"，没有语言关键字、没有词频排序，
            且 core/local_completer.LocalCompleter **完全未被调用**。

        P10 之后:
            关闭 QScintilla 内置弹窗（AcsNone），改由本类在
            SCN_CHARADDED / Ctrl+Space 时用 LocalCompleter 取候选，
            再经 SCI_AUTOCSHOW 弹出（与 core/editor.py 的 LSP 补全
            使用同一条 Scintilla 通道）。
            "文档词补全"能力没有丢：LocalCompleter 的 file_words /
            word_freq 就是文档词来源，见 _sync_completion_words。

        不受影响的行为: 括号/引号自动闭合、智能缩进、折叠等与
        补全无关的 QScintilla 行为一律未改动。
        """
        try:
            # AcsNone: 内置弹窗关闭，避免与自定义候选在同一按键上互相覆盖
            self.setAutoCompletionSource(QsciScintilla.AcsNone)
        except Exception:
            pass
        try:
            # -1 = 不使用内置阈值；触发门槛由 _completion_min_prefix 控制
            self.setAutoCompletionThreshold(-1)
        except Exception:
            pass
        try:
            self.setAutoCompletionCaseSensitivity(False)
            self.setAutoCompletionReplaceWord(False)
        except Exception:
            pass

    def _completion_language(self) -> str:
        """把当前文件扩展名映射到 LocalCompleter 的语言键（未知则空串）"""
        ext = os.path.splitext(self._completion_key())[1].lower()
        return COMPLETION_LANGUAGE_BY_EXT.get(ext, "")

    def _completion_key(self) -> str:
        """
        当前缓冲区的词频键。

        已保存文件用真实路径（这样 LocalCompleter 的 file_words
        能与磁盘文件对应），未保存缓冲区用稳定的实例内键。
        """
        try:
            filepath = getattr(self.document, "filepath", "") or ""
        except Exception:
            filepath = ""
        return filepath or self._completion_buffer_key

    def _current_prefix(self) -> Tuple[str, int]:
        """
        取光标左侧的标识符前缀。

        返回:
            (前缀, 前缀的 UTF-8 字节长度)；光标不在标识符末尾时返回 ("", 0)

        说明: 本文件统一按**字节偏移**处理 Scintilla 位置
        （见 _smart_home / _wrap_selection 的修复记录），这里同样用
        SCI_GETCURRENTPOS 减行首位置得到字节偏移，避免中英文混排错位。
        """
        try:
            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
            line = self.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, pos)
            line_start = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
            line_text = self.text(line)
            offset = max(0, pos - line_start)
            head = line_text.encode("utf-8")[:offset].decode("utf-8", "ignore")
        except Exception:
            return "", 0

        match = re.search(r"[A-Za-z_][A-Za-z0-9_]*\Z", head)
        if match is None:
            return "", 0
        prefix = match.group(0)
        return prefix, len(prefix.encode("utf-8"))

    def _sync_completion_words(self) -> None:
        """
        把当前文档内容同步给 LocalCompleter。

        性能保护（P10）: 全量正则扫描文档词频在长文档上有成本，
        因此按 COMPLETION_INDEX_MIN_INTERVAL 节流；候选结果本身
        另有 COMPLETION_CACHE_TTL 前缀缓存。
        """
        now = time.time()
        if (now - self._completion_index_ts) < COMPLETION_INDEX_MIN_INTERVAL:
            return
        try:
            text = self.text()
        except Exception:
            return
        try:
            self._local_completer.update_from_file(self._completion_key(), text)
        except Exception as e:
            print(f"[EditorWidget] 更新补全词频失败: {e}")
            return
        self._completion_index_ts = now
        self._completion_cache.clear()

    def local_completions(self, prefix: str) -> List[str]:
        """
        用 LocalCompleter 计算候选词（公开方法，便于测试与插件复用）。

        参数:
            prefix: 已输入的前缀

        返回:
            候选词列表，排序为: 最近使用 -> 语言关键字 ->
            当前文件词频 -> 全局词频
        """
        if not self._completion_enabled:
            return []
        if not prefix or len(prefix) < self._completion_min_prefix:
            return []

        self._sync_completion_words()
        try:
            items = self._local_completer.get_completions(
                prefix,
                filepath=self._completion_key(),
                language=self._completion_language(),
                limit=COMPLETION_MAX_ITEMS,
            )
        except Exception as e:
            print(f"[EditorWidget] 本地补全计算失败: {e}")
            return []

        words = [word for word, _source in items]

        # v2.3：合并插件补全提供者（插件通过 api.register_completion_provider
        # 注册；异常/缺失宿主时静默降级，不影响本地补全）。
        try:
            win = self.window()
            collector = getattr(win, "collect_plugin_completions", None)
            if callable(collector):
                extra = collector(
                    prefix,
                    language=self._completion_language(),
                    filepath=self._completion_key(),
                    limit=COMPLETION_MAX_ITEMS,
                )
                seen = set(words)
                for word in extra:
                    if word not in seen:
                        words.append(word)
                        seen.add(word)
        except Exception as e:
            print(f"[EditorWidget] 插件补全合并失败: {e}")

        return words[:COMPLETION_MAX_ITEMS]

    def trigger_local_completion(self, force: bool = False) -> List[str]:
        """
        按当前前缀弹出本地补全列表。

        参数:
            force: True 时忽略前缀长度门槛（供 Ctrl+Space 使用）

        返回:
            本次实际使用的候选词列表（可能来自前缀缓存）
        """
        if not self._completion_enabled:
            return []

        prefix, prefix_bytes = self._current_prefix()
        if not prefix:
            return []
        if not force and len(prefix) < self._completion_min_prefix:
            return []

        now = time.time()
        cached = self._completion_cache.get(prefix)
        if cached is not None and (now - cached[0]) < COMPLETION_CACHE_TTL:
            words = list(cached[1])
        else:
            words = self.local_completions(prefix)
            self._completion_cache[prefix] = (now, list(words))
            if len(self._completion_cache) > COMPLETION_CACHE_MAX_ENTRIES:
                self._completion_cache.clear()

        if not words:
            return []

        try:
            self.SendScintilla(
                QsciScintilla.SCI_AUTOCSHOW,
                prefix_bytes,
                " ".join(words).encode("utf-8"),
            )
        except Exception as e:
            print(f"[EditorWidget] 弹出本地补全失败: {e}")
        return words

    def _on_completion_accepted(self, *args):
        """
        补全项被用户接受后的回调（P10）。

        SCN_AUTOCCOMPLETED / SCN_AUTOCSELECTION 的第一个参数是选中的
        词（sip 里是 str，个别版本是 bytes）；这里两种都兼容。
        """
        word = ""
        for arg in args:
            if isinstance(arg, str) and arg:
                word = arg
                break
            if isinstance(arg, (bytes, bytearray)):
                text = bytes(arg).decode("utf-8", "ignore")
                if text:
                    word = text
                    break
        if not word:
            return
        try:
            self._local_completer.record_used(word)
        except Exception as e:
            print(f"[EditorWidget] 记录补全使用失败: {e}")

    # ========================================================
    # 语法高亮
    # ========================================================
