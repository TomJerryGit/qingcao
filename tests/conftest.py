# -*- coding: utf-8 -*-
"""
青草编辑器测试配置。

提供共享的 pytest fixture:
- qapp: 全局 QApplication（session 级）
- tmp_text_file: 临时文本文件
- tmp_py_file: 临时 Python 文件
- tmp_dir: 临时目录
- preferences: 隔离的 Preferences 实例
- action_manager: 隔离的 ActionManager
- event_bus: 隔离的 EventBus
"""

import os
import sys

# ============================================================
# QT_QPA_PLATFORM 必须在导入 Qt 之前设置
# ============================================================
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

import tempfile
import shutil
import pytest

# 确保项目根目录在 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================
# 全局 autouse fixture: 隔离 QSettings
# ============================================================
@pytest.fixture(autouse=True, scope="session")
def _isolate_qsettings(tmp_path_factory):
    """
    会话级 QSettings 隔离。

    把所有 QSettings 写入重定向到 pytest 临时目录，
    避免污染用户真实配置（Windows 注册表 / macOS plist /
    Linux ~/.config）。

    这样即使测试中途崩溃，也不会影响用户已保存的首选项。

    覆盖范围：
        - unittest.TestCase 里的 QSettings 调用
          （pytest 对 unittest.TestCase 也应用 autouse fixture）
        - 全局单例（EventBus / ActionManager / Preferences）
    """
    from PyQt5.QtCore import QSettings

    ini_dir = str(tmp_path_factory.mktemp("qsettings"))

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, ini_dir
    )
    QSettings.setPath(
        QSettings.IniFormat, QSettings.SystemScope, ini_dir
    )

    yield
    # tmp_path_factory 自动清理，无需手动处理


# ============================================================
# QApplication fixture
# ============================================================
@pytest.fixture(scope="session")
def qapp():
    """
    会话级 QApplication 实例。

    所有依赖 Qt 的测试都通过这个 fixture 获取唯一的 app。
    """
    from PyQt5.QtWidgets import QApplication

    # 设置 offscreen 以避免 CI 环境无显示器的问题
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    yield app

    # 不主动 quit，让 pytest 处理


# ============================================================
# 临时文件/目录 fixtures
# ============================================================
@pytest.fixture
def tmp_text_file(tmp_path):
    """临时文本文件"""
    p = tmp_path / "test.txt"
    p.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
    return str(p)


@pytest.fixture
def tmp_py_file(tmp_path):
    """临时 Python 文件"""
    p = tmp_path / "test.py"
    p.write_text(
        "#!/usr/bin/env python\n"
        "# -*- coding: utf-8 -*-\n"
        "\n"
        "def hello():\n"
        "    return 'world'\n"
        "\n"
        "class Foo:\n"
        "    def bar(self):\n"
        "        pass\n",
        encoding="utf-8"
    )
    return str(p)


@pytest.fixture
def tmp_dir():
    """临时目录（测试后自动清理）"""
    d = tempfile.mkdtemp(prefix="qingcao_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ============================================================
# 隔离的核心对象
# ============================================================
@pytest.fixture
def preferences(qapp, tmp_path, monkeypatch):
    """隔离的 Preferences 实例（不污染用户真实设置）"""
    # 强制使用 IniFormat + 临时目录
    from PyQt5.QtCore import QSettings
    ini_dir = str(tmp_path / "settings")
    os.makedirs(ini_dir, exist_ok=True)

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, ini_dir)

    try:
        from app.preferences import Preferences
        prefs = Preferences()
        yield prefs
    except ImportError:
        yield None


@pytest.fixture
def action_manager(qapp):
    """隔离的 ActionManager 实例"""
    try:
        from app.actions import ActionManager
        mgr = ActionManager()
        yield mgr
    except ImportError:
        yield None


@pytest.fixture
def event_bus(qapp):
    """隔离的 EventBus 实例"""
    try:
        from app.event_bus import EventBus
        bus = EventBus(debug=False)
        yield bus
    except ImportError:
        yield None


# ============================================================
# 编辑器 fixtures
# ============================================================
@pytest.fixture
def document(qapp):
    """空的 Document 实例"""
    try:
        from core.document import Document
        doc = Document()
        yield doc
        try:
            doc.close()
        except Exception:
            pass
    except ImportError:
        yield None


@pytest.fixture
def memory_provider(qapp):
    """内存 Provider"""
    try:
        from core.content_provider import MemoryProvider
        provider = MemoryProvider()
        yield provider
        try:
            provider.close()
        except Exception:
            pass
    except ImportError:
        yield None