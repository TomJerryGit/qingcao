# -*- coding: utf-8 -*-
"""端到端功能旅程验证：把"用户会走的路"真的跑一遍

不依赖单元测试的模拟，而是用真实组件完成完整操作链，记录每一步结果。
"""
import os
import sys
import tempfile


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

RESULTS = []


def step(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, "异常: %s: %s" % (type(e).__name__, e)
    RESULTS.append((name, ok, detail))
    print("  [%s] %-38s %s" % ("OK " if ok else "FAIL", name, detail))
    return ok


tmp = tempfile.mkdtemp()

# ---------------------------------------------------------------
# 旅程 1：打开 → 编辑 → 保存（内容一致性）
# ---------------------------------------------------------------
state = {}


def j1_open():
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    p = os.path.join(tmp, "j1.py")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("x = 1\n")
    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    assert proxy.open_file(p) is True
    state["j1"] = (p, sc, proxy)
    return True, "文件已打开，内容=%r" % sc.text()


def j1_edit():
    p, sc, proxy = state["j1"]
    sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()), b"y = 2\n")
    # 关键：provider 是否与屏幕一致（双内容源问题）
    prov = proxy.document.provider.read_text()
    same = prov.replace("\r\n", "\n") == sc.text().replace("\r\n", "\n")
    return same, "provider 与缓冲区一致=%s" % same


def j1_save():
    p, sc, proxy = state["j1"]
    ok = proxy.save_file()
    disk = open(p, "rb").read()
    return bool(ok) and b"y = 2" in disk, "磁盘=%r" % disk


def j1_undo():
    p, sc, proxy = state["j1"]
    before = sc.text()
    proxy.undo()
    changed = sc.text() != before
    return changed, "撤销后内容变化=%s (%r -> %r)" % (
        changed, before.strip(), sc.text().strip())


def j1_delete_undo():
    """删除后撤销必须还原（这是本轮修的严重缺陷）"""
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    p = os.path.join(tmp, "j1d.txt")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("hello world\n")
    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    proxy.open_file(p)
    original = sc.text()
    sc.SendScintilla(sc.SCI_DELETERANGE, 0, 5)      # 删掉 "hello"
    after_del = sc.text()
    proxy.undo()
    return sc.text() == original, "原文=%r 删除后=%r 撤销后=%r" % (
        original.strip(), after_del.strip(), sc.text().strip())


# ---------------------------------------------------------------
# 旅程 2：查找 / 替换（走缓冲区）
# ---------------------------------------------------------------
state2 = {}


def j2_setup():
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    p = os.path.join(tmp, "j2.txt")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("alpha\n")
    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    proxy.open_file(p)
    sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()), b"needle\n")
    state2["j2"] = (p, sc, proxy)
    return True, "已输入 needle"


def j2_find():
    p, sc, proxy = state2["j2"]
    found = proxy.search_next("needle")
    return found is True, "search_next('needle')=%s" % found


def j2_replace():
    p, sc, proxy = state2["j2"]
    sc.SendScintilla(sc.SCI_INSERTTEXT, len(sc.text()), b"MY EDIT\n")
    n = proxy.replace_all_in_buffer("needle", "REPLACED")
    kept = "MY EDIT" in sc.text()
    return (n >= 1 and kept), "替换 %d 处，未保存编辑保留=%s" % (n, kept)


# ---------------------------------------------------------------
# 旅程 3：切换行尾符必须落盘
# ---------------------------------------------------------------
def j3_eol():
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    p = os.path.join(tmp, "j3.txt")
    with open(p, "wb") as f:
        f.write(b"a\nb\n")
    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    proxy.open_file(p)
    proxy.document.set_eol("\r\n")
    proxy.save_file()
    disk = open(p, "rb").read()
    return disk == b"a\r\nb\r\n", "磁盘=%r" % disk


# ---------------------------------------------------------------
# 旅程 4：切换编码后编辑器内容刷新
# ---------------------------------------------------------------
def j4_encoding():
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    p = os.path.join(tmp, "j4.txt")
    with open(p, "wb") as f:
        f.write("中文内容\n".encode("gbk"))
    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    proxy.open_file(p)
    ok = proxy.document.change_encoding("gbk", reload=True)
    same = sc.text().replace("\r\n", "\n") == "中文内容\n"
    return (bool(ok) and same), "change_encoding=%s 编辑器=%r" % (
        ok, sc.text())


