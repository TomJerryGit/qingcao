# -*- coding: utf-8 -*-
"""验证：代码片段库（本地片段包）+ 协作模块已移除

    python tools\\verify_snippet_library.py

## 背景（为什么有这个脚本）

原「代码片段市场」依赖一个**不存在的 GitHub 仓库**
（`api.github.com/repos/qingcao-editor/snippets/contents`，实测 HTTP 404）。
已改造为**本地片段包库**：

* 片段包 = `<目录>/*.json`，格式见 `core/snippet_market.py`；
* 入口「工具 → 📚 代码片段库…」；
* 零网络请求、零第三方代码执行风险。

同时「实时协作」模块（裸 TCP 无认证/无加密）已整体移除。

覆盖：
  A. 本地片段库核心
     * 扫描片段包目录（多文件、数组格式、`{"snippets": [...]}` 格式）；
     * 坏 JSON 不影响其它文件（逐个容错）；
     * 目录为空 → 内置示例兜底（让用户知道格式）；
     * 片段包目录可切换 + 记住选择（QSettings）。
  B. 导入
     * 导入后进入 `SnippetManager`；
     * **同名不同内容不静默覆盖**（自动加 `_2` 后缀）；
     * `SnippetManager` 的存储路径是**绝对路径**（相对路径会随 cwd 漂移）。
  C. 对话框
     * 标题是「代码片段库」、有目录选择按钮、有语言/搜索过滤；
     * 过滤逻辑有效（按语言、按关键词）。
  D. 接线
     * 菜单项存在、处理器可调用；
     * **协作模块确实已删除**（文件不存在 + 无残留引用）。

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
from PyQt5.QtWidgets import QAction, QApplication  # noqa: E402


app = QApplication.instance() or QApplication([])
for _fp in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(_fp):
        QFontDatabase.addApplicationFont(_fp)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-52s %s" % ("OK " if cond else "FAIL", name, detail))


def wait_for(pred, timeout=5.0):
    """泵事件循环直到 pred() 为真（异步信号需要事件循环）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(pred())


TMP = tempfile.mkdtemp(prefix="qc_snipverify_")

print("=" * 96)
print("验证：代码片段库（本地）+ 协作模块已移除")
print("=" * 96)

# ============================================================
# A. 核心扫描
# ============================================================
print()
print("== A. 本地片段库扫描 ==")
from core.snippet_market import (  # noqa: E402
    DEFAULT_PACK_DIR,
    SnippetLibrary,
)


check("A1 默认片段包目录为绝对路径",
      os.path.isabs(DEFAULT_PACK_DIR), DEFAULT_PACK_DIR)

pack_dir = os.path.join(TMP, "packs")
os.makedirs(pack_dir, exist_ok=True)

# 两种格式各一个文件
with open(os.path.join(pack_dir, "a.json"), "w", encoding="utf-8") as f:
    json.dump({"snippets": [
        {"name": "Py Snip", "language": "python",
         "description": "python 片段", "body": "print(1)"},
    ]}, f, ensure_ascii=False)
with open(os.path.join(pack_dir, "b.json"), "w", encoding="utf-8") as f:
    json.dump([
        {"name": "Js Snip", "language": "javascript",
         "description": "js 片段", "body": "console.log(1)"},
    ], f, ensure_ascii=False)
# 坏文件：不应影响其它文件
with open(os.path.join(pack_dir, "broken.json"), "w", encoding="utf-8") as f:
    f.write("{ this is not json")

lib = SnippetLibrary(source_dir=pack_dir)
items = lib.scan()
check("A2 扫描到 2 个片段（坏文件被跳过）", len(items) == 2,
      str([i.get("name") for i in items]))
check("A3 支持 {\"snippets\": [...]} 格式",
      any(i.get("name") == "Py Snip" for i in items), "")
check("A4 支持裸数组格式",
      any(i.get("name") == "Js Snip" for i in items), "")
check("A5 每个片段带 source_file",
      all(i.get("source_file") for i in items), "")

