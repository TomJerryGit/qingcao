# -*- coding: utf-8 -*-
"""完整 UI 隔离阶段 C：远程控件协议（控件树 + 事件）。"""

MAX_NODES = 200
MAX_TEXT = 10_000
KINDS = {"label", "button", "line_edit", "check_box", "text_view", "box"}
EVENTS = {"click", "text_changed", "checked_changed"}


class RemoteControlTree:
    def __init__(self):
        self._nodes = {}
        self._order = []

    def add(self, control_id, kind, text="", value="", enabled=True, visible=True):
        cid = str(control_id)[:64]
        if not cid:
            raise ValueError("control_id 不能为空")
        if kind not in KINDS:
            raise ValueError("非法控件类型: %s" % kind)
        if len(self._nodes) >= MAX_NODES:
            raise ValueError("控件数量超过上限")
        if len(str(text)) > MAX_TEXT or len(str(value)) > MAX_TEXT:
            raise ValueError("文本超过上限")
        self._nodes[cid] = {
            "id": cid,
            "kind": kind,
            "text": str(text),
            "value": str(value),
            "enabled": bool(enabled),
            "visible": bool(visible),
        }
        if cid not in self._order:
            self._order.append(cid)
        return cid

    def remove(self, control_id):
        cid = str(control_id)
        if cid in self._nodes:
            del self._nodes[cid]
            self._order.remove(cid)
            return True
        return False

    def to_dict(self):
        return {
            "version": 1,
            "controls": [self._nodes[c] for c in self._order if c in self._nodes],
        }

    def dispatch(self, control_id, event, value=""):
        cid = str(control_id)
        if cid not in self._nodes:
            return None
        if event not in EVENTS:
            return None
        node = self._nodes[cid]
        if not node["enabled"]:
            return None
        if event == "text_changed":
            node["value"] = str(value)[:MAX_TEXT]
        elif event == "checked_changed":
            node["value"] = "1" if str(value) in ("1", "true", "True") else "0"
        return {"id": cid, "event": event, "value": str(value)[:MAX_TEXT]}
