# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""文本变换职责（v2.24 拆出）。"""
from core.editor_common import *  # noqa: F401,F403,F405


class EditorTextOpsMixin:
    def expand_snippet(self, trigger: str) -> bool:
        """
        展开代码片段。

        参数:
            trigger: 触发词（如 "if" / "for"）

        返回:
            是否成功
        """
        snippet = self.SNIPPETS.get(trigger)
        if not snippet:
            return False

        try:
            # 替换内置变量
            snippet = self._replace_snippet_vars(snippet)

            # 选中当前词并替换
            self.sc.selectCurrentWord()
            self.sc.removeSelectedText()
            self.sc.insert(snippet)

            # 高亮第一个占位符
            self._highlight_first_placeholder(snippet)

            return True

        except Exception as e:
            print(f"[EditorProxy] 展开片段失败: {e}")
            return False

    def _replace_snippet_vars(self, snippet: str) -> str:
        """替换片段中的内置变量"""
        now = datetime.datetime.now()

        # 从偏好获取作者（P8: 统一走 Preferences；author_name 不在
        # DEFAULTS 里，缺失时用 "anonymous"）
        prefs = self._prefs()
        if prefs is not None:
            author = prefs.get("author_name", "anonymous")
        else:
            author = "anonymous"

        replacements = {
            "$TM_FILENAME": (
                os.path.basename(self.document.filepath) if self.document.filepath else ""
            ),
            "$TM_FILENAME_BASE": (
                os.path.splitext(os.path.basename(self.document.filepath))[0]
                if self.document.filepath
                else ""
            ),
            "$TM_DIRECTORY": (
                os.path.dirname(self.document.filepath) if self.document.filepath else ""
            ),
            "$CURRENT_YEAR": str(now.year),
            "$CURRENT_MONTH": str(now.month).zfill(2),
            "$CURRENT_DAY": str(now.day).zfill(2),
            "$CURRENT_DATE": now.strftime("%Y-%m-%d"),
            "$CURRENT_TIME": now.strftime("%H:%M:%S"),
            "$CURRENT_DATETIME": now.strftime("%Y-%m-%d %H:%M:%S"),
            "$TM_AUTHOR": author,
        }

        for var, value in replacements.items():
            snippet = snippet.replace(var, value)

        return snippet

    def _highlight_first_placeholder(self, snippet: str):
        """高亮第一个占位符 ${1:...}"""
        try:
            match = re.search(r"\$\{1:([^}]*)\}", snippet)
            if not match:
                return

            # 计算位置
            insert_pos = self.get_current_pos() - len(snippet)
            start = insert_pos + match.start()
            end = start + (match.end() - match.start())

            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART, start)
            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, end)

        except Exception:
            pass

    # ========================================================
    # 特殊插入
    # ========================================================

    def insert_datetime(self):
        """插入当前日期时间。

        P7/P8 接线：格式来自 Preferences 的 ``date_format`` /
        ``time_format``（原先硬编码 ``"%Y-%m-%d %H:%M:%S"``，
        用户在首选项里改了这一项也没有任何效果）。
        """
        try:
            prefs = self._prefs()
            date_fmt = time_fmt = None
            if prefs is not None:
                date_fmt = prefs.get("date_format", None)
                time_fmt = prefs.get("time_format", None)
            fmt = resolve_datetime_format(date_fmt, time_fmt)
            ts = datetime.datetime.now().strftime(fmt)
            pos = self.get_current_pos()
            self.sc.SendScintilla(QsciScintilla.SCI_INSERTTEXT, pos, ts.encode("utf-8"))
        except Exception as e:
            print(f"[EditorProxy] 插入日期时间失败: {e}")

    def eval_expression(self) -> bool:
        """
        计算选中文本的数学表达式并替换结果。

        返回:
            是否成功
        """
        try:
            expr = self.sc.selectedText()
            if not expr:
                return False

            # 安全限制：仅允许数字、运算符、括号、空格
            if not re.match(r"^[\d\s\+\-\*\/\(\)\.\^\%]+$", expr):
                return False

            # 计算
            result = eval(expr, {"__builtins__": {}})

            if isinstance(result, (int, float)):
                # 格式化结果
                if isinstance(result, float):
                    if result.is_integer():
                        result_str = str(int(result))
                    else:
                        result_str = f"{result:.6g}"
                else:
                    result_str = str(result)

                self.sc.replaceSelectedText(result_str)
                return True

        except Exception as e:
            print(f"[EditorProxy] 计算表达式失败: {e}")

        return False

    # ========================================================
    # 大小写转换
    # ========================================================

    def to_upper(self):
        """选中文本转大写"""
        text = self.sc.selectedText()
        if text:
            self.sc.replaceSelectedText(text.upper())

    def to_lower(self):
        """选中文本转小写"""
        text = self.sc.selectedText()
        if text:
            self.sc.replaceSelectedText(text.lower())

    def toggle_case(self):
        """选中文本大小写切换"""
        text = self.sc.selectedText()
        if text:
            self.sc.replaceSelectedText(text.swapcase())

    # ========================================================
    # 行尾空白清理
    # ========================================================

    def trim_trailing_whitespace(self):
        """清除所有行的行尾空白"""
        try:
            text = self.sc.text()
            lines = [l.rstrip() for l in text.splitlines()]
            new_text = "\n".join(lines)

            if new_text != text:
                self.set_text(new_text)

        except Exception as e:
            print(f"[EditorProxy] 清除行尾空白失败: {e}")

    def remove_blank_lines(self):
        """删除所有空行"""
        try:
            text = self.sc.text()
            lines = [l for l in text.splitlines() if l.strip()]
            new_text = "\n".join(lines)

            if new_text != text:
                self.set_text(new_text)

        except Exception as e:
            print(f"[EditorProxy] 删除空行失败: {e}")

    # ========================================================
    # LSP 集成
    # ========================================================
