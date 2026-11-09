# -*- coding: utf-8 -*-
"""v2.22 P2 体验冒烟（自动部分）

终端多标签/ANSI、多语言包、市场注册表本地/在线校验；
生成 docs/smoke_report_v2.22.md（人工步骤见 docs/smoke_checklist_v2.22.md）。
    python tools/smoke_check.py
"""

import io
import json
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "smoke_report_v2.22.md")
results = []


def record(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))


def smoke_terminal():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    try:
        from ui.terminal_panel import TerminalPanel, ansi_to_html

        record("ANSI 转换", "#e06c75" in ansi_to_html("\x1b[31mred\x1b[0m"))
        panel = TerminalPanel(None)
        try:
            record("终端默认标签", panel.tabs.count() == 1)
            panel.add_tab()
            record("终端新建标签", panel.tabs.count() == 2)
            panel.input.setText("echo qc-smoke-ok")
            panel.run_command()
            deadline = time.time() + 25
            while time.time() < deadline and panel._proc is not None:
                app.processEvents()
                time.sleep(0.02)
            text = panel.output.toPlainText()
            record("终端执行命令", "qc-smoke-ok" in text, text[-60:])
        finally:
            panel.close()
    except Exception as e:
        record("终端冒烟", False, repr(e))


def smoke_i18n():
    try:
        from core.i18n_json import AVAILABLE, clear_cache, tr

        record("语言数量", len(AVAILABLE) >= 5, ",".join(AVAILABLE))
        for lang, sample_key, sample_val in (
            ("zh_TW", "保存", "儲存"),
            ("ja_JP", "文件", "ファイル"),
            ("ko_KR", "保存", "저장"),
        ):
            os.environ["QINGCAO_LANG"] = lang
            clear_cache()
            record("语言 %s" % lang, tr(sample_key) == sample_val, tr(sample_key))
        os.environ.pop("QINGCAO_LANG", None)
        clear_cache()
    except Exception as e:
        record("多语言冒烟", False, repr(e))


def smoke_market(offline=False):
    try:
        path = os.path.join(ROOT, "data", "registry_github", "registry.json")
        if not os.path.isfile(path) and offline:
            record("市场冒烟", True, "离线模式：跳过网络检查")
            return
        if not os.path.isfile(path):
            # 本地没有构建产物时，尝试线上 Release API
            import urllib.request

            req = urllib.request.Request(
                "https://api.github.com/repos/TomJerryGit/qingcao/releases/tags/plugin-registry"
            )
            req.add_header("User-Agent", "qc-smoke")
            rel = json.loads(urllib.request.urlopen(req, timeout=20).read())
            record(
                "市场 Release 存在",
                bool(rel.get("assets")),
                str(len(rel.get("assets", []))) + " assets",
            )
            return
        data = json.load(io.open(path, encoding="utf-8"))
        plugins = data.get("plugins", [])
        record("市场插件数", len(plugins) >= 1, str(len(plugins)))
        signed = all(p.get("file_hash") and p.get("signature") for p in plugins)
        record("市场签名完整", signed)
    except Exception as e:
        record("市场冒烟", False, repr(e))


def render():
    lines = [
        "# v2.22 P2 体验冒烟报告（自动部分）",
        "",
        "> 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M"),
        "> 自动部分覆盖终端/多语言/市场本地与在线只读检查；人工步骤见 "
        "`docs/smoke_checklist_v2.22.md`。",
        "",
        "| 检查项 | 结果 | 详情 |",
        "|---|---|---|",
    ]
    for name, ok, detail in results:
        lines.append(
            "| %s | %s | %s |"
            % (name, "✅ PASS" if ok else "❌ FAIL", detail.replace("|", "\\|")[:80])
        )
    passed = sum(1 for _, ok, _ in results if ok)
    lines += ["", "合计：%d/%d 通过" % (passed, len(results)), ""]
    return "\n".join(lines)


def main():
    offline = os.environ.get("QINGCAO_SMOKE_OFFLINE") == "1"
    smoke_terminal()
    smoke_i18n()
    smoke_market(offline=offline)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(render())
    passed = sum(1 for _, ok, _ in results if ok)
    print("[smoke] %d/%d 通过 -> %s" % (passed, len(results), OUT))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
