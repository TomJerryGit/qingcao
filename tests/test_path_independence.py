# -*- coding: utf-8 -*-
"""工作目录无关性回归测试

真实缺陷：插件目录等路径写成**相对形式**（`"plugins"`），其含义取决于
**当前工作目录**。从资源管理器双击 exe 时 cwd 恰为 exe 目录，一切正常；
但通过快捷方式/任务栏/其他目录启动时：

    cwd = exe 目录   -> PluginManager total=10 active=10
    cwd = C:\\        -> PluginManager total=0  active=0   <-- 插件与菜单全部消失

这类缺陷极难排查：日志显示"插件目录存在: True"（那是用绝对路径判断的），
却一个插件都发现不到。

本测试锁死：**任意工作目录下**都能正确解析插件/数据/资源目录。

运行::

    python -m pytest tests/test_path_independence.py -v
"""
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.mark.parametrize("cwd", ["C:\\", "D:\\", os.path.expanduser("~"),
                                 ROOT])
def test_resolve_plugin_dir_is_cwd_independent(cwd):
    """插件目录解析结果不随工作目录变化"""
    if not os.path.isdir(cwd):
        pytest.skip("目录不存在: %s" % cwd)
    from infrastructure.plugin_loader import resolve_plugin_dir

    old = os.getcwd()
    try:
        os.chdir(cwd)
        resolved = resolve_plugin_dir("plugins")
    finally:
        os.chdir(old)

    assert os.path.isabs(resolved), "应返回绝对路径，实际 %r" % resolved
    assert os.path.isdir(resolved), "解析出的目录应存在: %r" % resolved
    # 必须能找到真实的插件目录
    assert os.path.isfile(os.path.join(resolved, "ai_assistant",
                                       "plugin.json")), (
        "插件目录内容不正确: %s" % resolved
    )


def test_app_root_dir_matches_repo():
    """源码运行时 app_root_dir 应等于仓库根目录"""
    from infrastructure.plugin_loader import app_root_dir
    assert os.path.normcase(app_root_dir()) == os.path.normcase(ROOT)


@pytest.mark.parametrize("cwd", ["C:\\", os.path.expanduser("~")])
def test_data_dirs_are_absolute(cwd):
    """数据类目录（崩溃/自动备份）必须与工作目录无关"""
    if not os.path.isdir(cwd):
        pytest.skip("目录不存在: %s" % cwd)
    old = os.getcwd()
    try:
        os.chdir(cwd)
        # 重新导入以获得在新 cwd 下的求值
        for mod in ("core.crash_stats", "app.session",
                    "infrastructure.icon_manager",
                    "infrastructure.sound_manager"):
            sys.modules.pop(mod, None)
        import app.session as ss
        import core.crash_stats as cs
        import infrastructure.icon_manager as im
        import infrastructure.sound_manager as sm
    finally:
        os.chdir(old)

    for label, val in (("CRASH_DIR", cs.CRASH_DIR),
                       ("AUTOSAVE_DIR", ss.AUTOSAVE_DIR),
                       ("DEFAULT_ICON_DIR", im.DEFAULT_ICON_DIR),
                       ("DEFAULT_SOUND_DIR", sm.DEFAULT_SOUND_DIR)):
        assert os.path.isabs(val), (
            "%s 应为绝对路径（与工作目录无关），实际 %r" % (label, val)
        )
        assert os.path.normcase(val).startswith(
            os.path.normcase(ROOT)), (
            "%s 应位于应用根目录下，实际 %r" % (label, val)
        )


def test_plugin_manager_resolves_absolute(qapp):
    """PluginManager 持有的 plugin_dir 必须是绝对路径"""
    from app.plugin_manager import PluginManager
    pm = PluginManager(main_window=None, plugin_dir="plugins")
    try:
        assert os.path.isabs(pm.plugin_dir), (
            "plugin_dir 应为绝对路径，实际 %r" % pm.plugin_dir
        )
        assert os.path.isdir(pm.plugin_dir)
    finally:
        pass


@pytest.mark.parametrize("cwd", ["C:\\", os.path.expanduser("~")])
def test_config_manager_lists_plugins_from_any_cwd(cwd):
    """配置导出不应因工作目录不同而漏掉插件列表"""
    if not os.path.isdir(cwd):
        pytest.skip("目录不存在: %s" % cwd)
    from infrastructure.plugin_loader import resolve_plugin_dir

    old = os.getcwd()
    try:
        os.chdir(cwd)
        pdir = resolve_plugin_dir("plugins")
        names = sorted(d for d in os.listdir(pdir)
                       if os.path.isdir(os.path.join(pdir, d)))
    finally:
        os.chdir(old)

    assert "ai_assistant" in names, "应能列出插件，实际 %s" % names
