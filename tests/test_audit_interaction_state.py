# -*- coding: utf-8 -*-
"""
交互审计：标签页 / 文件保存 × 编辑器状态一致性
============================================

覆盖的交互：
    1. 编辑 × 保存（另存为）      —— 编辑器缓冲区从不回写 Document.provider
    2. 编辑 × 查找/替换            —— 编辑器内查找走 provider（过期内容）
    3. 后台标签内存回收 × 保存全部 —— 释放内容被误判为"已修改"，保存会清空文件
    4. 外部文件变更 × 撤销         —— 重新加载后撤销栈未清理

核心根因（静态定位）：
    EditorProxy._on_scintilla_modified  (core/editor.py:645-739) 只记录
    撤销命令，从不把 sc 的内容写回 self.document.provider；
    唯一同步点是 EditorProxy.save_file (core/editor.py:461-526)。
    于是"Scintilla 缓冲区"与"Document.provider"是两个不同步的内容源。

断言不变式：
    INV-A  Document.provider 的内容必须与编辑器可见内容一致，
           或至少在任何读取 provider 之前被同步。
    INV-B  保存（含另存为）写入磁盘的字节必须来自编辑器当前内容。
    INV-C  只有用户编辑才能让 proxy.is_modified 变为 True。
    INV-D  文件重新加载后，撤销栈必须与新的内容基线一致。

运行方式：
    python -m pytest tests/test_audit_interaction_state.py -v
"""

import os

import pytest


# ============================================================
# 0. 根因：编辑器缓冲区与 provider 双内容源
# ============================================================
class TestContentSourceDuplication:

    @pytest.mark.audit_expected_fail
    def test_provider_is_not_updated_while_typing(self, qapp, tmp_path):
        """打字后 provider 仍停留在打开时的快照（INV-A）。"""
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        p = tmp_path / "a.py"
        p.write_text("print(1)\n", encoding="utf-8")

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())
        assert proxy.open_file(str(p)) is True

        sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()),
                         b"print(2)\n")

        provider_text = proxy.document.provider.read_text()
        assert provider_text == sc.text(), (
            "INV-A 违反：编辑器内容与 Document.provider 不一致。"
            f" 编辑器={sc.text()!r} provider={provider_text!r}；"
            "任何基于 provider 的功能（查找/替换/另存为/全局替换）"
            "都会看到过期内容。"
        )


# ============================================================
# 1. 另存为：写入磁盘的是过期内容，且脏标记不清
# ============================================================
class TestSaveAs:

    @pytest.mark.skip(reason=(
        "已过时（P0-B 已修复）：本用例断言 `proxy.document.save(path)` "
        "应写入编辑器内容，但 Document 只持有 provider、**拿不到 "
        "QScintilla 文本** —— 唯一能同步内容的是 "
        "`EditorProxy.save_file()`。原缺陷是 UI 调用了错误的入口，"
        "现已把生产代码里所有 `document.save()` 调用改为 "
        "`save_file(path)`（生产代码中仅剩 save_file 内部一处正确调用）。"
        "把 Document 也做对在架构上不可能。"
        "等价且更可靠的不变量由 tests/test_wiring_audit.py 的 "
        "test_no_ui_bypasses_content_sync 守住。"
    ))
    @pytest.mark.audit_expected_fail
    def test_save_as_writes_stale_content(self, qapp, tmp_path):
        """ui/mixins/file_ops_mixin.py:230 的
        `proxy.document.save(path)` 只走 Document，不经过
        EditorProxy.save_file 的 _sync_content_to_provider，
        因此写盘的是 provider 里的旧内容（INV-B）。
        """
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        src = tmp_path / "src.py"
        src.write_text("print(1)\n", encoding="utf-8")

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())
        assert proxy.open_file(str(src)) is True

        # 用户输入新内容（未保存）
        sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()),
                         b"print(2)\n")
        assert "print(2)" in sc.text()

        # 复现 _save_file_as 的调用
        dst = tmp_path / "dst.py"
        assert proxy.document.save(str(dst)) is True

        written = dst.read_text(encoding="utf-8")
        assert "print(2)" in written, (
            "INV-B 违反：另存为丢失了未保存的编辑。"
            f" 另存为写入={written!r}，编辑器内容={sc.text()!r}"
        )

    @pytest.mark.skip(reason=(
        "已过时（P0-B 已修复）：同上 —— 断言 `document.save()` 应清除 "
        "Scintilla 的脏标记，但 Document 不持有编辑器控件。"
        "`EditorProxy.save_file()` 已经会 `sc.setModified(False)`，"
        "UI 层现已统一走该入口。"
    ))
    @pytest.mark.audit_expected_fail
    def test_save_as_does_not_clear_modified_flag(self, qapp, tmp_path):
        """另存为成功后 * 标记仍存在（Scintilla 侧未 setModified(False)）。"""
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        src = tmp_path / "src.py"
        src.write_text("print(1)\n", encoding="utf-8")

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())
        assert proxy.open_file(str(src)) is True
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"# c\n")
        assert proxy.is_modified is True

        dst = tmp_path / "dst.py"
        proxy.document.save(str(dst))

        assert proxy.is_modified is False, (
            "另存为之后 proxy.is_modified 仍为 True -> 标签页继续显示 '*'，"
            "并且 save_autosave 会为已保存文件生成备份。"
            f" document.is_modified={proxy.document.is_modified}"
        )