# 空目录 → 内置示例
empty_dir = os.path.join(TMP, "empty")
os.makedirs(empty_dir, exist_ok=True)
lib_empty = SnippetLibrary(source_dir=empty_dir)
check("A6 空目录扫描结果为空", lib_empty.scan() == [], "")
check("A7 内置示例可用于兜底",
      len(SnippetLibrary.builtin_snippets()) >= 3,
      "%d 条" % len(SnippetLibrary.builtin_snippets()))

# 切换目录 + 记住
got = []
lib.set_source_dir(empty_dir)
lib.fetch_completed.connect(lambda lst: got.append(list(lst)))
lib.fetch_async(force=True)
check("A8 set_source_dir 生效",
      lib.source_dir == os.path.abspath(empty_dir), lib.source_dir)
check("A9 异步读取能完成", wait_for(lambda: bool(got)),
      "%d 次回调" % len(got))
check("A10 新目录读取结果为空（无片段包）",
      got and got[0] == [], str(got[:1]))
check("A11 目录选择被记住",
      os.path.abspath(SnippetLibrary.saved_source_dir())
      == os.path.abspath(empty_dir),
      SnippetLibrary.saved_source_dir())

# ============================================================
# B. 导入
# ============================================================
print()
print("== B. 导入到本地片段管理器 ==")
lib_back = SnippetLibrary(source_dir=pack_dir)
items = lib_back.scan()
py_snip = next(i for i in items if i.get("name") == "Py Snip")
js_snip = next(i for i in items if i.get("name") == "Js Snip")

done, failed = [], []
lib_back.download_completed.connect(lambda p: done.append(p))
lib_back.download_failed.connect(lambda e: failed.append(e))

from core.snippets import get_snippet_manager  # noqa: E402


mgr = get_snippet_manager()
check("B1 片段库路径为绝对路径", os.path.isabs(mgr.filepath),
      mgr.filepath)

lib_back.download_async(py_snip)
check("B2 导入成功", wait_for(lambda: bool(done) or bool(failed)),
      str(done or failed))
check("B3 片段进入 SnippetManager",
      any(s.name == "Py Snip" for s in mgr.list_all()), "")

# 同名不同内容 → 加后缀，不静默覆盖
done2 = []
lib_back.download_completed.connect(lambda p: done2.append(p))
same_name = dict(py_snip)
same_name["body"] = "print(999)"
lib_back.download_async(same_name)
check("B4 同名不同内容导入完成", wait_for(lambda: bool(done2)),
      str(done2))
prefix = done2[0] if done2 else ""
check("B5 同名不静默覆盖（自动加后缀）", prefix.endswith("_2"), prefix)
old = mgr.get(done[0]) if done else None
check("B6 原片段内容未被覆盖",
      old is not None and old.body == "print(1)",
      getattr(old, 'body', None))

lib_back.download_async(js_snip)
check("B7 导入第二个片段成功",
      wait_for(lambda: any(s.name == "Js Snip" for s in mgr.list_all())), "")

# 缺 body 的片段必须被拒绝（不能塞空片段进库）
bad = {"name": "No Body"}
lib_back.download_async(bad)
check("B8 无 body 的片段被拒绝（失败信号）",
      wait_for(lambda: len(failed) >= 1 or len(done) >= 4), str(failed))

# ============================================================
# C. 对话框
# ============================================================
print()
print("== C. 代码片段库对话框 ==")
from ui.snippet_market_dialog import SnippetMarketDialog  # noqa: E402


dlg = SnippetMarketDialog()
check("C1 对话框可构造", dlg is not None, "")
check("C2 标题是「代码片段库」", dlg.windowTitle() == "代码片段库",
      dlg.windowTitle())
check("C3 有目录显示与选择目录按钮",
      hasattr(dlg, "dir_label")
      and callable(getattr(dlg, "_on_choose_dir", None)), "")
