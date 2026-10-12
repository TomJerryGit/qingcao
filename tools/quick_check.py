# quick_check.py
import os
import sys


# 修复：从 tools/ 直接运行时，项目根目录不在 sys.path，
# `import core` 会 ModuleNotFoundError。原脚本缺这一步，
# 导致它从未真正跑通过。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

# 修复：控制台可能是 GBK 代码页，直接 print "✓" 会 UnicodeEncodeError。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from PyQt5.QtWidgets import QApplication


app = QApplication(sys.argv)

from PyQt5.Qsci import QsciScintilla

from core.content_provider import MemoryProvider
from core.document import Document
from core.editor import EditorProxy


provider = MemoryProvider()
provider.open(initial_text="test\n")
doc = Document(provider=provider)
sc = QsciScintilla()
proxy = EditorProxy(sc, doc)

# 验证属性
assert hasattr(proxy, 'prov'), "proxy.prov 不存在"
assert hasattr(proxy, 'filepath'), "proxy.filepath 不存在"
assert hasattr(proxy, 'encoding'), "proxy.encoding 不存在"
assert hasattr(doc, 'enc'), "doc.enc 不存在"

print("✓ proxy.prov       =", proxy.prov)
print("✓ proxy.filepath   =", proxy.filepath)
print("✓ proxy.encoding   =", proxy.encoding)
print("✓ doc.enc          =", doc.enc)
print("✓ proxy.prov.filepath =", proxy.prov.filepath if proxy.prov else None)
print()
print("全部检查通过 ✓")

# 验证增强大纲可导入
try:
    from ui.outline_panel import OutlinePanel
    print("✓ ui.outline_panel.OutlinePanel 导入成功")
except ImportError as e:
    print("✗ 导入失败:", e)
    sys.exit(1)