# ============================================================
# 2. 编辑器内查找/替换 × 过期 provider
# ============================================================
class TestSearchAgainstStaleProvider:

    @pytest.mark.audit_expected_fail
    def test_search_next_cannot_find_freshly_typed_text(
            self, qapp, tmp_path):
        """EditorProxy.search_next / highlight_all / SearchBar._search
        全都查 document.provider（core/editor.py:1446,1504；
        ui/panels.py:443），所以刚输入的文字查不到。
        """
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        p = tmp_path / "s.py"
        p.write_text("alpha\n", encoding="utf-8")

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())
        assert proxy.open_file(str(p)) is True

        sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()), b"needle\n")
        assert "needle" in sc.text()

        found = proxy.search_next("needle")
        assert found is True, (
            "编辑器内查找无法命中刚刚输入的文字（查的是 provider 快照）。"
            f" 编辑器={sc.text()!r} provider="
            f"{proxy.document.provider.read_text()!r}"
        )

    @pytest.mark.audit_expected_fail
    def test_replace_all_reverts_editor_to_provider_snapshot(
            self, qapp, tmp_path):
        """ui/panels.py:640-653 的"全部替换"先在 provider 上替换，
        再用 `proxy.sc.setText(provider.read_text())` 覆盖编辑器，
        因此未保存的编辑会被丢弃。
        """
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy
        from core.search import ReplaceEngine, SearchEngine, SearchOptions

        p = tmp_path / "r.py"
        p.write_text("foo foo\n", encoding="utf-8")

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())
        assert proxy.open_file(str(p)) is True

        # 用户未保存的编辑
        sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()), b"MY EDIT\n")
        assert "MY EDIT" in sc.text()

        # 复现 SearchBar._on_replace_all 的核心三步
        provider = proxy.document.provider
        options = SearchOptions(pattern="foo")
        result = SearchEngine(provider, options).search()
        ReplaceEngine(provider).replace_all(result, "bar", pattern="foo")
        proxy.sc.setText(provider.read_text())     # ui/panels.py:652

        assert "MY EDIT" in sc.text(), (
            "全部替换把编辑器内容重置为 provider 快照，未保存的编辑丢失。"
            f" 替换后编辑器={sc.text()!r}"
        )


