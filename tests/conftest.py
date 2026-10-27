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


# 关键：让 pytest-qt 使用 PyQt5，与项目代码一致
# 必须在任何 Qt 导入之前设置
os.environ.setdefault("PYTEST_QT_API", "pyqt5")
os.environ.setdefault("QT_API", "pyqt5")

# 已有的环境变量保留
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")
import sys


# ============================================================
# QT_QPA_PLATFORM 必须在导入 Qt 之前设置
# ============================================================
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

import shutil
import tempfile

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

    ⚠ 为什么需要 monkeypatch（真实缺陷，已实测）:
        仅调用 `QSettings.setDefaultFormat(IniFormat)` + `setPath(...)`
        **不足以**隔离。PyQt5 的 `QSettings(org, app)` 两参构造
        **总是使用 NativeFormat**，完全忽略 `setDefaultFormat`：

            默认格式 = 1 (IniFormat)
            QSettings('QingCao','Editor').format()      -> 0 (注册表)
            QSettings(IniFormat,UserScope,org,app)      -> 1 (INI 文件)

        而 `app/preferences.py` 用的正是 `QSettings(ORG_NAME, APP_NAME)`
        —— 于是**所有测试都在读写真实注册表**：
          * 测试之间互相污染（前一个用例写的值影响后一个）
          * 污染开发者的真实首选项
        实测症状：`preferences.get("local_completion", True)` 返回 False
        （默认应为 True），因为注册表里残留了别的用例写入的 false。

        因此这里把 `app.preferences.QSettings` 换成强制 IniFormat 的包装，
        让被测代码"以为"在用普通 QSettings，实际落到临时 .ini。

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

    # 强制两参构造走 IniFormat（见上方说明）
    #
    # 注意：必须在 **类级别** 替换 `PyQt5.QtCore.QSettings`，而不是只改
    # `app.preferences.QSettings`。因为测试与生产代码经常这样写：
    #     from PyQt5.QtCore import QSettings
    #     QSettings(ORG, APP)
    # 若只打补丁到 app.preferences，这些直接 import 的地方仍会写真实注册表
    # （实测：tests/test_preferences_wiring.py 里 `settings.setValue(...)`
    #  写入注册表，而 main._pref 通过 Preferences 读临时 ini → 断言失败）。
    from PyQt5 import QtCore as _qtcore
    _real_qsettings = _qtcore.QSettings

    class _ForcedIniQSettings(_real_qsettings):
        """两参构造也强制 IniFormat，确保隔离真正生效

        只改写 `QSettings(org: str, app: str)` 这一种重载。
        必须放行其它重载，例如 `QSettings(fileName, Format)` ——
        test_secure_storage 等用例用的就是它，若一并改写会抛
        "arguments did not match any overloaded call"。
        """

        def __init__(self, *args, **kwargs):
            if (len(args) == 2
                    and isinstance(args[0], str)
                    and isinstance(args[1], str)):
                args = (_real_qsettings.IniFormat,
                        _real_qsettings.UserScope,
                        args[0], args[1])
            super().__init__(*args, **kwargs)

    _qtcore.QSettings = _ForcedIniQSettings

    import app.preferences as _prefs_mod
    _prefs_orig = getattr(_prefs_mod, 'QSettings', None)
    _prefs_mod.QSettings = _ForcedIniQSettings

    yield

    _qtcore.QSettings = _real_qsettings
    if _prefs_orig is not None:
        _prefs_mod.QSettings = _prefs_orig


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
# P2-C7: monkeypatch 未使用，已移除
@pytest.fixture
def preferences(qapp, tmp_path):
    """隔离的 Preferences 实例（不污染用户真实设置）

    说明（测试隔离修复）：
        会话级 `_isolate_qsettings` 已经把 **所有** QSettings（含
        `QSettings(org, app)` 两参形式）重定向到临时 .ini。

        本 fixture 原先还额外调用 `setPath(IniFormat, ..., tmp_path)`，
        但 `QSettings.setPath` 是**进程级全局状态**，而 `tmp_path` 是
        **每个用例独立**的目录 —— 用例结束后路径仍指向已被删除的目录，
        后续用例/未被 fixture 覆盖的代码（如 `main._pref()` 新建的
        Preferences）就会读写到一个不存在的路径，造成"写入读不到"。

        因此这里不再改全局路径，改为：复用会话级隔离目录，并在用例
        开始时**清空**其中的设置，保证每个用例都从干净默认值出发。
    """
    from PyQt5.QtCore import QSettings

    from app import preferences as _prefs_module
    from app.preferences import Preferences

    # 清掉上一个用例可能残留的值（同一会话共享一个临时 ini）
    # 注意 ORG_NAME / APP_NAME 是**模块级常量**，不是 Preferences 的类属性
    settings = QSettings(QSettings.IniFormat, QSettings.UserScope,
                         _prefs_module.ORG_NAME,
                         _prefs_module.APP_NAME)
    settings.clear()
    settings.sync()

    prefs = Preferences()
    yield prefs


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

# ============================================================
# 环境敏感用例隔离（真实子进程 / QProcess 握手）
# ============================================================
# 实测：tests/test_lsp_integration.py::TestRealSubprocessHandshake 的两个
# 用例会启动真实子进程等握手；**单独运行 100% 通过**，但跟在大量 GUI
# 用例之后同进程运行时会偶发挂起（QProcess 事件 + Qt 对象累积的交互问题，
# 放宽超时无效）。因此标记 @pytest.mark.isolated，默认跳过；
# 需要时显式运行：
#     $env:QC_RUN_ISOLATED="1"; python -m pytest tests/test_lsp_integration.py
import os as _os

import pytest as _pytest


_QC_RUN_ISOLATED = _os.environ.get("QC_RUN_ISOLATED") == "1"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "isolated: 环境敏感用例（真实子进程等），默认跳过")


def pytest_collection_modifyitems(config, items):
    if _QC_RUN_ISOLATED:
        return
    skip = _pytest.mark.skip(
        reason="环境敏感用例（真实子进程握手）；QC_RUN_ISOLATED=1 显式运行")
    for item in items:
        if item.get_closest_marker("isolated") is not None:
            item.add_marker(skip)


# 稳定性专项：把 QSettings 重定向到临时目录。
# 原因：测试会通过 MainWindow 保存布局/面板可见性到真实 QSettings；
# 同一进程内后序测试恢复这些状态 → 顺序敏感失败（分片运行时暴露），
# 且会污染用户真实配置。
@pytest.fixture(scope="session", autouse=True)
def _isolated_qsettings(tmp_path_factory):
    try:
        from PyQt5.QtCore import QSettings
    except Exception:
        yield
        return
    base = tmp_path_factory.mktemp("qsettings")
    old_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(base))
    QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope,
                      str(base))
    try:
        yield
    finally:
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, "")
        QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, "")
        QSettings.setDefaultFormat(old_format)
