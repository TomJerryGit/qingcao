# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""从 core/editor.py 拆出的 search 职责（v2.23 D1）。"""

from core.editor_common import *  # noqa: F401,F403
from core.editor_common import (  # noqa: F401
    _EOL_SPLIT_RE,
    _normalize_bytes,
    _trim_trailing_ws_keep_eol,
)


class EditorSearchMixin:
    # ========================================================
    # 搜索与高亮
    # ========================================================
    def highlight_all(
        self,
        pattern: str,
        case_sensitive: bool = False,
        is_regex: bool = False,
        whole_word: bool = False,
    ) -> int:
        """
        高亮所有匹配项。

        参数:
            pattern: 搜索内容
            case_sensitive: 是否区分大小写
            is_regex: 是否按正则解释
            whole_word: 是否整词匹配

        返回:
            匹配数量

        修复（两处真实缺陷）：
          1. 原先查 `document.provider` 快照 —— 刚输入的文字高亮不出来；
          2. 原先**硬编码 `is_regex=True`** —— 而搜索栏传进来的是用户原始
             输入，于是搜 `a.b` 得到正则语义、搜 `(` 直接抛 `re.error`。
             现在正则与否由调用方决定，默认按**字面量**处理。
        """
        try:
            self.clear_highlights()

            if not pattern:
                return 0

            options = SearchOptions(
                pattern=pattern,
                is_regex=is_regex,
                case_sensitive=case_sensitive,
                whole_word=whole_word,
            )
            # 走编辑器缓冲区（provider 是保存时的快照，会漏掉未保存内容）
            matches = self._buffer_find_all(options)

            if not matches:
                return 0

            # 分批绘制（避免大量匹配卡顿）
            if len(matches) > 1000:
                for i in range(0, len(matches), 500):
                    batch = matches[i : i + 500]
                    for s, e in batch:
                        self.sc.SendScintilla(
                            QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_SEARCH
                        )
                        self.sc.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, s, e - s)
                    from PyQt5.QtWidgets import QApplication

                    QApplication.processEvents()
            else:
                for s, e in matches:
                    self.sc.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_SEARCH)
                    self.sc.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, s, e - s)

            return len(matches)

        except Exception as e:
            print(f"[EditorProxy] 高亮失败: {e}")
            return 0

    def clear_highlights(self):
        """清除所有搜索高亮"""
        try:
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_SEARCH)
            self.sc.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length)
        except Exception:
            pass

    # --------------------------------------------------------
    # 缓冲区 → provider 实时同步（消除"双内容源"）
    # --------------------------------------------------------
    def _schedule_provider_sync(self):
        """编辑后把缓冲区同步到 provider（消除"双内容源"）

        分两档，兼顾一致性与打字流畅度：

        * **小文件（< 256KB）立即同步**：重编码一次全文在这个量级上是
          微秒级开销，立即同步能让 provider 在任何时刻都与屏幕一致 ——
          查找/替换/另存为/插件读到的不会是过期内容。
        * **中大文件走防抖定时器**：连续击键只触发一次，避免每次按键都
          重编码整篇文本拖慢输入。
        * **超大文件（> 8MB）不同步**：这类文件的实时同步会明显卡顿；
          保存时仍会显式同步（`save_file`），因此不会丢数据。

        为什么不做成"只在保存时同步"：那正是原来的缺陷 —— 打字期间存在
        两份内容源，导致查找查不到、全部替换丢编辑（审计用例已复现）。
        """
        try:
            if self._restoring or self._undoing:
                return
            provider = getattr(self.document, "provider", None)
            if provider is None or not getattr(provider, "is_open", False):
                return
            size = getattr(provider, "size", 0) or 0
            if size > self._provider_sync_max_bytes:
                return
            if size <= self._provider_sync_immediate_bytes:
                self._sync_provider_now()
            else:
                self._provider_sync_timer.start()
        except Exception as e:
            logger.debug("同步 provider 失败: %s", e)

    def _sync_provider_now(self):
        """把当前缓冲区内容写入 provider

        这就是"单一内容源"的关键一步：让 provider 反映**屏幕上的内容**，
        而不是上次保存时的快照。
        """
        try:
            if self._restoring or self._undoing:
                return
            provider = getattr(self.document, "provider", None)
            if provider is None or not getattr(provider, "is_open", False):
                return
            text = self.sc.text()
            # 内容未变则跳过（避免无谓的重编码）。
            # 优化（C 阶段）：用上次同步文本的内存缓存比较，省掉
            # provider.read_text() 的整篇解码（每次按键都做，实测占
            # 输入路径可观的固定开销）。
            if getattr(self, "_last_synced_text", None) == text:
                return
            self._sync_content_to_provider(text)
        except Exception as e:
            logger.debug("同步 provider 失败: %s", e)

    def _buffer_find_all(self, options) -> list:
        """在**编辑器缓冲区**里查找全部匹配（返回 [(start, end), ...]）

        为什么必须查缓冲区（真实缺陷，审计用例已复现）：
            `search_next` / `highlight_all` / 搜索栏原先都查
            `document.provider`，而 provider 只在**保存时**才与编辑器同步
            （`_sync_content_to_provider`）。于是用户刚输入的文字查不到 ——
            实测插入 "needle" 后 `search_next("needle")` 返回 False，
            而屏幕上明明有。更糟的是"全部替换"会在 provider 快照上替换、
            再用快照覆盖编辑器，**未保存的编辑被静默丢弃**。

            Scintilla 的 target 搜索天然作用于缓冲区，因此这里以
            `sc.text()` 为唯一内容源做匹配，坐标即缓冲区字节偏移，
            可直接用于选中/替换。

        用 Python `re` 而非 Scintilla 内建搜索：需要支持正则、整词、
        大小写等选项，且要一次拿到全部匹配（便于 next/prev 与替换）。
        """
        try:
            text_bytes = self.sc.text().encode("utf-8")
        except Exception:
            return []

        pattern = (
            options.build_pattern()
            if hasattr(options, "build_pattern")
            else (options.pattern or "")
        )
        if not pattern:
            return []

        flags = 0
        if hasattr(options, "to_regex_flags"):
            flags = options.to_regex_flags()
        elif not getattr(options, "case_sensitive", False):
            flags = re.IGNORECASE

        # 关键（易错点）：我们要在**字节**上匹配（Scintilla 的坐标是字节
        # 偏移），而 `re` **不允许**用 str 模式去匹配 bytes 对象 ——
        # 会抛 `TypeError: cannot use a string pattern on a bytes-like
        # object`。因此模式也必须编译成字节模式（re.ASCII 保证
        # `\b`、`\w` 等按 ASCII 语义解释，与字节偏移一致）。
        try:
            rx = re.compile(pattern.encode("utf-8"), flags | re.ASCII)
        except re.error as e:
            # 正则非法 → 退化为字面量搜索（用户多半只是想搜这串字符）
            try:
                rx = re.compile(
                    re.escape(options.pattern).encode("utf-8"),
                    flags | re.ASCII,
                )
            except re.error:
                logger.debug("搜索正则无效: %s", e)
                return []

        spans = []
        limit = getattr(options, "max_results", 1000000) or 1000000
        try:
            for m in rx.finditer(text_bytes):
                if m.end() == m.start():
                    continue  # 跳过零宽匹配，避免死循环
                spans.append((m.start(), m.end()))
                if len(spans) >= limit:
                    break
        except Exception as e:
            logger.debug("缓冲区匹配失败: %s", e)
        return spans

    def search_in_buffer(
        self,
        pattern: str,
        forward: bool = True,
        case_sensitive: bool = False,
        is_regex: bool = False,
        whole_word: bool = False,
    ) -> bool:
        """在编辑器缓冲区中查找并选中下一个/上一个匹配

        返回是否命中。这是"编辑器内查找"的正确实现（见
        `_buffer_find_all` 的说明）。
        """
        try:
            options = SearchOptions(
                pattern=pattern,
                is_regex=is_regex,
                case_sensitive=case_sensitive,
                whole_word=whole_word,
            )
            spans = self._buffer_find_all(options)
            if not spans:
                return False

            pos = self.get_current_pos()
            # 从光标处向后/向前找；超出则循环回另一端
            if forward:
                span = next((s for s in spans if s[0] > pos), None)
                if span is None:
                    span = spans[0]
            else:
                span = next((s for s in reversed(spans) if s[1] <= pos), None)
                if span is None:
                    span = spans[-1]

            self.set_selection(span[0], span[1])
            return True
        except Exception as e:
            logger.error("[EditorProxy] 缓冲区查找失败: %s", e)
            return False

    def replace_all_in_buffer(
        self,
        pattern: str,
        replacement: str,
        case_sensitive: bool = False,
        is_regex: bool = False,
        whole_word: bool = False,
    ) -> int:
        """在编辑器缓冲区里"全部替换"（返回替换次数）

        修复（审计用例 `test_replace_all_reverts_editor_to_provider_snapshot`）：
            原先的"全部替换"在 provider 快照上替换，再用
            `sc.setText(provider.read_text())` 覆盖编辑器 ——
            provider 不含未保存的编辑，于是这些编辑被**静默丢弃**。

            现在直接在缓冲区上替换（从后往前，避免偏移失效），
            未保存的编辑因此得以保留。
        """
        try:
            options = SearchOptions(
                pattern=pattern,
                is_regex=is_regex,
                case_sensitive=case_sensitive,
                whole_word=whole_word,
            )
            spans = self._buffer_find_all(options)
            if not spans:
                return 0

            # 从后往前替换，前面的偏移不受影响
            count = 0
            for start, end in reversed(spans):
                try:
                    old = bytes(self.sc.text().encode("utf-8")[start:end])
                except Exception:
                    old = b""
                if is_regex:
                    try:
                        rx = re.compile(
                            options.build_pattern(),
                            options.to_regex_flags(),
                        )
                        # 用字节切片重算，保证正则替换语义正确
                        seg = bytes(self.sc.text().encode("utf-8")[start:end])
                        new = rx.sub(replacement, seg.decode("utf-8", "replace")).encode("utf-8")
                    except Exception:
                        new = replacement.encode("utf-8")
                else:
                    new = replacement.encode("utf-8")
                try:
                    self._buffer_replace_range(start, end, new)
                    count += 1
                except Exception as e:
                    logger.debug("替换区间失败: %s", e)
            if count:
                self._modified = True
                self.modified_changed.emit(True)
            return count
        except Exception as e:
            logger.error("[EditorProxy] 缓冲区替换失败: %s", e)
            return 0

    def _buffer_replace_range(self, start: int, end: int, data: bytes):
        """用 Scintilla target 机制替换缓冲区的一段字节"""
        sc = self.sc
        sc.SendScintilla(QsciScintilla.SCI_SETTARGETSTART, start)
        sc.SendScintilla(QsciScintilla.SCI_SETTARGETEND, end)
        sc.SendScintilla(QsciScintilla.SCI_REPLACETARGETRE, len(data), data)

    def search_next(self, pattern: str, forward: bool = True) -> bool:
        """搜索下一个匹配（走编辑器缓冲区）

        修复：原实现查 `document.provider` 快照，刚输入的文字查不到。
        """
        try:
            return self.search_in_buffer(pattern, forward=forward)
        except Exception as e:
            print(f"[EditorProxy] 搜索失败: {e}")
            return False

    # ========================================================
    # 智能单词高亮
    # ========================================================
    def _do_smart_highlight(self):
        """执行智能单词高亮（防抖后触发）"""
        try:
            # P8: 统一走 Preferences
            prefs = self._prefs()
            if prefs is not None and not prefs.get("smart_highlight", True):
                return

            # 清除旧高亮
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_SMART_HIGHLIGHT)
            self.sc.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length)

            # 获取当前单词
            pos = self.get_current_pos()
            start = self.sc.SendScintilla(QsciScintilla.SCI_WORDSTARTPOSITION, pos, True)
            end = self.sc.SendScintilla(QsciScintilla.SCI_WORDENDPOSITION, pos, True)

            if start >= end:
                return

            word = self.sc.text()[start:end]

            # 单词太短不处理
            if len(word) < 3:
                return

            # 查找所有出现位置
            target = word.encode("utf-8")
            search_pos = 0
            max_pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)

            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSEARCHFLAGS,
                QsciScintilla.SCFIND_MATCHCASE | QsciScintilla.SCFIND_WHOLEWORD,
            )

            while search_pos < max_pos:
                self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETSTART, search_pos)
                self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETEND, max_pos)
                found = self.sc.SendScintilla(QsciScintilla.SCI_SEARCHINTARGET, len(target), target)
                if found < 0:
                    break

                self.sc.SendScintilla(
                    QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_SMART_HIGHLIGHT
                )
                self.sc.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, found, end - start)

                search_pos = found + 1

        except Exception as e:
            print(f"[EditorProxy] 智能高亮失败: {e}")

    # ========================================================
    # 光标拖尾
    # ========================================================
    def _update_cursor_trail(self):
        """更新光标拖尾效果"""
        try:
            # P8: 统一走 Preferences
            prefs = self._prefs()
            if prefs is not None and not prefs.get("cursor_trail", False):
                return

            pos = self.get_current_pos()
            now = time.time()
            self._cursor_trail.append((pos, now))

            # 清除旧拖尾
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_CURSOR_TRAIL)
            self.sc.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length)

            # 绘制当前拖尾
            valid = []
            for p, t in self._cursor_trail:
                if now - t < CURSOR_TRAIL_DURATION:
                    self.sc.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, p, 1)
                    valid.append((p, t))
            self._cursor_trail = valid

        except Exception:
            pass
