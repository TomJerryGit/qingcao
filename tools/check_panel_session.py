# -*- coding: utf-8 -*-
"""验证面板布局的保存/恢复闭环（含"零面板不得覆盖布局"的回归）

此前缺陷：
  * 面板延迟构造 → 启动时无面板 → 保存采集到空 docks → 覆盖用户布局
  * 会话记录了面板，但 `_restore_docks` 只遍历已存在的 dock，
    未构造的面板永远无法恢复
"""
import io
import json
import os
import sys
import time


sys.path.insert(0, r"D:\QingCaoEditor")
os.chdir(r"D:\QingCaoEditor")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication, QDockWidget  # noqa: E402


app = QApplication([])

from ui.main_window import MainWindow  # noqa: E402


SESSION = os.path.join(os.getcwd(), "session.json")
OUT = []


def log(s=""):
    OUT.append(str(s))
    print(s, flush=True)


def settle(w, seconds=1.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def new_window():
    w = MainWindow()
    w.show()
    end = time.time() + 25
    while time.time() < end:
        app.processEvents()
        pm = getattr(w, "plugin_manager", None)
        if pm and len(getattr(getattr(pm, "loader", None),
                              "specs", None) or {}) >= 10:
            break
        time.sleep(0.05)
    settle(w, 1.5)
    return w


def visible_names(w):
    return sorted(d.objectName() or d.windowTitle()
                  for d in w.findChildren(QDockWidget) if d.isVisible())


log("=" * 70)
log("面板布局 保存/恢复 闭环验证")
log("=" * 70)

# ---------- 场景 1：全新用户 ----------
if os.path.exists(SESSION):
    os.remove(SESSION)
log()
log("场景1 全新用户（无 session.json）")
w = new_window()
log("  默认可见面板: %s" % visible_names(w))
log("  期望包含: DirectoryTreeDock / GlobalSearchPanel / "
    "PluginsPanel / PerfMonitor")

# ---------- 场景 2：保存布局 ----------
log()
log("场景2 调整布局后保存")
w._ensure_panel('outline')
w._show_panel('outline')
w._show_panel('minimap')
settle(w, 0.5)
before = visible_names(w)
log("  保存前可见: %s" % before)
try:
    w.session.save_now()
    if hasattr(w.session, 'flush'):
        w.session.flush()
except Exception as e:
    log("  save_now 异常: %s" % e)
settle(w, 1.0)
w.close()
settle(w, 0.5)

if os.path.exists(SESSION):
    data = json.load(io.open(SESSION, encoding="utf-8"))
    docks = data.get("docks", {})
    log("  session.json 记录面板数: %d" % len(docks))
    for k, v in sorted(docks.items()):
        log("      %-24s visible=%s" % (k, v.get("visible")))
else:
    log("  !! session.json 未生成")

# ---------- 场景 3：恢复布局 ----------
log()
log("场景3 重新启动，应恢复上面的布局")
w2 = new_window()
after = visible_names(w2)
log("  恢复后可见: %s" % after)
log("  与保存前一致: %s" % (set(after) == set(before)))

# ---------- 场景 4：零面板不得覆盖布局（回归防线）----------
log()
log("场景4 回归：全部面板隐藏后保存，不得把布局清空")
for d in w2.findChildren(QDockWidget):
    d.setVisible(False)
settle(w2, 0.5)
log("  隐藏后可见: %s" % visible_names(w2))
try:
    w2.session.save_now()
except Exception as e:
    log("  save_now 异常: %s" % e)
settle(w2, 0.8)
if os.path.exists(SESSION):
    d2 = json.load(io.open(SESSION, encoding="utf-8")).get("docks", {})
    log("  保存后面板记录数: %d（应为 8，不得为 0）" % len(d2))
    log("  记录被清空: %s" % (len(d2) == 0))
w2.close()

log()
log("=" * 70)
with io.open(os.path.join(os.getcwd(), "panel_session_check.txt"), "w",
             encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("[check] 已写出 panel_session_check.txt")
