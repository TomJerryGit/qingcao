# -*- coding: utf-8 -*-
"""验证跨模块分析中的关键结论（实测，不靠读代码）"""
import os
import sys


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PyQt5.QtGui import QFontDatabase  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication([])
for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(p):
        QFontDatabase.addApplicationFont(p)

print("=" * 92)
print("跨模块结论实测验证")
print("=" * 92)

# ---------------------------------------------------------------
# 验证 1：宏录制是否真的录不到（生产者缺失）
# ---------------------------------------------------------------
print()
print("[1] 宏录制（子调查称：MacroRecorder 无 undo_manager -> 录到 0 条）")
try:
    import inspect

    from core.macro import MacroRecorder

    sig = inspect.signature(MacroRecorder.__init__)
    print("    MacroRecorder.__init__ 签名: %s" % sig)

    # 复现 main_window.py:198 的构造方式（无 undo_manager）
    import re as _re

    t = open("ui/main_window.py", encoding="utf-8").read()
    m = _re.search(r"self\.macro\s*=\s*([^\n]+)", t)
    print("    main_window 构造语句: %s" % (m.group(1).strip() if m else "未找到"))

    rec = MacroRecorder()          # 与 main_window 一致的构造
    print("    MacroRecorder().undo_manager = %r" % rec.undo_manager)
    hook = getattr(rec, "_register_hook", None)
    if hook:
        before = None
        rec.start("m")
        from PyQt5.Qsci import QsciScintilla

        sc = QsciScintilla()
        sc.setUtf8(True)
        sc.setText("")
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"ABC")
        rec.stop()
        n = len(rec.current_macro.commands) if rec.current_macro else -1
        print("    ★ 录制结果：命令数 = %d（期望 >=1）" % n)
        print("    → 结论：%s" % ("宏录制确实录不到" if n == 0 else "宏录制可用"))
except Exception as e:
    print("    异常: %s: %s" % (type(e).__name__, e))

# ---------------------------------------------------------------
# 验证 2：一次保存是否发两次 didSave
# ---------------------------------------------------------------
print()
print("[2] 保存是否重复发送 didSave（子调查称 core/editor.py:766-770 被复制两遍）")
try:
    t = open("core/editor.py", encoding="utf-8").read()
    n = t.count("_notify_lsp_saved(filepath)")
    print("    '_notify_lsp_saved(filepath)' 出现次数 = %d" % n)
    # 定位上下文
    import re as _re

    for m in _re.finditer(r"_notify_lsp_saved\(filepath\)", t):
        line = t[:m.start()].count("\n") + 1
        print("      行 %d" % line)
    print("    → 结论：%s" % ("重复发送" if n >= 2 else "仅一次"))
except Exception as e:
    print("    异常: %s" % e)

# ---------------------------------------------------------------
# 验证 3：全局替换是否丢选项（正则/大小写）
# ---------------------------------------------------------------
print()
print("[3] 全局替换丢选项（子调查称 main_window.py:2646 默认 is_regex=False）")
try:
    t = open("ui/main_window.py", encoding="utf-8").read()
    i = t.find("def _on_global_replace")
    seg = t[i:i + 1500] if i > 0 else ""
    has_opts = "SearchOptions(" in seg
    import re as _re

    m = _re.search(r"SearchOptions\(([^)]*)\)", seg)
    print("    _on_global_replace 中的构造: SearchOptions(%s)" % (
        m.group(1).strip() if m else "未找到"))
    print("    面板侧是否带选项:", "is_regex" in open(
        "ui/global_search_panel.py", encoding="utf-8").read())
    print("    → 结论：全局替换未携带面板的正则/大小写/整词选项"
          if m and "is_regex" not in (m.group(1) or "") else "    → 已携带选项")
except Exception as e:
    print("    异常: %s" % e)

# ---------------------------------------------------------------
# 验证 4：Ctrl+Space 双绑定
# ---------------------------------------------------------------
print()
print("[4] Ctrl+Space 双绑定（子调查称本地强制补全不可达）")
try:
    t1 = open("ui/main_window.py", encoding="utf-8").read()
    t2 = open("ui/editor_view.py", encoding="utf-8").read()
    for name, t in (("main_window.py", t1), ("editor_view.py", t2)):
        for m in __import__("re").finditer(r'.*Ctrl\+Space.*', t):
            line = t[:m.start()].count("\n") + 1
            print("    %-16s 行 %-5d %s" % (name, line, m.group(0).strip()[:70]))
except Exception as e:
    print("    异常: %s" % e)

# ---------------------------------------------------------------
# 验证 5：草稿恢复是否有调用点
# ---------------------------------------------------------------
print()
print("[5] 草稿恢复 check_and_recover_drafts 的调用点")
try:
    import re as _re

    hits = []
    for root, dirs, fs in os.walk("."):
        dirs[:] = [d for d in dirs if d not in
                   ("dist", "build", "__pycache__", ".git", "_archive",
                    "tests", "tools")]
        for f in fs:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            tt = open(p, encoding="utf-8", errors="replace").read()
            for m in _re.finditer(r"check_and_recover_drafts", tt):
                ln = tt[:m.start()].count("\n") + 1
                hits.append("%s:%d" % (p.replace(".\\", ""), ln))
    print("    引用点: %s" % (hits or "无"))
    print("    → 结论：%s" % ("只定义、无调用（草稿只写不读）"
                             if len(hits) <= 1 else "有调用点"))
except Exception as e:
    print("    异常: %s" % e)

# ---------------------------------------------------------------
# 验证 6：撤销后 provider 是否停在旧内容
# ---------------------------------------------------------------
print()
print("[6] 撤销后 provider 是否与缓冲区一致")
try:
    import tempfile

    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "a.txt")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("one\n")
    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    proxy.open_file(p)
    sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()), b"two\n")
    same_before = (proxy.document.provider.read_text().replace("\r\n", "\n")
                   == sc.text().replace("\r\n", "\n"))
    proxy.undo()
    buf = sc.text().replace("\r\n", "\n")
    prov = proxy.document.provider.read_text().replace("\r\n", "\n")
    print("    编辑后一致 = %s" % same_before)
    print("    撤销后 缓冲区=%r provider=%r 一致=%s" % (
        buf, prov, buf == prov))
    print("    → 结论：%s" % ("撤销后 provider 滞后（双源不一致）"
                             if buf != prov else "一致"))
except Exception as e:
    print("    异常: %s: %s" % (type(e).__name__, e))

print()
print("=" * 92)
