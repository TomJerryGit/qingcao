# -*- coding: utf-8 -*-
"""批次 B 验证：项目概念（工作区 + 项目配置 + 任务面板）

    python tools\\verify_project.py

三个模块共享同一个「项目根」语义，本脚本验证这条链路端到端可用：

  A. 菜单：项目菜单存在且位置正确（在「文件」之后、「编辑」之前）
  B. 打开项目：
     * `_set_project()` 设置项目根；
     * 项目根记进 Workspace 并**持久化**到 data/workspace.json；
     * `.qingcao/settings.json` 被加载；
     * 「最近项目」子菜单出现该项；
  C. 项目设置：
     * `_apply_project_settings()` 把 tab_width / 缩进方式真的作用到编辑器；
     * 设置对话框可构造、保存后能读回；
  D. 任务面板：
     * 面板可构造、加入 `_LAZY_PANELS`；
     * `.qingcao/tasks.json` 与旧版 `.qingcao-tasks.json` **都能读**；
     * `set_project()` 后任务树出现对应任务；
     * TaskRunner 能真的执行命令并拿到输出（用 python -c 做无害任务）；
  E. 关闭项目：状态被清空，任务面板解绑。

退出码: 0 = 全部通过；1 = 有失败项。
"""
import json
import os
import sys
import tempfile
import time


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PyQt5.QtGui import QFontDatabase  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402


app = QApplication.instance() or QApplication([])
for _fp in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(_fp):
        QFontDatabase.addApplicationFont(_fp)

# headless 下真实模态框会段错误（offscreen 平台限制），统一拦截
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Discard)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-52s %s" % ("OK " if cond else "FAIL", name, detail))


TMP = tempfile.mkdtemp(prefix="qc_proj_")

print("=" * 96)
print("批次 B 验证：项目概念（工作区 + 项目配置 + 任务面板）")
print("=" * 96)

# ============================================================
# A. 菜单
# ============================================================
print()
print("== A. 项目菜单 ==")
from PyQt5.QtWidgets import QAction  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


win = MainWindow()

tops = [a.text() for a in win.menuBar().actions()]
check("A1 一级菜单含「项目」", "项目(&P)" in tops, str(tops))
try:
    i_file = tops.index("文件(&F)")
    i_proj = tops.index("项目(&P)")
    i_edit = tops.index("编辑(&E)")
    check("A2 项目菜单位于「文件」之后、「编辑」之前",
          i_file < i_proj < i_edit,
          "文件@%d 项目@%d 编辑@%d" % (i_file, i_proj, i_edit))
except ValueError:
    check("A2 项目菜单位置正确", False, str(tops))

texts = [a.text() for a in win.findChildren(QAction)]
for want in ("📁 打开项目…", "⚙ 项目设置…", "❌ 关闭项目", "🕘 最近项目"):
    check("A3 菜单项 %s 存在" % want, want in texts, "")

# ============================================================
# B. 打开项目
# ============================================================
print()
print("== B. 打开项目 ==")
proj = os.path.join(TMP, "myproj")
os.makedirs(os.path.join(proj, ".qingcao"), exist_ok=True)
with open(os.path.join(proj, ".qingcao", "settings.json"),
          "w", encoding="utf-8") as f:
    json.dump({"tab_width": 8, "use_spaces": False, "eol": "\r\n"}, f)
with open(os.path.join(proj, ".qingcao", "tasks.json"),
          "w", encoding="utf-8") as f:
    json.dump({"tasks": [
        {"label": "echo-hi", "command": sys.executable,
         "args": ["-c", "print('HELLO_FROM_TASK')"], "group": "demo"},
    ]}, f)
# 造一个文件并打开，用于验证设置应用
sample = os.path.join(proj, "a.py")
with open(sample, "w", encoding="utf-8", newline="") as f:
    f.write("a = 1\nb = 2\n")
win.tabs.open_file(sample)

# 隔离 workspace 路径，避免污染真实 data/
win._workspace_path = os.path.join(TMP, "workspace.json")

ok = win._set_project(proj)
check("B1 _set_project 返回 True", ok is True, "")
check("B2 current_project_root 正确",
      win.current_project_root() == os.path.abspath(proj),
      win.current_project_root())
check("B3 project_config 已加载",
      win.project_config is not None, "")
check("B4 读到项目设置 tab_width=8",
      win.project_config.get_setting("tab_width") == 8,
      str(win.project_config.get_setting("tab_width")))
check("B5 项目根记进 workspace",
      win.workspace is not None
      and win.workspace.has_folder(os.path.abspath(proj)),
      "")
check("B6 workspace 已持久化到磁盘",
      os.path.isfile(win._workspace_path),
      win._workspace_path)
if os.path.isfile(win._workspace_path):
    with open(win._workspace_path, encoding="utf-8") as f:
        ws_data = json.load(f)
    check("B7 持久化内容含该项目",
          any(os.path.abspath(p) == os.path.abspath(proj)
              for p in json.dumps(ws_data).split('"')
              if os.path.sep in p),
          str(ws_data)[:100])

