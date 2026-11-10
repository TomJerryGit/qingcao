# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""词法/大文档高亮职责（v2.24 拆出）。"""

from ui.editor_view_common import *  # noqa: F401,F403,F405


class EditorLexerMixin:
    def set_lexer_by_filename(self, filepath: Optional[str]):
        """
        根据文件扩展名设置词法器。

        优先级（高 -> 低），与模块级 LEXER_BY_EXTENSION 的注释一致：
            1. 主窗口 _custom_lexers 插件注册表（插件注册的优先）
            2. .log -> core.log_lexer.LogLexer（专用词法器）
            3. 内置扩展名映射表（LEXER_BY_EXTENSION）
            4. 无匹配 / 本构建缺该词法器 -> setLexer(None)（零高亮，不报错）

        说明：core/editor.py 中另有一份历史副本，**本处为权威实现**。

        参数:
            filepath: 文件路径（None / 空字符串表示清除词法器）
        """
        if not filepath:
            self.set_lexer(None)
            return

        ext = os.path.splitext(filepath)[1].lower()

        # ---- 大文档模式：跳过语法高亮（性能，见 LARGE_DOC_LINES 注释）----
        if self.is_large_document() and not self._large_doc_highlight_override():
            self._large_doc_mode = True
            self._last_lexer_filepath = filepath
            self.set_lexer(None)
            self._apply_large_doc_tooltip(filepath)
            return

        # ---- 去重：同一文件不必重复对整个文档重做样式 ----
        # 实测一次 open 会走到这里 2 次（打开 + 标签切换），
        # 每次 setLexer 对 50 万行文档约 0.68s。
        #
        # 去重键必须带上"自定义词法器工厂身份"：插件可能在运行期
        # 注册/替换/移除某个扩展名的词法器，此时同一路径也要重新应用
        # （否则 test_custom_lexer_registry_has_higher_priority 会失败）。
        try:
            custom = getattr(self.window(), "_custom_lexers", None)
            factory = custom.get(ext) if isinstance(custom, dict) else None
        except Exception:
            factory = None
        _key = (filepath, id(factory) if factory is not None else None)
        if self._last_lexer_filepath == _key and self.lexer() is not None:
            return
        self._last_lexer_filepath = _key
        self._large_doc_mode = False

        # 1) 插件注册的自定义词法器优先
        #    app/plugins.py 会往主窗口的 _custom_lexers 里按扩展名
        #    注册工厂函数；此处对所有扩展名都先查注册表。
        try:
            if factory is not None:
                lexer = factory()
                if lexer is not None:
                    self.set_lexer(lexer)
                    return
        except Exception as e:
            print(f"[EditorWidget] 自定义词法器创建失败({ext}): {e}")

        # 2) .log 专用词法器
        if ext == ".log":
            try:
                from core.log_lexer import LogLexer

                self.set_lexer(LogLexer(self))
            except Exception as e:
                print(f"[EditorWidget] 日志词法器加载失败: {e}")
                self.set_lexer(None)
            return

        # 3) 内置映射表；缺词法器时 create_lexer_for_extension 返回 None，
        #    由 set_lexer(None) 完成"零高亮"降级。
        try:
            self.set_lexer(create_lexer_for_extension(ext, self))
        except Exception as e:
            print(f"[EditorWidget] 设置词法器失败({ext}): {e}")
            self.set_lexer(None)

    def is_large_document(self) -> bool:
        """是否为"大文档"（行数或字节数超过阈值）

        阈值与实测依据见 `LARGE_DOC_LINES` / `LARGE_DOC_BYTES` 上方注释。
        `lines()` / `length()` 都是 QScintilla 的廉价查询，不会遍历全文。
        """
        try:
            if self.lines() > LARGE_DOC_LINES:
                return True
            return self.length() > LARGE_DOC_BYTES
        except Exception:
            return False

    def _large_doc_highlight_override(self) -> bool:
        """用户是否强制给大文件开启高亮（「视图」菜单里的开关）"""
        try:
            return bool(getattr(self.window(), "_force_highlight_large_files", False))
        except Exception:
            return False

    def _apply_large_doc_tooltip(self, filepath: str) -> None:
        """在大文档上给出可见提示（避免用户以为高亮坏了）"""
        try:
            self.setToolTip(
                "大文件模式：已关闭语法高亮 / 缩略图渲染。\n"
                "编辑、查找、保存均不受影响。\n"
                "可在「视图 → 大文件强制高亮」中开启。\n" + filepath
            )
        except Exception:
            pass

    def set_lexer(self, lexer):
        """重写，同时设置字体（并保证词法器生命周期）

        生命周期说明（P5 实测发现）：
            没有 QObject parent 的词法器在 Python 侧唯一的引用消失后
            会被回收，而 Scintilla 只持有**裸指针**，于是
            `self.lexer()` 变成 None（插件工厂返回的词法器正是这种）。
            这里对无 parent 的词法器统一 `setParent(self)`，
            让编辑器持有它 —— 内置路径虽然已经传了 parent，
            插件/外部传入的路径也一并兜住。
        """
        if lexer is not None:
            try:
                if lexer.parent() is None:
                    lexer.setParent(self)
            except Exception:
                pass

        super().setLexer(lexer)
        if lexer:
            try:
                lexer.setDefaultFont(self.font())
            except Exception:
                pass

    # ========================================================
    # 按键处理
    # ========================================================