# ============================================================
# 3. 后台标签内存回收 × 保存
# ============================================================
class TestIdleReleaseVsSave:
    """app/tabs.py:1490-1528 的 _release_tab_content 直接调用 widget.clear()，
    未设置 proxy._restoring / _undoing，于是 SCN_MODIFIED 被当成"用户编辑"
    记录进撤销栈并把 proxy 标记为已修改。

    两个后果拆成两条独立测试，避免第一条断言失败后掩盖第二条。
    """

    @staticmethod
    def _make_tabs(tmp_path, name, filler="x"):
        from app.tabs import TabManager

        p = tmp_path / name
        original = filler * 2000 + "\n"
        # 关键：必须用 newline="" 写入。
        #
        # 在 Windows 上，`Path.write_text()` 默认走通用换行转换，会把
        # `"\n"` 改写成磁盘上的 `"\r\n"` —— 于是本文件里的 `original`
        # 变量（`\n`）与磁盘实际内容（`\r\n`）**不一致**，
        # 后续 `assert cached == original` 必然失败，而这个失败与
        # 被测逻辑无关（是测试自己的平台差异）。
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(original)
        tabs = TabManager()
        tabs._idle_timer.stop()          # 测试里手动触发，避免定时器干扰
        return tabs, p, original

    @pytest.mark.audit_expected_fail
    def test_release_does_not_mark_tab_modified(self, qapp, tmp_path):
        """INV-C：只有用户编辑才能让 proxy.is_modified 变 True。"""
        tabs, p, _ = self._make_tabs(tmp_path, "big.txt")
        proxy = tabs.open_file(str(p))
        assert proxy is not None, "前置条件：文件应能打开"
        widget = tabs.widget(0)
        assert widget is not None, "前置条件：应有编辑器控件"
        assert proxy.is_modified is False, "前置条件：刚打开应为干净状态"

        tabs._release_tab_content(widget)          # 等价于闲置 30 分钟
        assert widget.text() == "", "前置条件：内容应已被释放"

        assert proxy.is_modified is False, (
            "INV-C 违反：内存回收（非用户操作）把标签标记为已修改，"
            "标签标题会出现 '*'，退出时会被提示保存。"
            f" undo_stack={len(proxy.undo_manager.undo_stack)}"
        )

    @pytest.mark.audit_expected_fail
    def test_save_all_after_release_does_not_truncate_file(
            self, qapp, tmp_path):
        """INV-B：保存写盘的字节必须来自用户的真实内容，
        绝不能因为内存回收而把文件清空。

        用例自身的修正说明：
            原版断言 `saved >= 1`，理由是"释放动作把标签标记为已修改，
            save_all 才会处理它" —— 这与**上一条用例**
            （`test_release_does_not_mark_tab_modified` 要求释放后
            `is_modified` 必须为 False）**直接矛盾**：两者不可能同时成立。

            正确的语义是：内存回收**不是用户编辑**，因此
                * 不该把标签标记为已修改（上一条用例）；
                * `save_all()` 因此**不应该**处理它（返回 0 是正确行为）；
                * 但文件内容必须**原封不动**（本用例真正要守的不变量）。

            因此这里去掉对 saved 计数的错误假设，改为断言真正重要的
            两件事：文件未被破坏、且释放的内容仍在内存缓存里
            （可被切回标签时恢复，不会丢）。
        """
        tabs, p, original = self._make_tabs(tmp_path, "big2.txt")
        proxy = tabs.open_file(str(p))
        assert proxy is not None
        widget = tabs.widget(0)

        tabs._release_tab_content(widget)
        assert widget in tabs._released_content, (
            "前置条件：释放的内容应被缓存，以便切回时恢复"
        )

        tabs.save_all()

        after = p.read_text(encoding="utf-8")
        assert after == original, (
            "INV-B 违反：保存全部把文件内容清空/破坏。"
            f" 原长度={len(original)} 保存后长度={len(after)}"
        )
        # 释放只是内存优化，内容必须仍在缓存中、可恢复
        assert tabs._released_content[widget] == original, (
            "释放缓存的内容与磁盘不一致 —— 切回标签会看到错误内容"
        )

    @pytest.mark.audit_expected_fail
    def test_restore_after_release_keeps_clean_state(self, qapp, tmp_path):
        """释放后切回该标签，内容被 setText 恢复，但同样会被标记为已修改。"""
        tabs, p, _ = self._make_tabs(tmp_path, "big3.txt", filler="y")
        proxy = tabs.open_file(str(p))
        widget = tabs.widget(0)

        tabs._release_tab_content(widget)
        assert widget in tabs._released_content

        # 走**生产路径**恢复内容。
        #
        # 原版直接 `widget.setText(tabs._released_content.pop(widget))`
        # 模拟 app/tabs.py 的恢复逻辑 —— 但那是"照着有缺陷的写法抄一遍"，
        # 并没有测到真正的恢复代码。这里改为调用 TabManager 自己的恢复
        # 方法，这样断言才反映用户在"切回标签"时真实发生的事。
        tabs._restore_released_content(widget)
        assert widget.text().startswith("y" * 100)

        assert proxy.is_modified is False, (
            "内容恢复后仍被标记为已修改（恢复动作本身被当成用户编辑）。"
        )


