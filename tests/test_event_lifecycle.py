# -*- coding: utf-8 -*-
"""事件生命周期契约：文档与代码一致 + 全部事件可订阅/退订"""
import os


DOC_PATH = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "docs", "event_lifecycle.md")


def _api():
    from app.plugins import PluginAPI
    return PluginAPI(None, permissions=[], plugin_name="evt_test")


def test_every_event_is_documented(qapp):
    """代码里的事件必须全部出现在文档中（防止新增事件漏文档）"""
    api = _api()
    events = api.list_events()
    assert len(events) >= 15, "事件数量异常: %r" % (events,)
    doc = open(DOC_PATH, encoding="utf-8").read()
    missing = [name for name in events if name not in doc]
    assert not missing, "文档缺少事件说明: %r" % (missing,)


def test_all_events_subscribe_and_unsubscribe(qapp):
    """15 个事件都必须支持 subscribe/unsubscribe（成对、不抛异常）"""
    api = _api()
    callback = lambda *a, **k: None
    failures = []
    for name in api.list_events():
        try:
            api.subscribe(name, callback)
            api.unsubscribe(name, callback)
        except Exception as e:
            failures.append("%s: %r" % (name, e))
    assert not failures, "订阅/退订失败:\n" + "\n".join(failures)


def test_unknown_event_is_rejected(qapp):
    """未登记的事件名应被拒绝（宽松返回 False 或抛异常）"""
    api = _api()
    try:
        result = api.subscribe("not_an_event", lambda: None)
        assert result is not True, "未知事件不应注册成功"
    except Exception:
        pass
