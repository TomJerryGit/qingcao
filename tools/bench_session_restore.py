# -*- coding: utf-8 -*-
"""会话恢复成本测量：不同文件数下恢复耗时。"""

import os
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication([])
import main as _main  # noqa: E402


_main.load_theme(app)
from ui.main_window import MainWindow  # noqa: E402


tmp = tempfile.mkdtemp(prefix="qc_session_bench_")
files = []
for i in range(20):
    p = os.path.join(tmp, "f%02d.txt" % i)
    with open(p, "w", encoding="utf-8") as f:
        f.write(("line %d abcdefghij\n" % i) * 2000)
    files.append(p)

for n in (1, 5, 10, 20):
    win = MainWindow()
    try:
        for p in files[:n]:
            win.tabs.open_file(p)
        app.processEvents()
        win.save_session()
        win.close()
        app.processEvents()
        t0 = time.perf_counter()
        win2 = MainWindow()
        win2.restore_session()
        dt = time.perf_counter() - t0
        print("[session] n=%2d restore=%.3fs tabs=%d" % (n, dt, win2.tabs.count()))
        win2.close()
        app.processEvents()
    finally:
        try:
            win.close()
        except Exception:
            pass
