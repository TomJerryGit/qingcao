#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P0-1 / P0-2 / P0-3 缺陷修复验证脚本（供 Lead 运行）

覆盖的缺陷:
    P0-1 宏录制录到 0 条
         `ui/main_window.py` 构造 `MacroRecorder()` 时没有 undo_manager，
         `core/macro.py::_register_hook` 早退 → record_hook 永不设置。
         修复：`MacroRecorder(undo_manager_provider=...)` + start/stop 动态绑定
         当前标签的 undo_manager（proxy 是每标签一个）。

    P0-2 草稿只写不读
         `core/document.py` 每 60s 写 backup/drafts/*.draft，
         但 `SessionManager.check_and_recover_drafts()` 全仓零调用点。
         修复：`main.py::deferred_init` 调用它（并补渲染 + 可见提示）。

    P0-3 全局替换静默丢选项
         `MainWindow._on_global_replace` 用 `SearchOptions(pattern=pattern)`
         默认值重建选项，无视面板勾选 → 正则搜索按字面量替换。
         修复：面板 `build_options()` 是唯一构造点，选项随
         `replace_requested` 信号（第 4 个参数）传给替换端。

    P0-8 字符数口径（顺手修，非三个 P0 之一）
         `SCI_GETLENGTH` 是字节数却被标成"字符数"（中文差 3 倍）。

用法（在仓库根目录执行）::

    cd D:\\QingCaoEditor
    python tools/verify_p0_defects.py

    无显示器 / CI 环境（脚本默认也会设 offscreen）::

    set QT_QPA_PLATFORM=offscreen && python tools/verify_p0_defects.py

退出码:
    0 = 全部通过（SKIP 不算失败）
    1 = 存在 FAIL

说明:
    * 脚本**不改任何业务代码**，只在临时目录里造文件、造草稿；
    * `DocumentModel._draft_dir` 会被临时 monkeypatch 到临时目录，
      结束时恢复，不会污染真实的 backup/drafts；
    * 不弹任何对话框（`check_and_recover_drafts(parent=None)`）。
"""

import ast
import io
import os
import re as _re_mod
import shutil
import sys
import tempfile
import tokenize
import traceback
import types


# ------------------------------------------------------------
# 让 offscreen 生效（必须在创建 QApplication 之前设置）
# ------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

STATIC_CHECKS = []   # [(name, fn)]
QT_CHECKS = []       # [(name, fn)]
RESULTS = []         # [(ok, name, detail)]
SKIPPED = []         # [(name, reason)]


class _SkipCheck(Exception):
    """检查内部抛出：该项记为 SKIP（不算失败）"""


def static_check(name):
    def deco(fn):
        STATIC_CHECKS.append((name, fn))
        return fn
    return deco


def qt_check(name):
    def deco(fn):
        QT_CHECKS.append((name, fn))
        return fn
    return deco


def _run(name, fn):
    try:
        detail = fn()
        RESULTS.append((True, name, detail or ""))
    except _SkipCheck as e:
        SKIPPED.append((name, str(e)))
    except AssertionError as e:
        RESULTS.append((False, name, "断言失败: %s" % e))
    except Exception as e:
        RESULTS.append((
            False, name,
            "%s: %s\n%s" % (type(e).__name__, e, traceback.format_exc())
        ))


def read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def parse(path):
    return ast.parse(read(path))


def find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def strip_comments(src):
    """去掉注释后的 token 串（用于统计"真实可执行"的调用次数）

    返回 None 表示 tokenize 失败（此时调用方不得据原始文本下结论）。
    """
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE):
                continue
            out.append(tok.string)
    except Exception:
        return None
    return " ".join(out)


def _strip_comments_and_docstrings(src):
    """剥掉注释与**字符串字面量**（含 docstring），只留真实代码骨架

    为什么需要（Lead 实测的假阳性）：
        "本方法原先用 `SearchOptions(pattern=pattern)` 重建选项" 这类
        **缺陷说明 docstring** 里会引用旧代码。若直接对源码文本做
        `re.search`，断言会被这段说明文字命中 → 永远失败。

    做法：用 tokenize 过滤掉 COMMENT 与 STRING token（docstring 就是
    函数体的第一个 STRING，因此一并被去掉）。
    """
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL,
                            tokenize.NEWLINE, tokenize.STRING):
                continue
            out.append(tok.string)
    except Exception:
        # tokenize 失败时退化为原串（宁可严格，也不要静默放过）
        return src
    return " ".join(out)


# ============================================================
# 一、静态接线检查（不需要 Qt）
# ============================================================
@static_check("P0-1 静态：main_window 构造 MacroRecorder 时传入 undo_manager_provider")
def _s_macro_kwarg():
    tree = parse("ui/main_window.py")
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "MacroRecorder"):
            found.append([k.arg for k in node.keywords])
    assert found, "未找到 MacroRecorder(...) 构造调用"
    assert any("undo_manager_provider" in kwargs for kwargs in found), \
        "MacroRecorder 调用未传 undo_manager_provider: %r" % (found,)
    return "构造调用 keywords=%r" % (found,)


@static_check("P0-1 静态：main_window 有 _current_undo_manager（解析当前 proxy）")
def _s_macro_resolver():
    tree = parse("ui/main_window.py")
    fn = find_func(tree, "_current_undo_manager")
    assert fn is not None, "MainWindow 未定义 _current_undo_manager"
    src = ast.get_source_segment(read("ui/main_window.py"), fn) or ""
    assert "current_proxy" in src, "未通过 tabs.current_proxy() 取当前标签"
    assert "undo_manager" in src, "未取 proxy.undo_manager"
    return "已定义并引用 current_proxy()/undo_manager"


@static_check("P0-1 静态：_toggle_macro 开始前绑定 + start/stop + has_hook 提示")
def _s_toggle_macro():
    src = read("ui/main_window.py")
    tree = ast.parse(src)
    fn = find_func(tree, "_toggle_macro")
    assert fn is not None, "未找到 _toggle_macro"
    body = ast.get_source_segment(src, fn) or ""
    assert ".start()" in body and ".stop()" in body, "缺少 start()/stop()"
    assert "has_hook" in body, "未根据 has_hook 给出可见提示"
    assert "bind_current_undo_manager" in body, "未在开始前绑定当前管理器"
    return "start/stop + bind_current_undo_manager + has_hook 提示"


@static_check("P0-3 静态：_on_global_replace 接收 options 且不再自建默认 SearchOptions")
def _s_replace_options():
    src = read("ui/main_window.py")
    tree = ast.parse(src)
    fn = find_func(tree, "_on_global_replace")
    assert fn is not None, "未找到 _on_global_replace"
    args = [a.arg for a in fn.args.args]
    assert args[:4] == ["self", "pattern", "replace_text", "file_results"], \
        "参数列表异常: %r" % (args,)
    assert len(args) >= 5 and args[4] == "options", \
        "缺少第 4 个业务参数 options: %r" % (args,)
    body = ast.get_source_segment(src, fn) or ""
    assert "SearchEngine(provider, options)" in body, \
        "重新搜索时未复用 options"
    assert "options.is_regex" in body, "替换时未使用 options.is_regex"
    # ⚠️ 判据修正（Lead 实测）：直接对源码文本做正则会被**注释/docstring
    #   里的旧代码引用**误伤 —— 本方法的 docstring 为了讲清缺陷，写了一句
    #   「本方法原先用 `SearchOptions(pattern=pattern)` 重建选项」，
    #   于是朴素的 search() 恒为真、断言永远失败（假阳性）。
    #   这里先把 docstring 与注释剥掉，只检查**真实代码**。
    code_only = _strip_comments_and_docstrings(body)
    assert not _re_mod.search(r"SearchOptions\(pattern=pattern\)", code_only), \
        "仍在自建 SearchOptions(pattern=pattern)（P0-3 未修）"
    return "签名 args=%r，搜索/替换复用同一 SearchOptions" % (args,)


@static_check("P0-3 静态：replace_requested 信号携带第 4 个参数（SearchOptions）")
def _s_signal_arity():
    tree = parse("ui/global_search_panel.py")
    found = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if getattr(t, "id", "") == "replace_requested":
                    found = node
    assert found is not None, "未找到 replace_requested 赋值"
    call = found.value
    assert isinstance(call, ast.Call), "replace_requested 不是 pyqtSignal(...)"
    n = len(call.args)
    assert n == 4, "replace_requested 参数个数 = %d（应为 4）" % n
    return "pyqtSignal 参数个数 = 4"


@static_check("P0-2 静态：main.py::deferred_init 调用 check_and_recover_drafts")
def _s_draft_wired():
    tree = parse("main.py")
    fn = find_func(tree, "deferred_init")
    assert fn is not None, "未找到 deferred_init"
    calls = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.setdefault(node.func.attr, []).append(node)
    assert "check_and_recover_drafts" in calls, \
        "deferred_init 未调用 check_and_recover_drafts（P0-2 未接线）"
    assert "find_recoverable_drafts" in calls, "未先读取草稿列表"

    call = calls["check_and_recover_drafts"][0]
    kwargs = {k.arg for k in call.keywords}
    assert "parent" in kwargs, \
        "调用未传 parent（应带 parent=window 以弹出可见确认框）: %r" % (kwargs,)
    assert "drafts" in kwargs, \
        "调用未传 drafts（读取端与恢复端必须用同一份列表）: %r" % (kwargs,)
    return "已调用 find_recoverable_drafts + check_and_recover_drafts(parent=..., drafts=...)"


@static_check("P0-2 静态：main.py 定义补渲染 / 可见提示两个模块级函数")
def _s_draft_helpers():
    tree = parse("main.py")
    names = {n.name for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)}
    assert "_render_recovered_drafts" in names, "缺少 _render_recovered_drafts"
    assert "_notify_draft_recovery" in names, "缺少 _notify_draft_recovery"
    return "两个 helper 均在模块级定义"


@static_check("P0-2 静态：deferred_init 调用了补渲染与可见提示")
def _s_draft_helpers_called():
    tree = parse("main.py")
    fn = find_func(tree, "deferred_init")
    body = ast.get_source_segment(read("main.py"), fn) or ""
    assert "_render_recovered_drafts(window)" in body, "未调用补渲染"
    assert "_notify_draft_recovery(" in body, "未调用可见提示"
    return "补渲染 + 提示均已接线"


@static_check("P0-8 静态：app/tabs.py 区分 char_count / byte_count")
def _s_tabs_counts():
    src = read("app/tabs.py")
    assert "info['byte_count'] = widget.SendScintilla" in src, \
        "byte_count 未取 Scintilla 字节长度"
    assert "info['char_count'] = len(widget.text())" in src, \
        "char_count 未使用解码后的字符长度"
    assert "info['char_count'] = widget.SendScintilla" not in src, \
        "char_count 仍直接取字节数"
    return "char_count=len(text()), byte_count=SCI_GETLENGTH"


@static_check("P0-8 静态：ui/perf_monitor.py 不再把 sc.length() 当字符数")
def _s_perf_counts():
    src = read("ui/perf_monitor.py")
    assert "total_chars += w.proxy.sc.length()" not in src, \
        "仍在把字节长度累加为总字符"
    assert "_count_chars" in src, "缺少 _count_chars 辅助函数"
    return "改用 _count_chars(sc)（字符 + 字节双口径）"


# ============================================================
# 二、动态检查（需要 Qt + QScintilla）
# ============================================================
def _import_main_window():
    from ui.main_window import MainWindow
    return MainWindow


_MAIN_MODULE = {"mod": None}


def _import_main():
    """导入 main.py（保存/恢复 sys.excepthook，避免污染验证脚本）"""
    if _MAIN_MODULE["mod"] is not None:
        return _MAIN_MODULE["mod"]
    saved_hook = sys.excepthook
    try:
        import importlib
        mod = importlib.import_module("main")
    finally:
        sys.excepthook = saved_hook
    _MAIN_MODULE["mod"] = mod
    return mod


def _call_global_replace(MainWindow, pattern, repl, file_results, options):
    """调用**真实的** MainWindow._on_global_replace（用最小宿主 self）

    真正的 MainWindow 会创建 LSP / 插件 / 各类面板，这里只需它用到的属性：
    `tabs.count()` 与 `status_bar.showMessage`。方法体本身是生产代码。
    """
    class FakeStatusBar:
        def __init__(self):
            self.messages = []

        def showMessage(self, msg, timeout=0):
            self.messages.append(msg)

    class FakeTabs:
        def count(self):
            return 0

    host = types.SimpleNamespace(
        tabs=FakeTabs(),
        status_bar=FakeStatusBar(),
        gsearch=None,
    )
    MainWindow._on_global_replace(host, pattern, repl, file_results, options)
    return host


@qt_check("P0-1 动态：录制后 len(macro.commands) >= 1，且切标签后录到新标签")
def _d_macro_record():
    from core.commands import InsertCmd
    from core.macro import MacroRecorder

    class FakeUndoManager:
        """等价于 core/undo.py 的 UndoManager#record_hook 机制"""

        def __init__(self, name):
            self.name = name
            self.record_hook = None
            self.seen = []

        def record(self, cmd):
            self.seen.append(cmd)
            if self.record_hook:
                self.record_hook(cmd)

    um1 = FakeUndoManager("tab1")
    um2 = FakeUndoManager("tab2")
    current = {"um": um1}

    # 与 ui/main_window.py 的 MacroRecorder(undo_manager_provider=...) 一致
    rec = MacroRecorder(undo_manager_provider=lambda: current["um"])

    # --- 第一个标签 ---
    rec.start()
    assert rec.has_hook, "start() 后未挂钩（has_hook=False）"
    um1.record(InsertCmd(0, "A"))
    um1.record(InsertCmd(5, "B"))
    n1 = len(rec.current_macro.commands)
    macro1 = rec.stop()
    assert n1 >= 1, "录制后命令数 = %d（要求 >= 1）" % n1
    assert len(macro1.commands) >= 1, "返回的宏为空"
    assert um1.record_hook is None, "stop() 后未在 tab1 上解绑"

    # --- 切换标签后再次录制（必须录到 tab2）---
    current["um"] = um2
    rec.start()
    assert rec.has_hook, "切换标签后 start() 未挂钩"
    um2.record(InsertCmd(0, "C"))
    n2 = len(rec.current_macro.commands)
    rec.stop()
    assert n2 >= 1, "切标签后录制命令数 = %d（要求 >= 1）" % n2
    assert um2.record_hook is None, "stop() 后未在 tab2 上解绑"
    assert um1.record_hook is None, "tab1 上的钩子被串改"

    # --- 没有 undo_manager 时必须"可感知"而不是静默 ---
    errors = []
    rec2 = MacroRecorder(undo_manager_provider=lambda: None)
    rec2.error_occurred.connect(errors.append)
    rec2.start()
    assert errors, "无 undo_manager 时未发出 error_occurred"
    rec2.stop()

    return ("tab1 录到 %d 条、tab2 录到 %d 条；stop 后均解绑；"
            "无编辑器时发出 error_occurred" % (n1, n2))


@qt_check("P0-3 动态：面板 build_options() 遵守勾选 + 信号携带选项对象")
def _d_panel_options():
    from PyQt5.QtWidgets import QMainWindow

    from ui.global_search_panel import GlobalSearchPanel

    host = QMainWindow()
    panel = GlobalSearchPanel(host)
    try:
        panel.pattern_edit.setText("a.c")
        panel.regex_cb.setChecked(True)
        panel.case_cb.setChecked(True)
        panel.whole_word_cb.setChecked(True)
        panel.multiline_cb.setChecked(True)

        opts = panel.build_options()
        assert opts.pattern == "a.c", "pattern 未取面板文本"
        assert opts.is_regex is True, "is_regex 未取正则勾选"
        assert opts.case_sensitive is True, "case_sensitive 未取大小写勾选"
        assert opts.whole_word is True, "whole_word 未取全词勾选"
        assert opts.multi_line is True, "multi_line 未取多行勾选"

        # 信号必须是 4 参数，且第 4 个就是选项对象
        seen = {}

        def _slot(pattern, repl, files, options):
            seen['pattern'] = pattern
            seen['repl'] = repl
            seen['files'] = files
            seen['options'] = options

        panel.replace_requested.connect(_slot)
        panel.replace_requested.emit("a.c", "X", {}, opts)
        assert seen.get('options') is opts, \
            "replace_requested 未把 SearchOptions 传出去: %r" % (seen,)

        # 替换端必须复用"产生结果那次搜索"的选项
        panel.current_options = opts
        assert panel._options_for_replace() is opts, \
            "_options_for_replace 未复用搜索时的选项"
        panel.pattern_edit.setText("changed")
        assert panel._options_for_replace() is not opts, \
            "模式变化后仍复用旧选项（会拿旧匹配去替换）"

        return ("build_options 全项正确；信号 4 参数携带 options；"
                "替换复用搜索选项")
    finally:
        panel.deleteLater()
        host.deleteLater()


@qt_check("P0-3 动态：_on_global_replace 在 is_regex=True 时按正则替换")
def _d_replace_regex():
    MainWindow = _import_main_window()

    from core.search import SearchOptions

    tmp = tempfile.mkdtemp(prefix="qc_p0_regex_")
    try:
        path = os.path.join(tmp, "sample.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("foo FOO a.c\n")

        # 正则 a\.c 只匹配字面量 "a.c"。
        # 修复前按默认字面量处理 → 去找字面量 `a\.c` → 0 处替换 → 文件不变。
        options = SearchOptions(pattern=r"a\.c", is_regex=True,
                                case_sensitive=False, threads=1)
        # 面板实际发出的就是 options.pattern
        _call_global_replace(MainWindow, options.pattern, "ZZZ",
                             {path: []}, options)

        with open(path, encoding="utf-8") as f:
            got = f.read()
        assert got == "foo FOO ZZZ\n", \
            "正则替换结果 = %r（期望 'foo FOO ZZZ\\n'）" % got
        return "正则 a\\.c → ZZZ，文件内容=%r" % got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@qt_check("P0-3 动态：_on_global_replace 遵守 case_sensitive")
def _d_replace_case():
    MainWindow = _import_main_window()

    from core.search import SearchOptions

    tmp = tempfile.mkdtemp(prefix="qc_p0_case_")
    try:
        path = os.path.join(tmp, "case.txt")

        def run(case_sensitive):
            with open(path, "w", encoding="utf-8") as f:
                f.write("foo FOO\n")
            options = SearchOptions(pattern="foo", is_regex=False,
                                    case_sensitive=case_sensitive,
                                    threads=1)
            _call_global_replace(MainWindow, "foo", "BAR", {path: []}, options)
            with open(path, encoding="utf-8") as f:
                return f.read()

        strict = run(True)
        loose = run(False)
        assert strict == "BAR FOO\n", \
            "case_sensitive=True 结果 = %r（应只替换小写 foo）" % strict
        assert loose == "BAR BAR\n", \
            "case_sensitive=False 结果 = %r（应两处都替换）" % loose
        return "区分大小写: %r；不区分: %r" % (strict, loose)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@qt_check("P0-2 动态：草稿可被读取并恢复（真实 SessionManager + 真实标签页）")
def _d_draft_recover():
    from PyQt5.QtWidgets import QTabWidget

    from app.session import SessionManager

    # ⚠️ 修正（Lead 实测）：`_draft_dir` 定义在 **`Document`** 上，不是
    #   `DocumentModel`（后者是另一个类）。原写法会抛
    #   `AttributeError: type object 'DocumentModel' has no attribute '_draft_dir'`，
    #   使这条检查恒失败（脚本自身缺陷，与产品无关）。
    from core.document import Document

    try:
        from ui.editor_view import EditorWidget  # noqa: F401
    except ImportError as e:
        raise _SkipCheck("ui.editor_view 不可用: %s" % e)

    tmp = tempfile.mkdtemp(prefix="qc_p0_draft_")
    original_draft_dir = Document._draft_dir
    # 把草稿目录指到临时目录，避免污染真实 backup/drafts
    Document._draft_dir = staticmethod(lambda: tmp)
    try:
        def write_draft(name, original, text):
            p = os.path.join(tmp, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# QingCao Draft\n")
                f.write("# Original: %s\n" % (original or "(未命名)"))
                f.write("# Saved: 2025-01-01T00:00:00\n")
                f.write("# Encoding: utf-8\n")
                f.write("# ---\n")
                f.write(text)
            return p

        write_draft("untitled_0.draft", "", "草稿内容-未命名-ABC")
        write_draft("deadbeef.draft", os.path.join(tmp, "已删除.py"),
                    "草稿内容-已删除-XYZ")

        class FakeWindow:
            pass

        win = FakeWindow()
        win.tabs = QTabWidget()          # 真实标签容器

        sess = SessionManager()
        sess.bind_window(win)

        drafts = sess.find_recoverable_drafts()
        assert len(drafts) == 2, \
            "find_recoverable_drafts 找到 %d 项（期望 2）" % len(drafts)
        texts = sorted(d['text'] for d in drafts)
        assert texts == ["草稿内容-已删除-XYZ", "草稿内容-未命名-ABC"], \
            "草稿正文解析异常: %r" % (texts,)

        # main.py::deferred_init 实际执行的入口
        restored = sess.check_and_recover_drafts(parent=None, drafts=drafts)
        assert restored == 2, \
            "check_and_recover_drafts 返回 %d（期望 2）" % restored
        titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        assert len(titles) == 2, "标签数 = %d（期望 2）" % len(titles)
        assert all("[未保存]" in t for t in titles), \
            "恢复标签标题缺少 [未保存] 标记: %r" % (titles,)

        return "读取 2 项草稿 → 恢复 %d 项，标题=%r" % (restored, titles)
    finally:
        Document._draft_dir = staticmethod(original_draft_dir)
        shutil.rmtree(tmp, ignore_errors=True)


@qt_check("P0-2 动态：main._render_recovered_drafts 把草稿正文真正显示出来")
def _d_render_recovered():
    from PyQt5.QtWidgets import QTabWidget

    try:
        from core.content_provider import MemoryProvider
        from ui.editor_view import EditorWidget
    except ImportError as e:
        raise _SkipCheck("编辑器组件不可用: %s" % e)

    main_mod = _import_main()

    qtab = QTabWidget()
    text = "草稿内容-ZH-需要显示出来"
    provider = MemoryProvider()
    provider.open(initial_text=text)
    editor = EditorWidget(provider=provider)
    # 复刻 app/session.py 的建标签方式（正文只在 provider 里）
    qtab.addTab(editor, "未命名 [未保存]")

    # 先证明"缺口"真实存在：此时编辑器缓冲区是空的
    assert editor.text() == "", \
        "前置条件不成立：编辑器里已有内容 %r" % editor.text()

    window = types.SimpleNamespace(tabs=qtab)
    fixed = main_mod._render_recovered_drafts(window)
    assert fixed == 1, "_render_recovered_drafts 修复 %d 个标签（期望 1）" % fixed
    assert text in editor.text(), \
        "补渲染后编辑器内容 = %r（未包含草稿正文）" % editor.text()
    assert editor.proxy.is_modified is True, "补渲染后未标记为已修改"
    return "空白标签已渲染出 %d 字，并标记为已修改" % len(editor.text())


@qt_check("P0-8 动态：字符数按解码后的字符计（中文不再差 3 倍）")
def _d_char_counts():
    try:
        from app.tabs import TabManager
        from ui.editor_view import EditorWidget
        from ui.perf_monitor import PerfMonitor
    except ImportError as e:
        raise _SkipCheck("编辑器/面板组件不可用: %s" % e)

    editor = EditorWidget()
    editor.setText("中文abc")

    now = editor.text()
    assert "中文abc" in now, "setText 未生效: %r" % now
    expect_chars = len(now)                       # 真实字符数
    # 字节数由控件自己报告（生产代码用的就是这个值）
    expect_bytes = editor.SendScintilla(editor.SCI_GETLENGTH)
    assert expect_bytes > expect_chars, \
        "前置条件不成立：应为多字节文本（chars=%d bytes=%d）" % (
            expect_chars, expect_bytes)

    # ---- ui/perf_monitor.py ----
    chars, nbytes = PerfMonitor._count_chars(editor)
    assert chars == expect_chars, \
        "PerfMonitor._count_chars 字符数 = %d（期望 %d）" % (
            chars, expect_chars)
    assert nbytes == expect_bytes, \
        "PerfMonitor._count_chars 字节数 = %d（期望 %d）" % (
            nbytes, expect_bytes)

    # ---- app/tabs.py::get_tab_info（用最小宿主执行真实方法体）----
    class FakeHost:
        _get_proxy_filepath = staticmethod(lambda proxy: None)
        _get_proxy_encoding = staticmethod(lambda proxy: "utf-8")

        # `TabManager.get_tab_info` 开头会做
        # `if index < 0 or index >= self.count(): return None`，
        # 所以宿主必须提供 count()。原脚本缺这个方法，导致
        # `AttributeError: 'FakeHost' object has no attribute 'count'`
        # —— 脚本自身缺陷，与产品无关（Lead 实测补上）。
        def count(self):
            return 1

        def widget(self, index):
            return editor

        def tabText(self, index):
            return "测试"

    info = TabManager.get_tab_info(FakeHost(), 0)
    assert info is not None, "get_tab_info 返回 None"
    assert info['char_count'] == expect_chars, \
        "get_tab_info char_count = %r（期望 %d；修复前是字节数 %d）" % (
            info['char_count'], expect_chars, expect_bytes)
    assert info['byte_count'] == expect_bytes, \
        "get_tab_info byte_count = %r（期望 %d）" % (
            info['byte_count'], expect_bytes)
    return "PerfMonitor=(%d 字符/%d 字节)；get_tab_info char=%d byte=%d" % (
        chars, nbytes, info['char_count'], info['byte_count'])


# ============================================================
# 额外信息（非验收项）：P0-7 双重 didSave 的真实调用次数
# ============================================================
def report_p0_7():
    src = read("core/editor.py")
    stripped = strip_comments(src)
    raw = src.count("_notify_lsp_saved(filepath)")
    print("")
    print("[信息] P0-7（core/editor.py 双重 didSave）:")
    print("       原始文本出现次数              = %d（含注释里的说明文字）" % raw)
    if stripped is None:
        print("       tokenize 去注释失败：无法判定真实调用次数，"
              "请肉眼确认 760-780 行。")
        return
    real = stripped.count("_notify_lsp_saved ( filepath )")
    print("       去掉注释后的**真实调用**次数  = %d" % real)
    if real == 1:
        print("       → 当前工作区只有 1 次真实调用：多出来的一次来自修复说明"
              "注释里的反引号文本，P0-7 疑似**误报**。删除前请先确认！")
    elif real > 1:
        print("       → 存在 %d 次真实调用，确实重复。" % real)


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 72)
    print("青草编辑器 P0-1/2/3（+P0-8）缺陷修复验证")
    print("仓库根目录: %s" % ROOT)
    print("Python: %s" % sys.version.split()[0])
    print("=" * 72)

    print("")
    print("---- 静态接线检查 ----")
    for name, fn in STATIC_CHECKS:
        _run(name, fn)

    print("")
    print("---- 动态验证（QT_QPA_PLATFORM=%s）----"
          % os.environ.get("QT_QPA_PLATFORM"))
    qt_ok = True
    try:
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        assert app is not None
    except Exception as e:
        qt_ok = False
        print("[SKIP] 动态检查全部跳过：QApplication 创建失败: %s" % e)

    if qt_ok:
        for name, fn in QT_CHECKS:
            _run(name, fn)

    print("")
    print("=" * 72)
    passed = failed = 0
    for ok, name, detail in RESULTS:
        if ok:
            passed += 1
            print("[PASS] %s" % name)
        else:
            failed += 1
            print("[FAIL] %s" % name)
        if detail:
            print("       %s" % detail.replace("\n", "\n       "))
    for name, reason in SKIPPED:
        print("[SKIP] %s —— %s" % (name, reason))

    try:
        report_p0_7()
    except Exception as e:
        print("[信息] P0-7 统计失败: %s" % e)

    print("")
    print("=" * 72)
    print("结果: %d 通过, %d 失败, %d 跳过" % (passed, failed, len(SKIPPED)))
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except _SkipCheck as e:
        print("[SKIP] %s" % e)
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
