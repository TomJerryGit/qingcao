#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""依赖检查"""
import sys


REQUIRED = [
    ('PyQt5', 'PyQt5.QtCore', 'QT_VERSION_STR'),
    ('PyQt5-Qt5', 'PyQt5.QtCore', 'PYQT_VERSION_STR'),
    ('PyQt5-sip', 'PyQt5.sip', '__version__'),
    ('QScintilla', 'PyQt5.Qsci', 'QSCINTILLA_VERSION_STR'),
    ('chardet', 'chardet', '__version__'),
    ('requests', 'requests', '__version__'),
    ('psutil', 'psutil', '__version__'),
]

OPTIONAL = [
    ('keyring', 'keyring', '__version__'),
    ('reportlab', 'reportlab', 'Version'),
    ('pypinyin', 'pypinyin', '__version__'),
]

print(f"Python: {sys.version}")
print("=" * 60)
print("核心依赖:")
print("=" * 60)

all_ok = True
for name, module, version_attr in REQUIRED:
    try:
        m = __import__(module, fromlist=[version_attr])
        version = getattr(m, version_attr, '?')
        if version == '?':
            # 尝试通过 package 元数据获取
            try:
                from importlib.metadata import version as get_version
                version = get_version(name.replace('-', '_'))
            except Exception:
                pass
        print(f"  ✓ {name:20s} {version}")
    except ImportError:
        print(f"  ✗ {name:20s} 未安装")
        all_ok = False

print()
print("可选依赖:")
print("=" * 60)
for name, module, version_attr in OPTIONAL:
    try:
        m = __import__(module, fromlist=[version_attr])
        version = getattr(m, version_attr, '?')
        if version == '?':
            try:
                from importlib.metadata import version as get_version
                version = get_version(name.replace('-', '_'))
            except Exception:
                pass
        print(f"  ✓ {name:20s} {version}")
    except ImportError:
        print(f"  - {name:20s} 未安装（可选）")

print()
print("=" * 60)
if all_ok:
    print("✓ 所有核心依赖已就绪")
    sys.exit(0)
else:
    print("✗ 缺少核心依赖，请运行:")
    print("  pip install -r requirements.txt")
    sys.exit(1)