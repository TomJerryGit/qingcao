# -*- coding: utf-8 -*-
"""快捷键序列管理器（VSCode 风格）"""
import time
from typing import Dict, Callable, Optional, List, Tuple
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QKeySequence


class KeySequenceBinding:
    """快捷键序列绑定"""

    def __init__(self, keys, callback, description="",
                 timeout_ms=2000):
        self.keys: List[str] = list(keys)  # ["Ctrl+K", "Ctrl+S"]
        self.callback = callback
        self.description = description
        self.timeout_ms = timeout_ms


class KeySequenceManager(QObject):
    """快捷键序列管理器"""

    status_changed = pyqtSignal(str)  # 状态栏提示

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bindings: List[KeySequenceBinding] = []
        self._pending_keys: List[str] = []
        self._pending_start = 0.0

        # 超时定时器
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def register(self, keys, callback, description="",
                 timeout_ms=2000):
        """注册序列绑定"""
        if isinstance(keys, str):
            keys = keys.split()
        self.bindings.append(KeySequenceBinding(
            keys, callback, description, timeout_ms
        ))

    def register_many(self, items):
        """批量注册

        items: [(keys, callback, desc), ...]
        """
        for item in items:
            if len(item) >= 2:
                keys = item[0]
                cb = item[1]
                desc = item[2] if len(item) > 2 else ""
                self.register(keys, cb, desc)

    def handle_key(self, key_str: str) -> bool:
        """
        处理按键。

        参数:
            key_str: 当前按键的字符串表示（如 "Ctrl+K"）

        返回:
            True 表示已处理（消化按键）
        """
        now = time.time()

        # 检查超时
        if self._pending_keys:
            elapsed = (now - self._pending_start) * 1000
            timeout = self._get_pending_timeout()
            if elapsed > timeout:
                self._clear_pending()

        # 累积按键
        self._pending_keys.append(key_str)

        # 检查是否有绑定完全匹配
        for b in self.bindings:
            if b.keys == self._pending_keys:
                # 完全匹配
                self._clear_pending()
                try:
                    b.callback()
                except Exception as e:
                    print("[KeySeq] 执行失败: %s" % e)
                return True

        # 检查是否有绑定以此开头（前缀匹配）
        has_prefix = any(
            b.keys[:len(self._pending_keys)] == self._pending_keys
            for b in self.bindings
        )

        if has_prefix:
            # 显示等待提示
            display = " ".join(self._pending_keys)
            self.status_changed.emit(
                display + " ... (等待第二个键)"
            )
            self._pending_start = now
            self._timeout_timer.start(self._get_pending_timeout())
            return True

        # 无匹配，清除
        self._clear_pending()
        return False

    def _get_pending_timeout(self) -> int:
        """获取当前 pending 的超时时间"""
        for b in self.bindings:
            if b.keys[:len(self._pending_keys)] == self._pending_keys:
                return b.timeout_ms
        return 2000

    def _clear_pending(self):
        """清除 pending 状态"""
        if self._pending_keys:
            self._pending_keys = []
            self.status_changed.emit("")
        self._timeout_timer.stop()

    def _on_timeout(self):
        """超时清除"""
        self._clear_pending()

    def is_waiting(self) -> bool:
        """是否正在等待第二个键"""
        return len(self._pending_keys) > 0

    def cancel(self):
        """取消等待"""
        self._clear_pending()


# 便捷函数：把 QKeySequence 或字符串转为标准键名
def key_event_to_string(event) -> str:
    """把 QKeyEvent 转为标准键名字符串"""
    from PyQt5.QtCore import Qt

    parts = []
    mods = event.modifiers()
    if mods & Qt.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.AltModifier:
        parts.append("Alt")
    if mods & Qt.MetaModifier:
        parts.append("Meta")

    key = event.key()
    # 特殊键映射
    key_map = {
        Qt.Key_Space: "Space",
        Qt.Key_Tab: "Tab",
        Qt.Key_Return: "Enter",
        Qt.Key_Enter: "Enter",
        Qt.Key_Escape: "Esc",
        Qt.Key_Backspace: "Backspace",
        Qt.Key_Delete: "Delete",
        Qt.Key_Insert: "Insert",
        Qt.Key_Home: "Home",
        Qt.Key_End: "End",
        Qt.Key_PageUp: "PageUp",
        Qt.Key_PageDown: "PageDown",
        Qt.Key_Up: "Up",
        Qt.Key_Down: "Down",
        Qt.Key_Left: "Left",
        Qt.Key_Right: "Right",
    }

    if key in key_map:
        parts.append(key_map[key])
    elif Qt.Key_A <= key <= Qt.Key_Z:
        parts.append(chr(key))
    elif Qt.Key_0 <= key <= Qt.Key_9:
        parts.append(chr(key))
    elif Qt.Key_F1 <= key <= Qt.Key_F12:
        parts.append("F" + str(key - Qt.Key_F1 + 1))
    else:
        text = event.text()
        if text and text.isprintable():
            parts.append(text.upper())
        else:
            return ""

    return "+".join(parts)