# ============================================================
# 4. 外部文件变更 × 撤销
# ============================================================
class TestExternalChangeVsUndo:

    @pytest.mark.audit_expected_fail
    def test_reload_does_not_reset_undo_stack(self, qapp, tmp_path):
        """app/tabs.py:1399-1458 _reload_file 只重置 modified 标记，
        不清理 undo_manager；旧的撤销命令位置相对新内容全部失效（INV-D）。
        """
        from app.tabs import TabManager

        p = tmp_path / "ext.txt"
        # 用 newline="" 写入：Windows 上 Path.write_text() 默认会把 "\n"
        # 改写成磁盘上的 "\r\n"，使断言中的期望值与实际内容不一致
        # （这是测试自身的平台差异，与被测逻辑无关）。
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("AAAA\nBBBB\n")

        tabs = TabManager()
        tabs._idle_timer.stop()
        proxy = tabs.open_file(str(p))
        widget = tabs.widget(0)
        sc = proxy.sc

        # 用户做两次编辑 -> 撤销栈有内容
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"ZZ")
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"YY")
        assert len(proxy.undo_manager.undo_stack) >= 1

        # 外部程序把文件改成完全不同的内容
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("totally different\n")

        # 用户确认重新加载
        tabs._reload_file(str(p), widget)
        assert sc.text() == "totally different\n"

        stack_desc = [c.describe() for c in proxy.undo_manager.undo_stack]
        assert len(proxy.undo_manager.undo_stack) == 0, (
            "INV-D 违反：外部变更重新加载后撤销栈未清空，"
            "栈内命令的位置针对旧内容，Ctrl+Z 会破坏文件内容。"
            f" undo_stack={stack_desc}"
        )

    @pytest.mark.audit_expected_fail
    def test_reload_leaks_previous_provider(self, qapp, tmp_path):
        """_reload_file 用新 provider 替换 document.provider，
        却不 close() 旧的 provider（mmap/文件句柄泄漏，
        Windows 上会锁住文件导致外部写入失败）。"""
        from app.tabs import TabManager

        p = tmp_path / "leak.txt"
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("hello\n")

        tabs = TabManager()
        tabs._idle_timer.stop()
        proxy = tabs.open_file(str(p))
        widget = tabs.widget(0)
        old_provider = proxy.document.provider

        tabs._reload_file(str(p), widget)

        assert proxy.document.provider is not old_provider, (
            "前置条件：provider 应被替换"
        )
        assert getattr(old_provider, "_mmap", None) is None, (
            "旧 provider 的 mmap 未释放（文件句柄泄漏）。"
        )
        assert getattr(old_provider, "_file", None) is None, (
            "旧 provider 的文件句柄未关闭。"
        )


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
