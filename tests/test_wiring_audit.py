# -*- coding: utf-8 -*-
"""接线审计 + 端到端冒烟测试（P9，独立验证，不改生产代码）

本项目的**结构性缺陷**是同一类问题反复出现：

    "代码写好了，但从未被接线"

已知实例（本次改造前已核实）：

    * ``SessionManager.start_autosave()`` 零调用点 → 崩溃恢复完全失效
    * ``LocalCompleter.get_completions()`` / ``record_used()`` 零调用方
    * ``LspClient`` 的 8 个请求（request_definition 等）全部零调用方
    * ``EditorProxy.toggle_lsp()`` 零生产调用点
    * ``MARKER_BREAKPOINT`` 只被"画出来"，从不被读写（无法设断点）
    * ``external_change_detected`` 信号零 ``connect``
    * 若干 UI 模块零 import（本次 D2 已删除 19 个，见 KNOWN_DEAD_MODULES
      上方清单；剩余 17 个有删除阻塞，见同处注释）

这个测试文件把上述问题变成**可自动检测**的，分三部分：

1. ``TestKeyApiWiring``   —— 关键 API 必须有生产调用点（静态）
2. ``TestDeadModules``    —— 死模块不得**新增**（相对显式基线）
3. ``TestEndToEndSmoke``  —— offscreen Qt 下**真实执行**并断言结果

关于 ``xfail(strict=False)``
---------------------------
本次改造由多个队友**并行**进行，写这个文件时它们尚未全部完成。因此：
每个"当前确实未接线"的断言都标了 ``xfail(strict=False)`` 并写明当前状态。
- 未接线 → ``xfail``（预期失败，不拖红整个套件）
- 接线后 → ``XPASS``（报告里直接可见"已接上"）

**断言本身没有被放宽**：一旦接线，``XPASS`` 即告完成；若接线后又断开，
测试会真正失败。这样既能安全工作在中间状态，又保留了防线的力量。

运行::

    python -m pytest tests/test_wiring_audit.py -v -p no:cacheprovider
"""
import os
import re

import pytest


# ============================================================
# 路径与扫描基础
# ============================================================
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 生产代码根目录（**不含** tests/ 与 tools/）
PRODUCTION_DIRS = ("core", "ui", "app", "infrastructure", "plugins")

# 不参与"生产调用点"统计的目录
NON_PRODUCTION = tuple(
    os.path.join(ROOT, d)
    for d in ("tests", "tools", "docs", "dist", "build", "_archive")
)


def _read(path):
    """安全读文件，失败返回空串"""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _iter_py(root_dirs, skip_non_production=True):
    """遍历 .py 文件，产出绝对路径"""
    for rel in root_dirs:
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", ".git")]
            if skip_non_production and any(
                os.path.normcase(dirpath).startswith(os.path.normcase(p))
                for p in NON_PRODUCTION
            ):
                continue
            for fn in filenames:
                if fn.endswith(".py"):
                    yield os.path.join(dirpath, fn)


def _production_sources():
    """返回 {绝对路径: 源码}，仅生产代码"""
    return {p: _read(p) for p in _iter_py(PRODUCTION_DIRS)}


def _all_py_sources():
    """生产代码 + main.py（用于找调用点）"""
    src = _production_sources()
    main_py = os.path.join(ROOT, "main.py")
    if os.path.isfile(main_py):
        src[main_py] = _read(main_py)
    return src


def _definition_file(symbol):
    """找出定义 symbol 的文件（仅限生产代码）"""
    for path, src in _production_sources().items():
        if re.search(r"^\s*(def|class)\s+%s\b" % re.escape(symbol),
                     src, re.M):
            return path
    return None


def _call_sites(symbol, exclude_def=True):
    """返回 symbol 在**定义文件之外**出现的 (文件, 行号, 行内容) 列表

    只统计生产代码 + main.py；跳过纯注释行，避免把说明文字当调用点。
    """
    hits = []
    def_file = _definition_file(symbol) if exclude_def else None
    pat = re.compile(r"\b%s\b" % re.escape(symbol))
    for path, src in _all_py_sources().items():
        if def_file and os.path.normcase(path) == os.path.normcase(def_file):
            continue
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if pat.search(line):
                hits.append((path, i, stripped))
    return hits


def _rel(path):
    try:
        return os.path.relpath(path, ROOT).replace("\\", "/")
    except ValueError:
        return path


