# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""能力接线聚合（v2.25 拆分：common/keyseq/plugins/panels/commands）。"""

from ui.mixins.capability_commands_mixin import CommandsThemeMixin  # noqa: F401
from ui.mixins.capability_keyseq_mixin import KeySequenceMixin  # noqa: F401
from ui.mixins.capability_panels_mixin import PanelsExportMixin  # noqa: F401
from ui.mixins.capability_plugins_mixin import PluginsMixin  # noqa: F401
from ui.mixins.capability_wiring_common import *  # noqa: F401,F403


class CapabilityWiringMixin(
    KeySequenceMixin,
    PluginsMixin,
    PanelsExportMixin,
    CommandsThemeMixin,
):
    def _setup_format_menu(self):
        """在工具菜单挂「格式化文档」子菜单"""
        try:
            from core.formatter import get_formatter_registry

            available = [f.name for f in get_formatter_registry().list_available()]
        except Exception:
            available = []

        try:
            self.format_menu = self.tools_menu.addMenu("🪄 格式化文档")
        except Exception as e:
            if logger:
                logger.debug("创建格式化菜单失败: %s", e)
            return

        # 始终提供"自动选择"，即使当前机器一个格式化器都没装 ——
        # 菜单项存在但点击时给出明确安装提示，比菜单项凭空消失好。
        self._add_action(
            self.format_menu, "自动选择可用格式化器", "Ctrl+Alt+Shift+F", self._format_document
        )
        if available:
            self.format_menu.addSeparator()
            for name in available:
                label = {
                    "black": "Black（Python）",
                    "autopep8": "autopep8（Python）",
                    "clang-format": "clang-format（C/C++/Java/JS）",
                }.get(name, name)
                self._add_action(
                    self.format_menu,
                    label,
                    None,
                    lambda _checked=False, n=name: self._format_document(n),
                )
        else:
            self.format_menu.addSeparator()
            act = self._add_action(self.format_menu, "（未检测到本地格式化器）", None, None)
            try:
                if act is not None:
                    act.setEnabled(False)
                    act.setToolTip("安装方式：pip install black 或 pip install autopep8")
            except Exception:
                pass

    # ========================================================
    # 快捷键序列（core/key_sequence_manager.py）
    # ========================================================
    # 注册的序列（VSCode 风格；**前缀键 Ctrl+K 全仓无单键绑定**，已 grep 确认）
    KEY_SEQUENCES = (
        # (按键序列, 处理器名, 说明)
        (("Ctrl+K", "Ctrl+S"), "_save_all", "保存全部"),
        (("Ctrl+K", "Ctrl+W"), "_close_all_tabs", "关闭所有标签"),
        (("Ctrl+K", "Ctrl+C"), "_toggle_comment", "注释切换"),
        (("Ctrl+K", "Ctrl+F"), "_format_document", "格式化文档"),
        (("Ctrl+K", "Ctrl+T"), "_show_snapshot_dialog", "会话快照"),
        (("Ctrl+K", "Ctrl+D"), "_show_file_diff", "对比文件"),
    )
