# -*- coding: utf-8 -*-
"""完整 UI 隔离阶段 C：子进程远程 UI 客户端（控件树推送 + 事件轮询）。"""

from core.remote_ui import RemoteControlTree


class RemoteUIClient:
    def __init__(self, api, panel_id):
        self.api = api
        self.panel_id = int(panel_id)
        self.tree = RemoteControlTree()
        self._handlers = {}

    def add(self, control_id, kind, text="", value="", enabled=True, visible=True):
        cid = self.tree.add(
            control_id, kind, text=text, value=value, enabled=enabled, visible=visible
        )
        self.push()
        return cid

    def update(self, control_id, text=None, value=None, enabled=None, visible=None):
        node = self.tree._nodes.get(str(control_id))
        if node is None:
            return False
        if text is not None:
            node["text"] = str(text)
        if value is not None:
            node["value"] = str(value)
        if enabled is not None:
            node["enabled"] = bool(enabled)
        if visible is not None:
            node["visible"] = bool(visible)
        self.push()
        return True

    def on(self, control_id, callback):
        self._handlers[str(control_id)] = callback

    def push(self):
        try:
            return bool(self.api.update_remote_controls(self.panel_id, self.tree.to_dict()))
        except Exception:
            return False

    def poll(self):
        try:
            events = self.api.poll_remote_ui_events() or []
        except Exception:
            return 0
        handled = 0
        for ev in events:
            if int(ev.get("panel_id", -1)) != self.panel_id:
                continue
            cb = self._handlers.get(str(ev.get("id")))
            if cb is None:
                continue
            try:
                cb(ev.get("event"), ev.get("value", ""))
                handled += 1
            except Exception:
                pass
        return handled