# ============================================================
# 1. 关键 API 接线断言
# ============================================================
class TestKeyApiWiring:
    """本次"生产可用化"改造的目标 API 必须有**生产调用点**"""

    def test_start_autosave_is_called(self):
        """P1: start_autosave 必须被生产代码调用（否则崩溃恢复是空壳）

        已接线：`ui/main_window.py` 构造时调用 `session.start_autosave()`。
        （原为 xfail；接线完成后摘掉标记，恢复为硬断言。）
        """
        hits = _call_sites("start_autosave")
        detail = "\n".join(
            "    %s:%d  %s" % (_rel(p), n, s) for p, n, s in hits
        ) or "    （无任何调用点）"
        assert hits, (
            "start_autosave 零生产调用点 → 崩溃恢复失效。\n"
            "    期望：ui/main_window.py 构造时调用 "
            "self.session.start_autosave()\n"
            "    实际命中：\n%s" % detail
        )

    def test_stop_autosave_is_called(self):
        """P1: stop_autosave 应同时接线（关闭时停止定时器）

        已接线：`ui/main_window.py` 的 closeEvent 里与 start_autosave 配对。
        （原为 xfail；接线完成后摘掉标记，恢复为硬断言。）
        """
        hits = _call_sites("stop_autosave")
        assert hits, (
            "stop_autosave 零生产调用点（定时器启动后无人停止）"
        )

    def test_local_completer_is_wired(self):
        """P10: LocalCompleter 的补全/记录方法必须被生产代码调用"""
        used = {
            name: len(_call_sites(name))
            for name in ("get_completions", "record_used", "update_from_file")
        }
        assert any(v > 0 for v in used.values()), (
            "LocalCompleter 完全未接线（get_completions/record_used/"
            "update_from_file 均零调用点）：%s" % used
        )

    def test_local_completer_used_in_editor(self):
        """P10: 补全器必须接在编辑器路径上（而不只是统计面板读实例）"""
        hits = _call_sites("LocalCompleter", exclude_def=False)
        editor_hits = [
            (p, n, s) for p, n, s in hits
            if "editor_view" in os.path.normcase(p)
        ]
        assert editor_hits, (
            "LocalCompleter 未出现在 ui/editor_view.py —— 补全未接进编辑器。\n"
            "    当前引用：%s"
            % [(_rel(p), n) for p, n, s in hits]
        )

    def test_lsp_request_definition_is_called(self):
        """P6: LspClient.request_definition 必须有生产调用方"""
        hits = _call_sites("request_definition")
        assert hits, (
            "request_definition 零生产调用点 → 转到定义不可用。\n"
            "    期望由 EditorProxy.goto_definition() 发出请求。"
        )

    def test_lsp_definition_signal_connected(self):
        """P6: definition_ready 信号必须被 connect（否则结果无人接收）"""
        hits = [
            (p, n, s) for p, n, s in _call_sites(
                "definition_ready", exclude_def=False)
            if "connect" in s
        ]
        assert hits, (
            "definition_ready 信号零 connect → 转到定义即使发出请求，"
            "结果也无人处理。"
        )

    def test_toggle_lsp_has_production_call_site(self):
        """P6: EditorProxy.toggle_lsp 必须有生产入口（不能只在测试里调）

        改造前唯一调用在 tests/audit_concurrency_probe.py:199。
        """
        hits = _call_sites("toggle_lsp")
        # 当前状态：ui/main_window.py 可能已接线（lsp_action.toggled）
        assert hits, (
            "toggle_lsp 零生产调用点 → LSP 无法被用户启用。\n"
            "    期望：ui/main_window.py 的 LSP 菜单项连接到它。"
        )

    def test_lsp_start_passes_command(self):
        """P6: lsp_client.start() 必须带 command 参数"""
        src = _read(os.path.join(ROOT, "core", "editor.py"))
        bad = re.findall(r"lsp_client\.start\(\s*\)", src)
        assert not bad, (
            "core/editor.py 仍存在 lsp_client.start() 无参调用（%d 处）"
            "→ LSP 必然 TypeError。\n"
            "    期望：start(command, working_dir=...)，command 从 "
            "LspServerRegistry.get_command(lang) 取。" % len(bad)
        )

    def test_breakpoint_marker_is_read_write(self):
        """MARKER_BREAKPOINT 必须能被"设置/清除"，而不只是被绘制

        已接线：`ui/editor_view.py` 的 `_toggle_breakpoint_at_line` /
        `get_breakpoints` / `clear_breakpoints` 会 markerAdd/markerDelete，
        并有装订线单击 + F9 + 右键菜单三个入口。
        （原为 xfail；接线完成后摘掉标记，恢复为硬断言 —— 否则接线再被
         改坏时它只会变成 XPASS 而不报错，防线失效。）
        """
        pattern = re.compile(
            r"marker(Add|Delete)\s*\(\s*[^,)]+,\s*MARKER_BREAKPOINT\b"
        )
        hits = []
        for path, src in _all_py_sources().items():
            for i, line in enumerate(src.splitlines(), 1):
                if pattern.search(line):
                    hits.append((path, i, line.strip()))
        assert hits, (
            "MARKER_BREAKPOINT 只被绘制、从未被读写 → 无法设置断点。\n"
            "    期望：行号边距点击处理里调用 "
            "markerAdd(line, MARKER_BREAKPOINT) / markerDelete(...)。"
        )

    def test_external_change_signal_connected(self):
        """external_change_detected 必须被 connect（否则外部改动无提示）

        已接线：`core/editor.py` 的 `EditorProxy._connect_signals()` 把
        `document.external_change_detected` 接到 `_on_external_change`，
        并转发为 `EditorProxy.external_change_detected` 供宿主提示。
        （原为 xfail；接线完成后摘掉标记，恢复为硬断言。）
        """
        hits = [
            (p, n, s) for p, n, s in _call_sites(
                "external_change_detected", exclude_def=False)
            if "connect" in s
        ]
        assert hits, (
            "external_change_detected 零 connect → 文件被外部修改时不提示，"
            "继续按偏移覆盖，可能丢数据。"
        )

    def test_goto_definition_exists_on_proxy(self):
        """P6: main_window 调用的 EditorProxy.goto_definition 必须真的存在"""
        editor_src = _read(os.path.join(ROOT, "core", "editor.py"))
        assert re.search(r"^\s*def\s+goto_definition\b", editor_src, re.M), (
            "core/editor.py 中不存在 EditorProxy.goto_definition()，"
            "但 ui/main_window.py 会调用它 → 转到定义永远不可用。"
        )

    def test_lsp_requests_have_result_handlers(self):
        """B 阶段防线：LSP 的每个请求方法都必须有**结果信号 connect**

        缺陷背景（本项目最典型的一类）：
            `LspClient` 实现了 10 个请求与对应信号，但
            `request_hover/references/rename/document_symbols/code_actions/
            formatting/signature_help` 的信号**全仓零 connect** ——
            请求发得出去、结果永远回不来，功能等于不存在。

            本测试要求：每个请求方法在 `core/editor.py` 里都有对应的
            `xxx_ready.connect(...)`，防止将来加请求时忘记接结果。
        """
        editor_src = _read(os.path.join(ROOT, "core", "editor.py"))
        # 请求方法 → 结果信号
        pairs = {
            "request_hover": "hover_ready",
            "request_definition": "definition_ready",
            "request_references": "references_ready",
            "request_rename": "rename_ready",
            "request_document_symbols": "document_symbols_ready",
            "request_code_actions": "code_actions_ready",
            "request_formatting": "formatting_ready",
            "request_signature_help": "signature_help_ready",
        }
        problems = []
        for method, sig in pairs.items():
            if not re.search(r"\." + method + r"\s*\(", editor_src):
                problems.append("%s 无生产调用点" % method)
            if not re.search(r"\." + sig + r"\.connect\s*\(", editor_src):
                problems.append("%s 结果信号未 connect" % sig)
        assert not problems, (
            "LSP 请求与结果信号接线不完整（发了请求收不到结果）：\n      "
            + "\n      ".join(problems)
        )

    def test_no_ui_bypasses_content_sync(self):
        """P0-B 防线：UI 层不得直接调 `document.save()` 保存用户文件

        缺陷背景（已实测复现的数据丢失）：
            `_save_file_as` 曾调用 `proxy.document.save(path)`，绕过
            `EditorProxy._sync_content_to_provider()` —— 而 Document 只持有
            provider，**拿不到 QScintilla 里的当前文本**。于是"另存为"
            写下的是**打开文件时**的旧内容：

                打开 = 'OLD LINE 1\\nOLD LINE 2\\n'
                编辑 = 'NEW CONTENT A\\n...'
                另存为返回 True，磁盘上却仍是 OLD

            而 `Document.save` 还返回 True、清 modified、删草稿 ——
            用户看到"成功"，编辑全部丢失且连草稿都救不回来。

        现在 UI 层一律走 `proxy.save_file(path)`（同步 → 保存 → 清标记
        → 通知 LSP → 删草稿）。`document.save()` 在**生产代码中只允许
        出现在 `EditorProxy.save_file()` 内部**（即在同步之后）。

        本测试把这个不变量固化，防止将来有人再图省事直接调 Document。
        """
        offenders = []
        for path, src in _all_py_sources().items():
            rel = _rel(path)
            # 只约束 UI 层与插件（core 内部的正确调用在 editor.py）
            if not (rel.startswith("ui/") or rel.startswith("plugins/")):
                continue
            for n, line in enumerate(src.split("\n"), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if re.search(r"\bdocument\.save\s*\(", s):
                    offenders.append("%s:%d  %s" % (rel, n, s[:70]))
        assert not offenders, (
            "UI/插件层直接调用了 `document.save()` —— 这会绕过内容同步，"
            "导致写入磁盘的是 provider 里的**旧内容**（P0-B 数据丢失）。\n"
            "    请改用 `proxy.save_file(path)`。\n"
            "    违规位置：\n      " + "\n      ".join(offenders)
        )


# ============================================================
# 2. 死模块检测（相对基线）
# ============================================================
# 已核实的零 import 模块基线。
#
# 这些是历史遗留，不在本次范围；**新增**的才需要报警。
#
# ------------------------------------------------------------------
# D2 死模块清理（本次任务）后本基线从 37 条缩到 17 条
# ------------------------------------------------------------------
#
# **已删除的 19 个模块**（均逐个全仓 grep 核实零引用，删除记录见
# git 历史；此处保留清单是为了让"基线为什么变短"有据可查）：
#
#   ui/macro_editor.py           宏编辑器对话框。core.macro 的 MacroRecorder
#                                仍由 ui/main_window.py:197 接线，删除的只是
#                                从未被打开过的编辑对话框（2280 行）。
#   ui/benchmark_dialog.py       零引用；且是 docs/audit_concurrency.md 记录的
#                                "子线程改 QWidget" 潜伏缺陷（F-4b）所在地。
#   ui/file_merge_dialog.py      零引用（core/file_merge 仍被 tests 使用）。
#   ui/git_panel.py              零引用（core/git_client 仍被 tests 与
#                                git_deep 插件使用）。
#   ui/code_metrics_panel.py     零引用（core/code_metrics 仍被
#                                tools/bench_performance_audit.py:377,382 使用）。
#   ui/usage_stats_panel.py      零引用（core/usage_stats 仍被
#                                ui/welcome_widget.py:886 使用）。
#   ui/snippet_editor.py         零引用（core/snippets 仍被
#                                ui/editor_view.py:1117 使用）。
#   ui/refactor_dialog.py        零引用；同为 F-4a 潜伏缺陷所在地。
#   ui/enhanced_scrollbar.py     全仓零引用。
#   ui/breadcrumb.py             全仓零引用（ui/outline_panel.py 的
#                                `breadcrumb_label` 是自有属性，与此无关）。
#   ui/debug_panel.py            全仓零引用。
#   ui/log_viewer.py             全仓零引用。
#   ui/shortcut_overlay.py       全仓零引用。
#   ui/file_association.py       全仓零引用。
#   ui/diff_view.py              全仓零引用。
#   ui/markdown_preview.py       全仓零引用（同名**插件** markdown_preview
#                                用的是自己的 QTextBrowser，未复用该控件）。
#   ui/terminal_panel.py         零生产引用；唯一指向是
#                                tests/audit_concurrency_probe.py:463 的**带
#                                守卫**导入（ImportError→pytest.skip），而
#                                audit_*.py 按本文件既定规则不计入引用统计。
#   plugins/git_deep/commit_panel.py  未被 plugins/git_deep/__init__.py 导入。
#   plugins/git_deep/diff_view.py     同上。
#
# **`ui/help_browser.py` 已移出本基线**（不是因为它被删除 —— 文件仍在）：
#   它现在被 tests/test_shortcuts.py:298,307 `from ui.help_browser import
#   HELP_TOPICS` 导入，因此本脚本的 import 扫描不再把它判为死模块。
#   注意耦合：若将来移除 tests/test_shortcuts.py 的这两处导入，
#   help_browser 会重新变成死模块并被 test_no_new_dead_modules 报出。
#
# **仍保留在基线里的 17 条及原因**（都有删除阻塞，不是"懒得删"）：
#   * 接线候选（价值真实，但接线点在 ui/main_window.py / core/editor.py，
#     不在 task-8 写作用域内）：
#       ui/problems_panel.py      LSP 诊断列表。core/editor.py:2251 的
#                                 _on_lsp_diagnostics 目前只画指示器，
#                                 **从不**调 ProblemManager；核心缺口是生产者，
#                                 不是面板。
#       ui/undo_history_panel.py  refresh() 读 proxy.undo_manager.undo_stack /
#                                 redo_stack，契约与 core/undo.py 一致，可用。
#   * tools/ 有真实路径引用（非 import，但工具脚本会 FileNotFoundError）：
#       ui/lsp_panel.py           tools/verify_patches.py:46,52；且 LSP 刚接通。
#   * **完成态的功能引擎，保留而非删除**（Lead 决策，见下方说明）：
#       ui/collab_dialog.py       -> core/collab.py        （协同编辑）
#       ui/snapshot_manager_dialog.py -> core/snapshot.py  （快照管理）
#       ui/task_panel.py          -> core/project_tasks.py （项目任务）
#       ui/snippet_market_dialog.py   -> core/snippet_market.py（片段市场）
#       ui/profiler_panel.py      -> core/profiler.py      （性能剖析）
#
#       说明：这 5 组**不是**废弃代码，而是"已实现但从未接线"的功能引擎
#       （core 侧完整、零生产引用、零测试）。它们确实零引用，但：
#         - 删除是**不可逆的产品决策**，超出"清理死代码"的授权范围；
#         - 正确处置是**接线**而非删除（例如 problems_panel 只需
#           在 _on_lsp_diagnostics 里补一次 ProblemManager 写入）；
#         - 把死模块计数从 17 降到 3 属于"指标好看"，不是工程收益。
#       因此明确**保留**，作为已知的技术债登记在此，而不是靠"删除会
#       孤立 core 后端"这种机制性理由搪塞。
#
#       附带事实（供将来接线时参考）：build.py:442-447 是
#       `for m in project_modules: try: __import__(m) except ImportError: pass`
#       —— 漏删 hiddenimports **不会**导致打包失败，只会被静默跳过。
#   * 零引用但列在 build.py hiddenimports：
#       core/key_sequence_manager.py (build.py:411)
#       core/code_templates.py       (build.py:408)
#       core/exporter.py             (build.py:409)
#       core/formatter.py            (build.py:410)
#       core/project_config.py       (build.py:413)
#       core/workspace.py            (build.py:417)
#       core/keymap_profiles.py      (build.py:412)
KNOWN_DEAD_MODULES = frozenset({
    # ---- 仅剩 2 个，且都**需要产品成立条件**才能接线 ----
    #
    # `ui/collab_dialog.py` + `core/collab.py`：
    #   实时协作（P2P）。协议与 UI 都完整，但缺 NAT 穿透、权限、冲突解决、
    #   安全模型，且无法在无网络环境验证 —— 属"高风险新功能"，
    #   不是接线问题。详见 docs/product_decision_pending.md。
    "ui/collab_dialog.py",
    # `ui/snippet_market_dialog.py` + `core/snippet_market.py`：
    #   代码片段市场。对话框完整，但后端是**网络客户端** ——
    #   没有市场服务端就没有内容可下载。属"需先有产品服务"，
    #   不是接线问题。详见 docs/product_decision_pending.md。
    "ui/snippet_market_dialog.py",
})
#
# 说明（已从基线移除的条目 —— 它们**已经接线**，不再是孤立模块）：
#   第一轮：core/formatter.py、core/exporter.py、ui/lsp_panel.py、
#           ui/problems_panel.py、ui/undo_history_panel.py、
#           core/keymap_profiles.py、ui/profiler_panel.py
#   第二轮（批次 A）：core/code_templates.py、ui/snapshot_manager_dialog.py
#   第三轮（批次 C）：core/key_sequence_manager.py
#   第四轮（批次 B）：core/workspace.py、core/project_config.py、
#                     ui/task_panel.py
# 移除动作由 `test_ledger_matches_baseline` 与棘轮
# `test_dead_module_count_is_decreasing` 共同保证不会被偷偷放回来。

# ============================================================
# P0-11：技术债台账 + 递减棘轮（把"可豁免基线"改成"必须递减"）
# ============================================================
#
# 为什么需要（本仓库最大的系统性风险）：
#   原先只有 `KNOWN_DEAD_MODULES`（一个 frozenset 基线）+ "不得新增"断言。
#   这能防**新增**，却**对存量零压力** —— 基线一旦写死，30 个孤立模块
#   （约 9,200 行）可以永远躺在那里；测试源码里甚至写着
#   「把死模块计数从 17 降到 3 属于指标好看，不是工程收益」，
#   等于用基线把指标洗白了。
#
# 现在改为**三件套**：
#   1. DEBT_LEDGER —— 每条债务必须有 owner / 动作（接线或删除）/ 期限，
#      没有台账条目的孤立模块直接算"未登记新增"，测试失败；
#   2. DEBT_CEILING_HISTORY —— 只增不减的"棘轮"历史。当前孤立模块数
#      **不得超过历史最低值**，且每次降低都必须留下记录。这条把
#      "必须递减"变成**机器可执行的约束**，而不是口号；
#   3. 债务统计会打印在失败信息里（模块数 + 总行数），让"欠了多少"可见。
#
# 注意（防呆）：`DEBT_LEDGER` 的键集合必须与 `KNOWN_DEAD_MODULES` 完全一致，
# 由 `test_ledger_matches_baseline` 强制 —— 避免出现"基线里有、台账里没有"
# 的幽灵条目（那正是本次要消灭的"豁免式基线"）。
DEBT_ACTION_WIRE = "wire"      # 接线（功能保留，补上入口）
DEBT_ACTION_DELETE = "delete"  # 删除（确认不再需要）

DEBT_LEDGER = {
    # ---------- 仅剩 2 个：需要"产品成立条件"才能接线 ----------
    #
    # 已接线的条目**必须从台账里删除**，不能留作"历史记录" ——
    # 台账 = 当前欠债清单，`test_ledger_matches_baseline` 强制它与
    # `KNOWN_DEAD_MODULES` 键集合完全一致。已完成的接线见上方注释。
    "ui/collab_dialog.py": dict(
        owner="product", action=DEBT_ACTION_WIRE, due="待产品立项",
        note="实时协作(P2P)。协议+UI 完整，但缺 NAT 穿透/权限/冲突解决/"
             "安全模型，且无法在无网络环境验证。属高风险新功能，"
             "不是接线问题 —— 需先决定是否做该功能。"),
    "ui/snippet_market_dialog.py": dict(
        owner="product", action=DEBT_ACTION_WIRE, due="待产品立项",
        note="代码片段市场。对话框完整，但后端 SnippetMarketClient 是"
             "**网络客户端** —— 没有市场服务端就没有内容可下载。"
             "属需先有产品服务，不是接线问题。"),
}

# 孤立模块数量的"棘轮"历史（只增不减地记录**降低**，不得回填升高）
#
# 规则：当前孤立模块数 <= 历史最低值。想把上限调高，必须在本列表里
# 追加一条并写明原因 —— 那会让"放宽门槛"变成一个**显式的、要评审的动作**，
# 而不是悄悄改个数字。
DEBT_CEILING_HISTORY = [
    # (日期, 上限, 说明)
    ("2026-02-20", 17, "初次建立台账（此前基线 frozenset 无递减约束）"),
    ("2026-02-20", 12, "本轮接线 5 个：formatter/exporter/lsp_panel/"
                       "problems_panel/undo_history_panel"),
    ("2026-02-20", 10, "再接线 3 个：keymap_profiles（VSCode/Sublime/Vim "
                       "快捷键方案）、profiler + profiler_panel（性能剖析）"),
    ("2026-02-20", 8, "删除 2 个确认无用的：benchmark（生产无用途，测试应改用 "
                      "pytest-benchmark）、refactor_session（配套 UI 早已删除）。"
                      "删除同时清理了 build.py 与 QingCaoEditor.spec 的 "
                      "hiddenimports，避免打包时静默跳过不存在的模块。"),
    ("2026-02-20", 6, "批次 A 接线 2 个：code_templates（从模板新建 + 修 "
                      "format_template 参数冲突/占位符残留）、"
                      "snapshot_manager_dialog（会话快照 + 修相对路径/未保存保护）"),
    ("2026-02-20", 5, "批次 C 接线 1 个：key_sequence_manager（多键序列，"
                      "修事件过滤器导致崩溃 + 焦点判断失效两个缺陷）"),
    ("2026-02-20", 2, "批次 B 接线 3 个：workspace + project_config + "
                      "task_panel（统一「项目根」语义）。"
                      "剩余 2 个需产品立项，已转入 docs/product_decision_pending.md"),
]

# 当前上限 = 历史最低值（棘轮只允许往下走）

# 当前上限 = 历史最低值（棘轮只允许往下走）
DEBT_CEILING = min(c for _d, c, _n in DEBT_CEILING_HISTORY)

# 这些模块即使无人 import 也合法（特殊情况）
#
# 当前为空：`core/log_lexer.py` 一度被列在这里，但实测确认它**确实**被
# `ui/editor_view.py:633` 的 `from core.log_lexer import LogLexer` 导入，
# 因此不需要豁免 —— 保持豁免清单为空可以让检测保持严格。
EXEMPT_MODULES = frozenset()

_IMPORT_PAT = re.compile(
    r"^\s*(?:from\s+([\w\.]+)\s+import\b|import\s+([\w\.]+))", re.M
)


def _module_import_names(rel_path):
    """把 ui/foo.py 转成可被 import 的点分模块名候选集合"""
    dotted = rel_path[:-3].replace("/", ".")
    return {dotted, dotted.split(".")[-1]}


def _imported_modules():
    """收集全仓（含 tests/tools/main.py）的 import 模块名集合

    注意：``tests/`` 下**只扫描 ``test_*.py`` 与 ``conftest.py``**，
    不扫描 ``audit_*.py`` 等辅助脚本。原因：并发审计脚本里有把模块名
    写在**注释/字符串**里的习惯（例如把 ``ui/refactor_dialog.py`` 当成
    "已知问题位置"引用），若一并计入，会让真正的死模块被误判为"有引用"，
    从而漏报本测试最想抓的那类缺陷。
    """
    imported = set()
    for rel in PRODUCTION_DIRS + ("tests", "tools"):
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames
                           if d not in ("__pycache__", ".git")]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                if rel == "tests" and not (
                    fn.startswith("test_") or fn == "conftest.py"
                ):
                    continue
                src = _read(os.path.join(dirpath, fn))
                for m in _IMPORT_PAT.finditer(src):
                    mod = m.group(1) or m.group(2)
                    if mod:
                        imported.add(mod)
    imported.update(
        m.group(1) or m.group(2)
        for m in _IMPORT_PAT.finditer(_read(os.path.join(ROOT, "main.py")))
    )
    return imported


