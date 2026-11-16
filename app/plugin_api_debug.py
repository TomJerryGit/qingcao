# -*- coding: utf-8 -*-
"""插件 API：宿主调试服务（B3-D6，feature flag 关闭时不可用）。"""

from app.plugin_api import PERMISSION_DEBUGGER


def _disabled():
    return {"ok": False, "error": "debugger host service disabled"}


class DebugMixin:
    def debug_available(self):
        from core.debug_service import host_enabled

        return bool(host_enabled() and self.require_permission(PERMISSION_DEBUGGER))

    def debug_start(self, script, args=None):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.start", {"script": script, "args": args or []})

    def debug_stop(self):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.stop")

    def debug_continue(self):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.continue")

    def debug_step(self, kind="over"):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.step", {"kind": kind})

    def debug_set_breakpoints(self, files):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.set_breakpoints", {"files": files or {}})

    def debug_locals(self):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.locals")

    def debug_stack(self):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.stack")

    def debug_eval(self, expr):
        if not self.debug_available():
            return _disabled()
        from core.debug_service import get_debug_service

        return get_debug_service().handle("debug.eval", {"expr": expr})

    def debug_show_panel(self):
        if not self.debug_available():
            return False
        from PyQt5.QtCore import Qt

        from core.debug_service import get_debug_service
        from ui.debug_host_panel import DebugHostPanel

        service = get_debug_service()
        panel = getattr(service, "_host_panel", None)
        win = self._host_window()
        if panel is None:
            panel = DebugHostPanel(service, win)
            service._host_panel = panel
            win.addDockWidget(Qt.BottomDockWidgetArea, panel)
        panel.show()
        panel.raise_()
        return True
