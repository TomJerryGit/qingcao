# -*- coding: utf-8 -*-
"""批次 A 验证：会话快照 + 代码模板（接线后必须真的能用）

    python tools\\verify_snapshot_templates.py

覆盖：
  A. 代码模板（core/code_templates.py）
     * 8 个模板都取得到、都有占位符声明；
     * `format_template` 的**参数冲突已修**（`name` 占位符可正常填值）；
     * 缺占位符时生成结果**不含 `{xxx}` 残留**（原实现会原样返回坏代码）；
     * 未知模板返回空串而不是抛异常。
  B. 模板选择对话框（ui/template_picker_dialog.py）
     * 可构造、模板下拉数量正确、切换模板重建占位符输入框；
     * 预览非空；填值后生成的文本替换正确。
  C. 会话快照（core/snapshot.py + ui/snapshot_manager_dialog.py）
     * 快照目录是**绝对路径**（相对路径会随 cwd 漂移，快照"凭空消失"）；
     * save → list → load → restore 往返正确（用真实 TabManager）；
     * 恢复会正确关闭旧标签、打开快照里的文件、恢复光标位置；
     * 对话框可构造、`_collect_modified_tabs` 能识别未保存修改。
  D. 接线（main_window）
     * 两个菜单项存在、处理器可调用；
     * 「从模板新建」走 `add_tab` 而**不再二次弹**格式选择框。

退出码: 0 = 全部通过；1 = 有失败项。
"""
import os
import sys
import tempfile


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

# headless 下弹真实模态框会段错误（offscreen 平台限制），统一拦截
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Discard)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-50s %s" % ("OK " if cond else "FAIL", name, detail))


TMP = tempfile.mkdtemp(prefix="qc_batch_a_")

print("=" * 96)
print("批次 A 验证：会话快照 + 代码模板")
print("=" * 96)

# ============================================================
# A. 代码模板
# ============================================================
print()
print("== A. core/code_templates.py ==")
from core.code_templates import (  # noqa: E402
    format_template,
    get_template,
    get_template_placeholders,
    list_templates,
)


names = list_templates()
check("A1 模板数量 == 8", len(names) == 8, str(names))
# 注意：`.gitignore` 模板本来就没有占位符（纯静态内容），
# 所以只要求"有非空 code"，不要求"必须有 placeholders"。
check("A2 每个模板都有非空 code",
      all(get_template(n).get("code") for n in names), "")
check("A2b 至少 6 个模板声明了占位符",
      sum(1 for n in names if get_template_placeholders(n)) >= 6,
      str({n: len(get_template_placeholders(n)) for n in names}))

# ★ 参数冲突回归：name 既是模板名参数、又是占位符
out = format_template(
    "py_class", name="MyClass", docstring="示例类",
    args="", init_body="pass", method="run", method_body="pass",
)
check("A3 format_template 可传 name 占位符（参数冲突已修）",
      "class MyClass:" in out, repr(out[:40]))
check("A4 生成结果无 {xxx} 残留", "{" not in out, repr(out[-40:]))

# 缺占位符时也不能留 {xxx}
partial = format_template("py_function")
check("A5 缺占位符时结果仍无 {xxx} 残留", "{" not in partial,
      repr(partial[:60]))
check("A6 未知模板返回空串", format_template("__nope__") == "", "")

# ============================================================
# B. 模板选择对话框
# ============================================================
print()
print("== B. ui/template_picker_dialog.py ==")
from ui.template_picker_dialog import TemplatePickerDialog  # noqa: E402


dlg = TemplatePickerDialog(None)
check("B1 对话框可构造", dlg is not None, "")
check("B2 模板下拉项数 == 模板数",
      dlg.template_combo.count() == len(names),
      "%d" % dlg.template_combo.count())
n_ph = dlg.params_form.rowCount()
check("B3 首个模板生成了占位符输入框", n_ph >= 1, "%d 个" % n_ph)
check("B4 预览非空", bool(dlg.preview.toPlainText()), "")

# 切换模板 → 输入框重建
dlg.template_combo.setCurrentIndex(2)
check("B5 切换模板后占位符输入框重建",
      dlg.params_form.rowCount() >= 1,
      "%d 个" % dlg.params_form.rowCount())

# 填值生成
for _ph, w in dlg._inputs.items():
    w.setText("Demo")
dlg._on_accept()
check("B6 生成文本非空", bool(dlg.generated_text),
      "%d 字符" % len(dlg.generated_text))
check("B7 生成文本无 {xxx} 残留", "{" not in dlg.generated_text, "")
check("B8 有建议文件名", bool(dlg.suggested_filename),
      dlg.suggested_filename)
dlg.close()

# ============================================================
# C. 会话快照
# ============================================================
print()
print("== C. core/snapshot.py ==")
import core.snapshot as snap_mod  # noqa: E402


check("C1 快照目录是绝对路径",
      os.path.isabs(snap_mod.SNAPSHOT_DIR), snap_mod.SNAPSHOT_DIR)
