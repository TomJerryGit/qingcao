# -*- coding: utf-8 -*-
"""调试器前置校验（v2.26 从 __init__ 拆出）。"""

import logging
import os


logger = logging.getLogger(__name__)


class DebugGuardsMixin:
    def _show_control_hint(self):
        self.api.show_status(
            "调试控制：F8 继续 / F10 跳过 / Shift+F10 进入 / Ctrl+F10 跳出",
            4000,
        )

    # --------------------------------------------------------
    # 前置校验（错误场景必须**用户可见**）
    # --------------------------------------------------------
    def _require_python_file(self, action="调试"):
        """返回 (filepath, None)；不满足条件时返回 (None, 用户可见提示)。"""
        proxy = self.api.current_editor()
        if proxy is None:
            return None, f"没有打开的编辑器，无法{action}。"

        filepath = ""
        try:
            filepath = self.api.get_current_filepath() or ""
        except Exception:
            filepath = ""

        if not filepath:
            return None, (
                f"请先保存文件再{action}：当前标签还没有磁盘路径（未保存的文件无法交给调试进程）。"
            )
        if not filepath.lower().endswith((".py", ".pyw")):
            return None, (f"只有 Python 文件可以{action}：当前是 {os.path.basename(filepath)}。")
        if not os.path.isfile(filepath):
            return None, f"文件不存在，无法{action}：{filepath}"
        return filepath, None

    def _ensure_saved(self, proxy):
        """确保磁盘内容与编辑器一致。返回 (ok, message)。"""
        try:
            modified = bool(getattr(proxy, "is_modified", False))
        except Exception:
            modified = False
        if not modified:
            return True, ""

        try:
            saved = bool(self.api.save_current_file())
        except Exception as exc:
            logger.warning("自动保存失败: %s", exc)
            saved = False

        if saved:
            return True, "文件已自动保存"
        return False, ("文件有未保存的修改，且自动保存失败；请先按 Ctrl+S 手动保存后再调试。")

    def _notify_error(self, title, message):
        """统一错误出口：日志 + 状态栏 + 对话框（都失败也不崩）。"""
        logger.warning("[python_debugger] %s: %s", title, message)
        try:
            self.api.show_status(str(message), 6000, "error")
        except Exception:
            pass
        try:
            self.api.show_message(title, str(message), "error")
        except Exception:
            pass

    # --------------------------------------------------------
    # 调试会话
    # --------------------------------------------------------
