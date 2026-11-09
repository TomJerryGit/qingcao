# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""插件 API 聚合入口（v2.23 拆分）。PluginAPI 位于 app/plugin_api.py。"""

from app.plugin_api import *  # noqa: F401,F403


# ============================================================
# 权限辅助函数
# ============================================================
def parse_permissions(plugin_manifest: Dict[str, Any]) -> List[str]:
    """
    从插件清单中解析权限列表。

    参数:
        plugin_manifest: plugin.json 加载的字典

    返回:
        有效的权限列表
    """
    raw = plugin_manifest.get("permissions", [])
    if not isinstance(raw, list):
        return []
    return [p for p in raw if p in ALL_PERMISSIONS]


def validate_permissions(permissions: List[str]) -> List[str]:
    """
    校验权限列表，返回无效权限。

    参数:
        permissions: 权限列表

    返回:
        无效权限列表
    """
    return [p for p in permissions if p not in ALL_PERMISSIONS]


def describe_permissions(permissions: List[str]) -> str:
    """生成权限的友好描述（用于插件安装时提示用户）"""
    descriptions = {
        PERMISSION_FILESYSTEM: "读写本地文件",
        PERMISSION_NETWORK: "访问网络",
        PERMISSION_PROCESS: "执行系统命令",
        PERMISSION_CLIPBOARD: "读写剪贴板",
        PERMISSION_DIALOG: "显示对话框",
        PERMISSION_EDITOR_WRITE: "修改编辑器内容",
        PERMISSION_EDITOR_READ: "读取编辑器内容",
        PERMISSION_TERMINAL: "使用终端",
    }
    lines = []
    for p in permissions:
        if p in descriptions:
            lines.append(f"  • {descriptions[p]} ({p})")
    return "\n".join(lines) if lines else "  （无特殊权限）"


# ============================================================
# 插件基类
# ============================================================
class PluginBase:
    """
    插件基类。

    插件可以选择继承此类，也可不继承（只要实现 activate/deactivate 即可）。

    用法:
        from app.plugins import PluginBase

        class Plugin(PluginBase):
            NAME = "my_plugin"
            VERSION = "1.0.0"
            DESCRIPTION = "我的插件"

            def on_activate(self):
                self.api.add_menu("工具/我的功能", self.run)

            def run(self):
                self.api.show_status("Hello from my plugin!")
    """

    NAME: str = "unknown"
    VERSION: str = "0.0.0"
    DESCRIPTION: str = ""
    AUTHOR: str = ""
    PERMISSIONS: List[str] = []

    def __init__(self):
        self.api: Optional[PluginAPI] = None

    def activate(self, api):
        """
        由 PluginLoader 调用。

        修复记录:
            - api 为 None 时安全处理，不再二次调用 api.log()
            - 捕获 on_activate 异常并输出堆栈，但不二次崩溃
        """
        self.api = api

        # 安全处理：api 为 None 时直接返回
        if api is None:
            print(f"[PluginBase] {self.NAME}: api 为 None，跳过激活")
            return

        try:
            self.on_activate()
        except Exception as e:
            # 安全地记录错误（避免 api 为 None 时二次崩溃）
            try:
                if self.api is not None:
                    self.api.log(f"activate 失败: {e}", "error")
            except Exception:
                pass

            import traceback

            traceback.print_exc()
            # 让 PluginLoader 知道激活失败
            raise

    def on_activate(self):
        """子类重写，实现插件激活逻辑"""
        pass

    def deactivate(self):
        """由 PluginLoader 调用"""
        try:
            self.on_deactivate()
        except Exception as e:
            if self.api is not None:
                try:
                    self.api.log(f"deactivate 失败: {e}", "error")
                except Exception:
                    pass

    def on_deactivate(self):
        """子类重写，实现插件清理逻辑"""
        pass


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

    app = QApplication(sys.argv)
    win = QMainWindow()

    # 模拟主窗口必要属性
    class FakeTabs:
        def count(self):
            return 0

        def currentIndex(self):
            return -1

        def current_proxy(self):
            return None

        def add_tab(self, title="Untitled"):
            return None

        def open_file(self, path):
            return None

    win.tabs = FakeTabs()
    win.act_mgr = type("Mgr", (), {"register": lambda *a, **k: None, "actions": {}})()
    win.statusBar = lambda: type("SB", (), {"showMessage": lambda *a: None})()

    # 创建 API（有全部权限）
    api = PluginAPI(win, permissions=ALL_PERMISSIONS, plugin_name="test_plugin")

    print("API 版本:", api.get_api_version())
    print("插件名称:", api.get_plugin_name())
    print("权限:", api.get_permissions())
    print("数据目录:", api.get_plugin_data_dir())
    print()
    print("权限描述:")
    print(describe_permissions(api.get_permissions()))
    print()

    # 测试注册菜单
    action = api.add_menu("工具/测试/打招呼", lambda: print("Hello!"))
    print(f"注册菜单动作: {action}")

    # 测试注册命令
    api.register_command("hello", lambda: print("命令执行"), "打招呼")
    print(f"已注册命令: {api.list_commands()}")

    # 测试配置
    api.set_config("test_key", "test_value")
    print(f"读取配置: {api.get_config('test_key')}")

    # 测试 api 为 None 的 PluginBase
    print()
    print("=== 测试 PluginBase 安全处理 ===")

    class SafePlugin(PluginBase):
        NAME = "safe_test"

        def on_activate(self):
            print("SafePlugin on_activate 被调用")

    sp = SafePlugin()

    # 正常 activate
    sp.activate(api)
    print("正常 activate 成功")

    # api 为 None 的 activate（不应崩溃）
    sp2 = SafePlugin()
    try:
        sp2.activate(None)
        print("api=None 的 activate 安全通过")
    except Exception as e:
        print(f"api=None 的 activate 崩溃: {e}")

    # 测试清理
    api.cleanup()
    print("清理完成")

    print()
    print(api)