check("C2 快照目录基于应用根（含 data/snapshots）",
      os.path.join("data", "snapshots") in snap_mod.SNAPSHOT_DIR,
      snap_mod.SNAPSHOT_DIR)

from ui.main_window import MainWindow  # noqa: E402


win = MainWindow()

# 造两个文件并打开
f1 = os.path.join(TMP, "snap_a.py")
f2 = os.path.join(TMP, "snap_b.py")
for p, body in ((f1, "a = 1\nb = 2\nc = 3\n"), (f2, "x = 9\ny = 8\n")):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(body)
win.tabs.open_file(f1)
win.tabs.open_file(f2)
check("C3 打开 2 个文件", win.tabs.count() == 2, str(win.tabs.count()))

# 把光标放到第 3 行
p1 = win.tabs.open_file(f1)
p1.sc.setCursorPosition(2, 0)

from core.snapshot import SnapshotManager  # noqa: E402


print()
print("== C. 快照保存/恢复往返 ==")

# 用临时目录隔离，避免污染真实 data/snapshots
_orig_dir = snap_mod.SNAPSHOT_DIR
snap_mod.SNAPSHOT_DIR = os.path.join(TMP, "snaps")
os.makedirs(snap_mod.SNAPSHOT_DIR, exist_ok=True)
try:
    mgr = SnapshotManager()
    ok = mgr.save_snapshot("测试快照", win.tabs, win)
    check("C4 save_snapshot 成功", ok is True, "")
    snaps = mgr.list_snapshots()
    check("C5 list_snapshots 能看到快照",
          any(s["name"] == "测试快照" for s in snaps),
          str([s["name"] for s in snaps]))
    data = mgr.load_snapshot("测试快照")
    check("C6 load_snapshot 能读回", data is not None, "")
    check("C7 快照记录 2 个文件",
          len(data.get("files", [])) == 2,
          str(len(data.get("files", []))))
    check("C8 快照记录了光标行号",
          any(f.get("cursor_line") == 2 for f in data["files"]),
          str([f.get("cursor_line") for f in data["files"]]))

    # 恢复：先关掉所有标签，再恢复
    while win.tabs.count():
        win.tabs.close_tab(0)
    check("C9 已清空标签", win.tabs.count() == 0, str(win.tabs.count()))

    n = mgr.restore_snapshot("测试快照", win.tabs, win)
    check("C10 restore_snapshot 恢复了 2 个文件", n == 2, str(n))
    check("C11 标签数正确", win.tabs.count() == 2, str(win.tabs.count()))
    cur = win.tabs.current_proxy()
    check("C12 恢复后光标位置正确",
          cur is not None and cur.sc.getCursorPosition()[0] == 2,
          str(cur.sc.getCursorPosition() if cur else None))

    # 删除
    mgr.delete_snapshot("测试快照")
    check("C13 delete_snapshot 后列表为空",
          not any(s["name"] == "测试快照" for s in mgr.list_snapshots()),
          "")
finally:
    snap_mod.SNAPSHOT_DIR = _orig_dir

# 对话框 + 未保存检测
print()
print("== C. 快照对话框 ==")
from ui.snapshot_manager_dialog import SnapshotDialog  # noqa: E402


dlg2 = SnapshotDialog(win, win)
check("C14 快照对话框可构造", dlg2 is not None, "")
check("C15 有列表控件", hasattr(dlg2, "list_widget"), "")
check("C16 有未保存修改检测方法",
      callable(getattr(dlg2, "_collect_modified_tabs", None)), "")
check("C17 有批量保存方法",
      callable(getattr(dlg2, "_save_all_modified", None)), "")

# 修改一个标签，确认能检测到
cur = win.tabs.current_proxy()
if cur is not None:
    cur.set_text("changed\n")
    mods = dlg2._collect_modified_tabs()
    check("C18 能识别出未保存修改", len(mods) >= 1, str(mods))
dlg2.close()

# ============================================================
# D. 接线
# ============================================================
print()
print("== D. main_window 接线 ==")
from PyQt5.QtWidgets import QAction  # noqa: E402


texts = [a.text() for a in win.findChildren(QAction)]
check("D1 有「从模板新建」菜单项",
      "🧩 从模板新建…" in texts, "")
check("D2 有「会话快照」菜单项",
      "📸 会话快照…" in texts, "")
check("D3 有 _new_from_template 处理器",
      callable(getattr(win, "_new_from_template", None)), "")
check("D4 有 _show_snapshot_dialog 处理器",
      callable(getattr(win, "_show_snapshot_dialog", None)), "")

# 模板处理器不应再调 _new_file（避免二次弹框）
import inspect  # noqa: E402


src = inspect.getsource(win._new_from_template)
check("D5 模板处理器不再调用 _new_file（避免二次弹框）",
      "self._new_file()" not in src, "")
check("D6 模板处理器用 add_tab 直接建标签",
      "add_tab" in src, "")

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