def _detect_dead_modules():
    """返回 (相对路径) 集合：完全没有任何 import 指向它的模块"""
    imported = _imported_modules()
    candidates = []
    for rel in ("core", "ui"):
        base = os.path.join(ROOT, rel)
        if not os.path.isdir(base):
            continue
        for fn in sorted(os.listdir(base)):
            if fn.endswith(".py") and fn != "__init__.py":
                candidates.append("%s/%s" % (rel, fn))

    dead = set()
    for rel in candidates:
        if rel in EXEMPT_MODULES:
            continue
        if not (_module_import_names(rel) & imported):
            dead.add(rel)
    return dead


class TestDeadModules:
    """把"模块存在但无人调用"变成可自动检测的防线"""

    def test_no_new_dead_modules(self):
        """不得**新增**死模块（相对已知基线）

        不断言"零死代码"——仓库确实有历史遗留死模块。
        新增任何死模块即失败，逼迫"要么接线、要么明确登记"。
        """
        dead = _detect_dead_modules()
        new_dead = sorted(dead - KNOWN_DEAD_MODULES)
        assert not new_dead, (
            "检测到**新增**死模块（零 import）：\n%s\n\n"
            "若确为有意保留，请把它加入 KNOWN_DEAD_MODULES 并说明原因；"
            "否则应接线或删除。\n"
            "（当前死模块总数=%d，基线=%d）"
            % ("\n".join("    " + m for m in new_dead),
               len(dead), len(KNOWN_DEAD_MODULES))
        )

    def test_baseline_entries_still_exist(self):
        """基线里的模块若已被删除，应同步更新基线（防止基线腐化）"""
        missing = [m for m in sorted(KNOWN_DEAD_MODULES)
                   if not os.path.isfile(os.path.join(ROOT, m))]
        assert not missing, (
            "KNOWN_DEAD_MODULES 中的文件已不存在，请更新基线：\n%s"
            % "\n".join("    " + m for m in missing)
        )

    def test_refactored_modules_have_callers(self):
        """本次改造涉及的核心模块必须有调用方（不能是死模块）"""
        targets = {
            "core/local_completer.py": "LocalCompleter",
            "core/lsp_client.py": "LspClient",
            "core/content_provider.py": "LocalFileProvider",
            "app/session.py": "SessionManager",
            "ui/editor_view.py": "EditorWidget",
        }
        problems = []
        for rel, symbol in targets.items():
            path = os.path.join(ROOT, rel)
            if not os.path.isfile(path):
                problems.append("%s 不存在" % rel)
                continue
            hits = _call_sites(symbol, exclude_def=False)
            external = [h for h in hits
                        if os.path.normcase(h[0]) != os.path.normcase(path)]
            if not external:
                problems.append("%s 的 %s 无外部引用" % (rel, symbol))
        assert not problems, (
            "以下核心模块/符号没有任何外部引用（退化为死代码）：\n%s"
            % "\n".join("    " + p for p in problems)
        )

    # ========================================================
    # P0-11：技术债台账 + 递减棘轮
    # ========================================================
    def test_ledger_matches_baseline(self):
        """台账与基线必须**完全一致**（消灭"豁免式基线"）

        原先只有 `KNOWN_DEAD_MODULES` —— 一个没有 owner、没有动作、没有期限的
        frozenset。它能防新增，却对存量零压力：条目一旦写进去就可以永远躺着。
        现在每条债务都必须在 `DEBT_LEDGER` 里对应一条，键集合不一致即失败。
        """
        ledger_keys = set(DEBT_LEDGER)
        base = set(KNOWN_DEAD_MODULES)
        only_base = sorted(base - ledger_keys)
        only_ledger = sorted(ledger_keys - base)
        assert not only_base and not only_ledger, (
            "DEBT_LEDGER 与 KNOWN_DEAD_MODULES 不一致：\n"
            "  仅在基线里（= 无 owner/无期限的豁免条目）：%s\n"
            "  仅在台账里（= 指向不存在的基线条目）：%s\n"
            "两者必须一一对应。" % (only_base, only_ledger)
        )

    def test_ledger_entries_are_actionable(self):
        """每条债务必须有 owner / 动作 / 期限，且动作取值合法"""
        valid = {DEBT_ACTION_WIRE, DEBT_ACTION_DELETE}
        bad = []
        for mod, info in sorted(DEBT_LEDGER.items()):
            missing = [k for k in ("owner", "action", "due", "note")
                       if not info.get(k)]
            if missing:
                bad.append("%s 缺少字段 %s" % (mod, missing))
                continue
            if info["action"] not in valid:
                bad.append("%s 的 action=%r 非法（应为 %s）"
                           % (mod, info["action"], sorted(valid)))
        assert not bad, (
            "技术债台账条目不可执行（缺 owner/动作/期限 或 动作非法）：\n%s"
            % "\n".join("    " + b for b in bad)
        )

    def test_dead_module_count_is_decreasing(self):
        """★ 递减棘轮：孤立模块数不得超过历史最低值

        这是 P0-11 的核心 —— 把"必须递减"变成**机器可执行的约束**。
        想放宽上限，必须在 `DEBT_CEILING_HISTORY` 里追加一条并写明原因，
        让"提高门槛"成为显式的、要评审的动作，而不是悄悄改个数字。
        """
        dead = _detect_dead_modules()
        ceiling = DEBT_CEILING

        over = sorted(dead - KNOWN_DEAD_MODULES)
        assert not over, (
            "检测到**未登记**的孤立模块（零 import）：\n%s\n\n"
            "处理方式二选一：接线，或删除；若确需保留，"
            "必须同时加入 KNOWN_DEAD_MODULES **和** DEBT_LEDGER（含 owner/期限）。"
            % "\n".join("    " + m for m in over)
        )

        assert len(dead) <= ceiling, (
            "★ 孤立模块数**回升**了：当前 %d 个 > 棘轮上限 %d 个。\n"
            "  P0-11 要求该数字只能下降。请接线或删除若干模块；\n"
            "  若确实需要放宽上限，必须在 DEBT_CEILING_HISTORY 追加一条并写明原因。\n"
            "  当前孤立模块：%s"
            % (len(dead), ceiling, sorted(dead))
        )

    def test_ceiling_history_is_monotonic(self):
        """棘轮历史只能下降：不得出现"先降到 3、又回到 10"的回填

        允许的例外只有一种 —— 在历史里**追加**一条比当前更高的上限并写明原因，
        这会让放宽门槛留下审计痕迹（下面的断言会明确提示该怎么做）。
        """
        counts = [c for _d, c, _n in DEBT_CEILING_HISTORY]
        assert counts, "DEBT_CEILING_HISTORY 不能为空"
        bad = [(i, counts[i - 1], counts[i])
               for i in range(1, len(counts)) if counts[i] > counts[i - 1]]
        assert not bad, (
            "DEBT_CEILING_HISTORY 出现上限回升（棘轮被回填）：%s\n"
            "  棘轮只允许下降。若确需放宽，请在该条目的说明里写清原因。" % (bad,)
        )
        assert min(counts) == DEBT_CEILING, (
            "DEBT_CEILING 应等于历史最低值 %d，实际 %d"
            % (min(counts), DEBT_CEILING)
        )

    def test_debt_volume_report(self):
        """打印债务体量（模块数 + 总行数），让"欠了多少"可见

        本测试**不做断言**（永远通过）—— 它的价值是把数字放进 CI 输出里，
        避免"债务只存在于某个人的记忆里"。
        """
        dead = _detect_dead_modules()
        total_lines = 0
        for mod in sorted(dead):
            path = os.path.join(ROOT, mod)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    total_lines += sum(1 for _ in fh)
            except OSError:
                pass
        wire = sum(1 for i in DEBT_LEDGER.values()
                   if i["action"] == DEBT_ACTION_WIRE)
        delete = sum(1 for i in DEBT_LEDGER.values()
                     if i["action"] == DEBT_ACTION_DELETE)
        print("\n[技术债体量] 孤立模块 %d 个 / %d 行；棘轮上限 %d"
              % (len(dead), total_lines, DEBT_CEILING))
        print("             处置计划：接线 %d 个，删除 %d 个"
              % (wire, delete))
        for mod in sorted(dead):
            info = DEBT_LEDGER.get(mod, {})
            print("               %-40s %-6s owner=%-9s due=%s"
                  % (mod, info.get("action", "未登记"),
                     info.get("owner", "-"), info.get("due", "-")))