# 最近项目菜单
try:
    recent = win._recent_menu
    acts = [a.text() for a in recent.actions() if a.text()]
    check("B8 「最近项目」出现该项目",
          any(os.path.basename(proj) in t or proj in t for t in acts),
          str(acts[:3]))
except Exception as e:
    check("B8 「最近项目」出现该项目", False, str(e))

# ============================================================
# C. 项目设置生效
# ============================================================
print()
print("== C. 项目设置应用到编辑器 ==")
proxy = win.tabs.current_proxy()
check("C1 当前有编辑器", proxy is not None, "")
if proxy is not None:
    try:
        check("C2 tab 宽度应用为 8",
              proxy.sc.tabWidth() == 8, str(proxy.sc.tabWidth()))
    except Exception as e:
        check("C2 tab 宽度应用为 8", False, str(e))
    try:
        check("C3 缩进方式为 Tab（use_spaces=False）",
              proxy.sc.indentationsUseTabs() is True,
              str(proxy.sc.indentationsUseTabs()))
    except Exception as e:
        check("C3 缩进方式为 Tab", False, str(e))

# 设置对话框
from ui.mixins.project_mixin import ProjectSettingsDialog  # noqa: E402


dlg = ProjectSettingsDialog(win.project_config, proj, win)
check("C4 设置对话框可构造", dlg is not None, "")
check("C5 回显 tab_width=8", dlg.tab_spin.value() == 8,
      str(dlg.tab_spin.value()))
dlg.tab_spin.setValue(2)
dlg.spaces_cb.setChecked(True)
dlg._on_accept()
check("C6 保存后读回 tab_width=2",
      win.project_config.get_setting("tab_width") == 2,
      str(win.project_config.get_setting("tab_width")))
# 重新应用
win._apply_project_settings()
if proxy is not None:
    try:
        check("C7 重新应用后编辑器 tab 宽度=2",
              proxy.sc.tabWidth() == 2, str(proxy.sc.tabWidth()))
    except Exception as e:
        check("C7 重新应用后编辑器 tab 宽度=2", False, str(e))

# ============================================================
# D. 任务面板
# ============================================================
print()
print("== D. 任务面板 ==")
check("D1 'task' 在 _LAZY_PANELS 中", 'task' in win._LAZY_PANELS, "")
check("D2 _ensure_panel('task') 成功", win._ensure_panel('task') is True, "")
check("D3 self.task 是 TaskPanel",
      type(getattr(win, 'task', None)).__name__ == "TaskPanel",
      type(getattr(win, 'task', None)).__name__)
panel = getattr(win, 'task', None)
if panel is not None:
    # 打开项目时已 set_project → 任务树应有任务
    check("D4 任务树已加载项目任务",
          panel.task_tree.topLevelItemCount() >= 1,
          "%d 组" % panel.task_tree.topLevelItemCount())
    # 旧版 .qingcao-tasks.json 也要能读
    proj2 = os.path.join(TMP, "oldstyle")
    os.makedirs(proj2, exist_ok=True)
    with open(os.path.join(proj2, ".qingcao-tasks.json"),
              "w", encoding="utf-8") as f:
        json.dump({"tasks": [{"label": "legacy", "command": "echo",
                              "args": ["x"], "group": "g"}]}, f)
    from core.project_tasks import ProjectTaskManager
    mgr = ProjectTaskManager(proj2)
    mgr.load_tasks()
    check("D5 支持旧版 .qingcao-tasks.json", len(mgr.tasks) == 1,
          "%d 个" % len(mgr.tasks))
    mgr2 = ProjectTaskManager(proj)
    mgr2.load_tasks()
    check("D6 支持新版 .qingcao/tasks.json", len(mgr2.tasks) == 1,
          "%d 个" % len(mgr2.tasks))

    # 真跑一个无害任务
    outputs = []
    finished = []
    panel.runner.task_output.connect(lambda s: outputs.append(s))
    panel.runner.task_finished.connect(
        lambda label, code: finished.append((label, code)))
    task = mgr2.find_task("echo-hi")
    check("D7 能找到 echo-hi 任务", task is not None, "")
    if task is not None:
        panel.runner.run(task, proj)
        deadline = time.time() + 20
        while time.time() < deadline and not finished:
            app.processEvents()
            time.sleep(0.02)
        check("D8 任务执行完成", bool(finished), str(finished))
        check("D9 捕获到任务输出",
              any("HELLO_FROM_TASK" in o for o in outputs),
              str(outputs[:2]))
        check("D10 退出码为 0",
              bool(finished) and finished[0][1] == 0, str(finished[:1]))

# ============================================================
# E. 关闭项目
# ============================================================
print()
print("== E. 关闭项目 ==")
win._close_project()
check("E1 current_project_root 清空",
      win.current_project_root() == "", repr(win.current_project_root()))
check("E2 project_config 清空", win.project_config is None, "")
if panel is not None:
    check("E3 任务面板已解绑",
          getattr(panel, 'task_manager', None) is None, "")

# ============================================================
# 汇总
# ============================================================
print()
print("=" * 96)
print("结果：通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
print("=" * 96)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)

try:
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
except Exception:
    pass
sys.exit(1 if FAIL else 0)
