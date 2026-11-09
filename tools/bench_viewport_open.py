# -*- coding: utf-8 -*-
"""50MB 大文件视口优先加载基准（v2.24 W3 原型）。

    python tools/bench_viewport_open.py
对比 QINGCAO_VIEWPORT_LOAD=0/1 的首次可视时间与完整加载时间。
"""

import json
import os
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "docs", "perf_viewport_prototype.md")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _make_file(path, lines=3_000_000):
    with open(path, "wb") as f:
        f.write(b"hello world 12345\n" * lines)
    return lines + 1


def run_once(path, viewport):
    os.environ["QINGCAO_VIEWPORT_LOAD"] = "1" if viewport else "0"
    os.environ.setdefault("QINGCAO_VIEWPORT_THRESHOLD_MB", "8")
    os.environ.setdefault("QINGCAO_VIEWPORT_PREFIX_MB", "2")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PyQt5.Qsci import QsciScintilla
    from PyQt5.QtWidgets import QApplication

    from core.document import Document
    from core.editor import EditorProxy

    app = QApplication.instance() or QApplication([])
    sc = QsciScintilla()
    doc = Document()
    proxy = EditorProxy(sc, doc)
    t0 = time.perf_counter()
    ok = proxy.open_file(path)
    first = None
    # 视口模式：open_file 返回时首屏已完成（后台补齐由事件循环驱动）
    if getattr(proxy, "_viewport_ready", False):
        first = time.perf_counter() - t0
    total = getattr(proxy, "_load_total", 0) or 0
    deadline = time.time() + 120
    while first is None and time.time() < deadline:
        app.processEvents()
        if getattr(proxy, "_viewport_ready", False):
            first = time.perf_counter() - t0
            break
        time.sleep(0.002)
    while time.time() < deadline:
        app.processEvents()
        cur = getattr(proxy, "_load_cursor", 0)
        if total and cur >= total:
            break
        time.sleep(0.002)
    full = time.perf_counter() - t0
    lines = sc.lines()
    try:
        proxy.close()
    except Exception:
        pass
    return {
        "ok": bool(ok),
        "first_paint_s": round(first or full, 3),
        "full_load_s": round(full, 3),
        "lines": int(lines),
        "deferred_done": not bool(getattr(proxy, "_deferred_loading", False)),
    }


def main():
    tmp = tempfile.mkdtemp(prefix="qc_viewport_")
    path = os.path.join(tmp, "huge.txt")
    try:
        expected = _make_file(path)
        off = run_once(path, viewport=False)
        on = run_once(path, viewport=True)
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    speed = (off["first_paint_s"] / on["first_paint_s"]) if on["first_paint_s"] else 0
    print("[viewport] off:", json.dumps(off, ensure_ascii=False))
    print("[viewport] on :", json.dumps(on, ensure_ascii=False))
    print("[viewport] 首次可视加速: %.2fx" % speed)
    lines = [
        "# 50MB 大文件视口优先加载原型（v2.24 W3）",
        "",
        "> 开关：`QINGCAO_VIEWPORT_LOAD=1`（默认关闭）",
        "",
        "| 模式 | 首次可视 | 完整加载 | 行数 |",
        "|---|---|---|---|",
        "| 关闭（原同步加载） | %.3fs | %.3fs | %d |"
        % (off["first_paint_s"], off["full_load_s"], off["lines"]),
        "| 开启（视口优先） | %.3fs | %.3fs | %d |"
        % (on["first_paint_s"], on["full_load_s"], on["lines"]),
        "",
        "**首次可视加速：%.2fx**" % speed,
        "",
        "## 原理",
        "- 大文件先同步加载前 2MB（约数万行）立即 `setText` 显示；",
        "- 剩余内容由后台几何递增批量 append（断开修改信号、完成后清理脏标记）；",
        "- 默认关闭，待验证后作为大文件默认策略。",
        "",
        "## 限制",
        "- 加载完成前全文搜索/列编辑只作用于已加载部分（需 UI 提示）；",
        "- 完整加载时间可能略增（append 开销），收益在首次可视与交互响应。",
        "",
    ]
    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("[viewport] 报告:", REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