# ============================================================
# 3. 端到端功能冒烟（真实执行）
# ============================================================
def _ensure_fonts():
    """注入字体：offscreen 下缺字体可能导致 segfault"""
    try:
        from PyQt5.QtGui import QFontDatabase
        for p in (r"C:\Windows\Fonts\consola.ttf",
                  r"C:\Windows\Fonts\msyh.ttc"):
            if os.path.isfile(p):
                QFontDatabase.addApplicationFont(p)
    except Exception:
        pass


def _make_editor_for_file(name):
    """按文件名构造真实 EditorWidget 并设置词法器"""
    _ensure_fonts()
    from core.content_provider import MemoryProvider
    from ui.editor_view import EditorWidget

    prov = MemoryProvider()
    prov.open(initial_text="")
    w = EditorWidget(provider=prov)
    w.set_lexer_by_filename(name)
    return w


class TestEndToEndSmoke:
    """真实执行，不只看静态代码"""

    @pytest.mark.parametrize("filename", [
        "sample.json", "sample.md", "sample.py", "sample.js",
        "sample.yaml", "sample.html", "sample.css", "sample.sql",
        "sample.xml", "sample.sh", "sample.diff",
    ])
    def test_lexer_assigned_for_common_extensions(self, qapp, filename):
        """P5: 打开常见扩展名文件必须有高亮（lexer 非 None）"""
        w = _make_editor_for_file(filename)
        try:
            assert w.lexer() is not None, (
                "%s 没有词法器（零高亮）—— 语法高亮映射未覆盖" % filename
            )
        finally:
            try:
                w.close()
            except Exception:
                pass

    def test_lexer_none_for_unknown_extension(self, qapp):
        """未知扩展名应为 None 且不抛异常（优雅降级）"""
        w = _make_editor_for_file("sample.zzz_unknown")
        try:
            assert w.lexer() is None
        finally:
            try:
                w.close()
            except Exception:
                pass

    def test_log_extension_still_uses_custom_lexer(self, qapp):
        """回归：.log 仍走自定义 LogLexer"""
        w = _make_editor_for_file("app.log")
        try:
            assert w.lexer() is not None, ".log 的自定义词法器丢了"
        finally:
            try:
                w.close()
            except Exception:
                pass

    def test_save_autosave_writes_meta_json(self, qapp, tmp_path):
        """P1 生产者: save_autosave 真的写出 meta.json（崩溃恢复前提）"""
        from app.session import SessionManager

        asd = str(tmp_path / "autosave")
        mgr = SessionManager(
            filepath=str(tmp_path / "session.json"), enabled=True)
        mgr.autosave_dir = asd

        class FakeSc:
            def text(self):
                return "UNSAVED CONTENT\nline2\n"

        class FakeDoc:
            filepath = str(tmp_path / "sample.txt")

        class FakeProxy:
            is_modified = True
            sc = FakeSc()
            document = FakeDoc()

        class FakeEditor:
            proxy = FakeProxy()

        class FakeTabs:
            def count(self):
                return 1

            def widget(self, i):
                return FakeEditor()

            def tabText(self, i):
                return "sample.txt"

        count = mgr.save_autosave(FakeTabs())
        assert count >= 1, "save_autosave 没有备份任何已修改文件"
        meta = os.path.join(asd, "meta.json")
        assert os.path.isfile(meta), (
            "save_autosave 未生成 meta.json（恢复前置条件恒为假）→ "
            "崩溃恢复不可用。目录内容=%s"
            % (os.listdir(asd) if os.path.isdir(asd) else "目录不存在")
        )

    def test_start_autosave_activates_timer(self, qapp, tmp_path):
        """P1: start_autosave() 后定时器必须处于活动状态"""
        from app.session import SessionManager

        mgr = SessionManager(
            filepath=str(tmp_path / "session.json"), enabled=True)
        assert not mgr._autosave_timer.isActive(), "初始应为未启动"
        mgr.start_autosave()
        assert mgr._autosave_timer.isActive(), (
            "start_autosave() 未启动定时器（enabled=True 时应启动）"
        )
        mgr.stop_autosave()

    def test_main_window_calls_start_autosave(self, qapp):
        """P1 接线（运行时）: MainWindow 构造后自动备份定时器应已启动

        端到端核心断言——同时覆盖"代码里写了调用"与"该调用真的执行到"。
        已接线：`ui/main_window.py` 构造末尾调用 `session.start_autosave()`。
        （原为 xfail；接线完成后摘掉标记，恢复为硬断言。）
        """
        _ensure_fonts()
        from ui.main_window import MainWindow
        win = MainWindow()
        try:
            assert win.session is not None, "MainWindow 未创建 SessionManager"
            assert win.session._autosave_timer.isActive(), (
                "MainWindow 构造后自动备份定时器未启动 → "
                "崩溃恢复生产者永不运行（P1 未接线）。\n"
                "    期望：ui/main_window.py 里调用 "
                "self.session.start_autosave()"
            )
        finally:
            try:
                win.close()
            except Exception:
                pass

    def test_draft_dir_matches_ensure_directories(self):
        """草稿目录必须**只有一处定义**

        改造前：``core/document.py`` 写 ``<root>/backup/drafts``，
        而 ``main.py`` 建的是 ``<root>/data/drafts`` —— 同一个概念在两处
        各自定义，路径必然漂移。

        修复方式（重要）：不是把某一处改成另一处的字面量，而是让
        ``main.py`` **直接复用写入端的定义** ``DocumentModel._draft_dir()``。
        因此本测试断言"两处解析到同一个真实路径 + main.py 确实在复用"，
        而不是匹配某种字面写法 —— 这样实现日后改用常量，测试仍有效。
        """
        from core.document import Document

        draft_dir = Document._draft_dir()
        assert os.path.isabs(draft_dir), (
            "草稿目录必须是绝对路径（相对路径会随工作目录漂移）：%r"
            % draft_dir
        )

        main_src = _read(os.path.join(ROOT, "main.py"))
        assert "_draft_dir()" in main_src, (
            "main.py 的 ensure_directories 未复用 "
            "Document._draft_dir() —— 两处各自定义目录正是路径漂移"
            "的根因，请改为引用同一来源"
        )
        assert "drafts_dir" in main_src, (
            "main.py 算出 drafts_dir 后未纳入 makedirs 清单"
        )

    def test_panel_object_names_unique(self, qapp):
        """所有面板 objectName 必须唯一（防重复注册）"""
        _ensure_fonts()
        from PyQt5.QtWidgets import QDockWidget

        from ui.main_window import MainWindow

        win = MainWindow()
        try:
            for name in win._LAZY_PANELS:
                try:
                    win._ensure_panel(name)
                except Exception:
                    pass
            names = [d.objectName() for d in win.findChildren(QDockWidget)
                     if d.objectName()]
            dups = sorted({n for n in names if names.count(n) > 1})
            assert not dups, "面板 objectName 重复：%s" % dups
            assert "DirectoryTreeDock" in names, (
                "默认面板目录树未构造（objectName 缺失）"
            )
        finally:
            try:
                win.close()
            except Exception:
                pass

    def test_default_panels_visible(self, qapp):
        """回归防线：默认面板必须可见（此前"界面全空"缺陷）"""
        _ensure_fonts()
        from PyQt5.QtWidgets import QDockWidget

        from ui.main_window import MainWindow

        win = MainWindow()
        win.show()
        try:
            qapp.processEvents()
            visible = {d.objectName() for d in win.findChildren(QDockWidget)
                       if d.isVisible()}
            assert "DirectoryTreeDock" in visible, (
                "项目目录树默认不可见，可见面板=%s" % sorted(visible)
            )
        finally:
            try:
                win.close()
            except Exception:
                pass