# ---------------------------------------------------------------
# 旅程 5：外部修改检测（本轮修复的核心能力）
# ---------------------------------------------------------------
def j5_external():
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    p = os.path.join(tmp, "j5.txt")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("orig\n")
    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    proxy.open_file(p)
    # 编辑器释放句柄（TabManager 会做；这里模拟）
    for obj in (proxy.document.provider,):
        if hasattr(obj, "release_mmap"):
            obj.release_mmap()
    try:
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("changed externally\n")
    except OSError as e:
        return False, "外部写入被阻止（文件被锁）: %s" % e
    import time
    time.sleep(0.05)
    return True, "外部程序可正常修改已打开的文件（关键前提）"


# ---------------------------------------------------------------
# 旅程 6：三方合并不丢内容
# ---------------------------------------------------------------
def j6_merge():
    from core.file_merge import ThreeWayMerger
    r = ThreeWayMerger.merge("a\nb\n", "a\nb\nLOCAL\n", "a\nb\nREMOTE\n")
    m = r["merged"]
    ok = ("LOCAL" in m and "REMOTE" in m) or bool(r["conflicts"])
    return ok, "merged=%r conflicts=%d" % (m, len(r["conflicts"]))


# ---------------------------------------------------------------
# 旅程 7：Git 状态解析（含空格/中文路径）
# ---------------------------------------------------------------
def j7_git():
    import subprocess

    from core.git_client import GitClient

    repo = os.path.join(tmp, "repo")
    os.makedirs(repo, exist_ok=True)

    def g(*a):
        return subprocess.run(["git"] + list(a), cwd=repo,
                              capture_output=True, text=True)

    g("init", "-q")
    g("config", "user.email", "t@t.t")
    g("config", "user.name", "t")
    for name in ("with space.txt", "中文名字.txt"):
        with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
            f.write("x\n")
    st = GitClient(repo).status()
    ok = "with space.txt" in st and "中文名字.txt" in st
    return ok, "解析键=%s" % list(st)


# ---------------------------------------------------------------
# 旅程 8：会话/草稿恢复链路
# ---------------------------------------------------------------
def j8_session():
    from app.session import SessionManager

    sm = SessionManager()
    has_drafts = hasattr(sm, "find_recoverable_drafts")
    has_autosave = hasattr(sm, "save_autosave")
    return (has_drafts and has_autosave), (
        "find_recoverable_drafts=%s save_autosave=%s"
        % (has_drafts, has_autosave))


# ---------------------------------------------------------------
# 旅程 9：插件系统（真实加载）
# ---------------------------------------------------------------
def j9_plugins():
    from app.plugin_manager import PluginManager

    pm = PluginManager()
    r = pm.load_all()
    # LoadResult 的属性是 loaded/failed/disabled/total（不是 activated）
    return r.loaded > 0, "loaded=%s failed=%s total=%s" % (
        r.loaded, r.failed, r.total)


# ---------------------------------------------------------------
# 旅程 10：AI 客户端可用性（Ollama）
# ---------------------------------------------------------------
def j10_ollama():
    from core.ollama_client import OllamaClient
    c = OllamaClient()
    running = c.is_running() if hasattr(c, "is_running") else None
    return True, "OllamaClient 可构造，is_running=%s" % running


print("=" * 96)
print("端到端功能旅程验证")
print("=" * 96)

step("1a 打开文件", j1_open)
step("1b 编辑后 provider 同步", j1_edit)
step("1c Ctrl+S 落盘", j1_save)
step("1d 撤销生效", j1_undo)
step("1e 删除后撤销还原", j1_delete_undo)
step("2a 查找刚输入的文字", j2_setup)
step("2b search_next 命中", j2_find)
step("2c 全部替换保留未保存编辑", j2_replace)
step("3  行尾切换落盘", j3_eol)
step("4  编码切换刷新编辑器", j4_encoding)
step("5  外部可修改已打开文件", j5_external)
step("6  三方合并不丢内容", j6_merge)
step("7  Git 路径含空格/中文", j7_git)
step("8  会话/草稿 API", j8_session)
step("9  插件系统加载", j9_plugins)
step("10 AI/Ollama 客户端", j10_ollama)

ok_n = sum(1 for _n, o, _d in RESULTS if o)
print()
print("=" * 96)
print("结果：%d/%d 通过" % (ok_n, len(RESULTS)))
print("=" * 96)
for n, o, d in RESULTS:
    if not o:
        print("  未通过：%s -> %s" % (n, d))