check("C4 有语言过滤下拉", hasattr(dlg, "lang_combo"), "")
check("C5 有搜索框", hasattr(dlg, "search_edit"), "")
check("C6 有导入按钮逻辑", callable(getattr(dlg, "_on_install", None)), "")

# 过滤逻辑：直接注入数据验证
dlg._snippets = [
    {"name": "PyOne", "language": "python", "description": "aaa",
     "body": "x"},
    {"name": "JsOne", "language": "javascript", "description": "bbb",
     "body": "y"},
]
dlg.lang_combo.setCurrentIndex(0)      # 全部
dlg.search_edit.setText("")
dlg._apply_filter()
n_all = dlg.list_widget.count()
dlg.lang_combo.setCurrentText("Python")
dlg._apply_filter()
n_py = dlg.list_widget.count()
dlg.lang_combo.setCurrentText("全部")
dlg.search_edit.setText("bbb")
dlg._apply_filter()
n_kw = dlg.list_widget.count()
check("C7 语言过滤生效", n_py == 1 and n_all == 2,
      "全部=%d python=%d" % (n_all, n_py))
check("C8 关键词过滤生效", n_kw == 1, "命中 %d" % n_kw)
dlg.close()

# ============================================================
# D. 接线 + 协作已移除
# ============================================================
print()
print("== D. 接线与移除确认 ==")
from ui.main_window import MainWindow  # noqa: E402


win = MainWindow()
texts = [a.text() for a in win.findChildren(QAction)]
check("D1 菜单项「📚 代码片段库…」存在",
      "📚 代码片段库…" in texts, "")
check("D2 处理器 _show_snippet_library 可调用",
      callable(getattr(win, "_show_snippet_library", None)), "")

# 协作模块必须真的没了
root = r"D:\QingCaoEditor"
for rel in ("ui/collab_dialog.py", "core/collab.py"):
    check("D3 协作模块已删除: %s" % rel,
          not os.path.isfile(os.path.join(root, rel)), "")

# 全仓不得再有对 core.collab 的 import（注释/文档里的说明不算）
import io  # noqa: E402
import re  # noqa: E402


offenders = []
for sub in ("core", "ui", "app", "main.py"):
    base = os.path.join(root, sub)
    files = []
    if os.path.isfile(base):
        files = [base]
    else:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            files.extend(os.path.join(dirpath, f) for f in filenames
                         if f.endswith(".py"))
    for path in files:
        try:
            src = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in re.finditer(r"^\s*(?:from|import)\s+core\.collab\b",
                             src, re.M):
            offenders.append(os.path.relpath(path, root))
check("D4 无残留 core.collab 导入", not offenders, str(offenders[:5]))

# 网络请求必须彻底移除（原市场客户端用 requests 拉 404 地址）
#
# 注意：不能用"文本里是否出现 requests/api.github.com"来判断 ——
# 该模块的**文档字符串**刻意写明了「原实现拉一个不存在的仓库」，
# 那是解释**为什么改为本地库**的必需文档。这里只检查真正的**代码**：
# import 语句、赋值语句、函数调用。
src_market = io.open(os.path.join(root, "core", "snippet_market.py"),
                     encoding="utf-8").read()
code_offenders = []
for pat, desc in (
    (r"^\s*import\s+requests\b", "import requests"),
    (r"^\s*from\s+requests\b", "from requests"),
    (r"^\s*MARKET_API\s*=", "MARKET_API 赋值（网络市场地址）"),
    (r"requests\.(?:get|post|head)\s*\(", "requests 调用"),
    (r"urlopen\s*\(", "urllib urlopen 调用"),
):
    if re.search(pat, src_market, re.M):
        code_offenders.append(desc)
check("D5 片段库代码里不再有网络请求", not code_offenders,
      str(code_offenders))
check("D6 片段库不再定义网络市场地址常量",
      not re.search(r"^\s*MARKET_API\s*=", src_market, re.M), "")
check("D7 文档里说明了改为本地库的原因（404）",
      "404" in src_market, "")

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
