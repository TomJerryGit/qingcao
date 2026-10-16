# -*- coding: utf-8 -*-
"""实测"编码语义混合"是否真的会造成静默数据损坏

场景：UTF-8 文件里含中文。用户只是"换一种解释看看"（切到 GBK），
然后按 Ctrl+S。文件会不会被永久破坏？
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

from PyQt5.Qsci import QsciScintilla  # noqa: E402

from core.document import Document  # noqa: E402
from core.editor import EditorProxy  # noqa: E402


print("=" * 92)
print("编码语义混合 → 是否存在静默数据损坏风险")
print("=" * 92)

tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "utf8_cn.txt")
ORIGINAL = "中文内容测试\n"
with open(p, "wb") as f:
    f.write(ORIGINAL.encode("utf-8"))

before = open(p, "rb").read()
print()
print("初始状态")
print("  磁盘字节      : %r" % before)
print("  期望文本      : %r" % ORIGINAL)

sc = QsciScintilla()
sc.setUtf8(True)
proxy = EditorProxy(sc, Document())
proxy.open_file(p)
print("  打开后编码    : %s" % proxy.document.encoding)
print("  打开后显示    : %r" % sc.text())

# 用户动作：把编码"改解释"为 GBK（相当于 Notepad++ 的 Encoding > Character sets）
print()
print("用户动作：切换解释为 GBK（不改内容，只是换个解释）")
ok = proxy.document.change_encoding("gbk", reload=True)
print("  change_encoding('gbk') -> %s" % ok)
print("  切换后编码    : %s" % proxy.document.encoding)
print("  切换后显示    : %r" % sc.text())
print("  磁盘此时      : %r" % open(p, "rb").read())

# 用户按 Ctrl+S（他可能只是想"确认一下"）
print()
print("用户动作：Ctrl+S")
saved = proxy.save_file()
after = open(p, "rb").read()
print("  保存结果      : %s" % saved)
print("  磁盘字节      : %r" % after)
print("  provider 编码 : %s" % proxy.document.provider.encoding)

print()
print("-" * 92)
if after == before:
    print("结论：磁盘未被改写（无损坏）")
else:
    print("★ 结论：磁盘字节已被改写！")
    print("   原字节 : %r" % before)
    print("   新字节 : %r" % after)
    # 用原编码读回看是否还能还原
    try:
        restored = after.decode("utf-8", errors="replace")
        print("   用 UTF-8 重新读回 : %r" % restored)
    except Exception as e:
        print("   用 UTF-8 读回失败 : %s" % e)
    try:
        as_gbk = after.decode("gbk", errors="replace")
        print("   用 GBK 读回       : %r" % as_gbk)
    except Exception as e:
        print("   用 GBK 读回失败   : %s" % e)

# 再测一遍"损坏是否可逆"：如果不保存，关掉重开是否恢复
print()
print("=" * 92)
print("对照：只切换解释、**不保存**，关闭后重开")
tmp2 = tempfile.mkdtemp()
p2 = os.path.join(tmp2, "utf8_cn2.txt")
with open(p2, "wb") as f:
    f.write(ORIGINAL.encode("utf-8"))
sc2 = QsciScintilla()
sc2.setUtf8(True)
proxy2 = EditorProxy(sc2, Document())
proxy2.open_file(p2)
proxy2.document.change_encoding("gbk", reload=True)
shown = sc2.text()
proxy2.document.close()          # 不保存，直接关闭
proxy3 = EditorProxy(QsciScintilla(), Document())
proxy3.sc.setUtf8(True)
proxy3.open_file(p2)
print("  切换解释时显示 : %r" % shown)
print("  不保存关闭后重开: %r" % proxy3.sc.text())
print("  磁盘           : %r" % open(p2, "rb").read())
