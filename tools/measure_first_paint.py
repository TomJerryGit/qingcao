# -*- coding: utf-8 -*-
"""测量首帧绘制：首次 Paint 时间 + 前 500ms 绘制/Polish 次数。"""

import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QObject  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication([])
import main as _main  # noqa: E402


_main.load_theme(app)
from ui.main_window import MainWindow  # noqa: E402


counter = {"paint": 0, "polish": 0, "first": None}


class _F(QObject):
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Paint:
            counter["paint"] += 1
            if counter["first"] is None:
                counter["first"] = time.perf_counter()
        elif ev.type() == QEvent.Polish:
            counter["polish"] += 1
        return False


f = _F()
app.installEventFilter(f)
t0 = time.perf_counter()
win = MainWindow()
t_build = time.perf_counter() - t0
counter["first"] = None
win.show()
deadline = time.time() + 2
while time.time() < deadline and counter["first"] is None:
    app.processEvents()
t_first = (counter["first"] - t0) if counter["first"] else -1
end = time.time() + 0.5
while time.time() < end:
    app.processEvents()
print(
    "[paint] MainWindow %.3fs 首帧 %.3fs paint500=%d polish500=%d"
    % (t_build, t_first, counter["paint"], counter["polish"])
)
win.close()
