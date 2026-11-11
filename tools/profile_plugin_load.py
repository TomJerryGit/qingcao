# -*- coding: utf-8 -*-
"""插件加载专项分析：按插件计时 + cProfile 热点。"""
import cProfile
import os
import pstats
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
import main as _main  # noqa: E402

_main.load_theme(app)
from infrastructure.plugin_loader import PluginLoader  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

times = {}
orig = PluginLoader._load_plugin


def wrap(self, spec):
    t = time.perf_counter()
    try:
        return orig(self, spec)
    finally:
        times[spec.name] = round(time.perf_counter() - t, 3)


PluginLoader._load_plugin = wrap
prof = cProfile.Profile()
prof.enable()
t0 = time.perf_counter()
win = MainWindow()
t_main = time.perf_counter() - t0
deadline = time.time() + 20
while time.time() < deadline:
    app.processEvents()
    pm = getattr(win, "plugin_manager", None)
    ld = getattr(pm, "loader", None) if pm else None
    specs = getattr(ld, "specs", {}) or {}
    active = sum(1 for s in specs.values() if "ACTIVATED" in str(getattr(s, "state", "")))
    if pm is not None and active >= 10:
        break
    time.sleep(0.01)
t_all = time.perf_counter() - t0
prof.disable()
print("[profile] MainWindow %.3fs，插件全就绪累计 %.3fs" % (t_main, t_all))
print("[profile] 各插件加载耗时:")
for name, sec in sorted(times.items(), key=lambda kv: -kv[1]):
    print("    %-22s %6.3f s" % (name, sec))
print("[profile] cProfile 热点（cumulative）:")
stats = pstats.Stats(prof)
stats.sort_stats("cumulative").print_stats(18)
win.close()
