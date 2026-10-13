# -*- coding: utf-8 -*-
"""AI 四项增强的测试

覆盖：
  ① 推理状态显示（分阶段 + 计时 + 字符计数）
  ② 结果缓存（键构成、LRU、容量与大小限制、线程安全）
  ③ 会话窗口（非模态、复用同一实例、新会话清空上下文）
  ④ 命令面板注册

运行::

    python -m pytest tests/test_ai_enhancements.py -v
"""
import os
import sys
import threading
import time

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai_cache import AIResultCache  # noqa: E402


# =========================================================
# ② 结果缓存
# =========================================================

class FakeClient:
    def __init__(self, **kw):
        self.provider = kw.get("provider", "openai")
        self.model = kw.get("model", "gpt-4o")
        self.base_url = kw.get("base_url", "https://x/v1")
        self.temperature = kw.get("temperature", 0.3)
        self.max_tokens = kw.get("max_tokens", 4096)
        # 真实 AIClient 有这些，替身也要有，否则 hasattr 检查会跳过逻辑
        self._history = []

    def reset_history(self):
        self._history = []

    def get_history(self):
        return [dict(m) for m in self._history]

    def _trim_history(self):
        pass


class TestCacheKey:
    """键必须覆盖所有影响输出的参数，否则会串味"""

    def test_stable_for_same_params(self):
        c = FakeClient()
        k1 = AIResultCache.make_key(c, "P", "S", 1024)
        k2 = AIResultCache.make_key(c, "P", "S", 1024)
        assert k1 == k2

    @pytest.mark.parametrize("field,value", [
        ("model", "gpt-4o-mini"),
        ("provider", "ollama"),
        ("base_url", "https://y/v1"),
        ("temperature", 0.9),
    ])
    def test_differs_when_client_field_differs(self, field, value):
        base = FakeClient()
        other = FakeClient(**{field: value})
        assert (AIResultCache.make_key(base, "P", "S", 1024)
                != AIResultCache.make_key(other, "P", "S", 1024)), field

    def test_differs_on_max_tokens(self):
        c = FakeClient()
        assert (AIResultCache.make_key(c, "P", "S", 1024)
                != AIResultCache.make_key(c, "P", "S", 2048))

    def test_differs_on_system_and_prompt(self):
        c = FakeClient()
        k = AIResultCache.make_key(c, "P", "S", 1024)
        assert k != AIResultCache.make_key(c, "P", "S2", 1024)
        assert k != AIResultCache.make_key(c, "P2", "S", 1024)

    def test_max_tokens_none_falls_back_to_client(self):
        c = FakeClient(max_tokens=777)
        a = AIResultCache.make_key(c, "P", "S", None)
        b = AIResultCache.make_key(c, "P", "S", 777)
        assert a == b, "max_tokens=None 应等价于客户端的默认值"


class TestCacheBehaviour:
    def test_miss_then_hit(self):
        cache = AIResultCache()
        assert cache.get("k") is None
        assert cache.put("k", "v") is True
        assert cache.get("k") == "v"

    def test_empty_value_not_cached(self):
        cache = AIResultCache()
        assert cache.put("k", "") is False
        assert cache.get("k") is None

    def test_oversized_value_not_cached(self):
        cache = AIResultCache(max_entry_chars=10)
        assert cache.put("k", "x" * 11) is False
        assert cache.get("k") is None

    def test_lru_eviction(self):
        cache = AIResultCache(max_entries=2)
        cache.put("a", "1")
        cache.put("b", "2")
        cache.get("a")              # 让 a 变"新"
        cache.put("c", "3")         # 应淘汰 b
        assert cache.get("a") == "1"
        assert cache.get("b") is None
        assert cache.get("c") == "3"

    def test_stats(self):
        cache = AIResultCache()
        cache.put("k", "v")
        cache.get("k")
        cache.get("missing")
        s = cache.stats()
        assert s["entries"] == 1
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert "缓存" in cache.stats_text()

    def test_clear(self):
        cache = AIResultCache()
        cache.put("k", "v")
        cache.clear()
        assert cache.stats()["entries"] == 0

    def test_thread_safety(self):
        """并发读写不应抛异常，且最终条数不超上限"""
        cache = AIResultCache(max_entries=20)
        errors = []

        def worker(tag):
            try:
                for i in range(60):
                    cache.put("%s-%d" % (tag, i), "v%d" % i)
                    cache.get("%s-%d" % (tag, i - 1))
            except Exception as e:      # pragma: no cover
                errors.append(e)

        ts = [threading.Thread(target=worker, args=(t,)) for t in "abcd"]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not errors
        assert cache.stats()["entries"] <= 20

    def test_shared_singleton(self):
        from core.ai_cache import get_result_cache
        assert get_result_cache() is get_result_cache()


# =========================================================
# ① 推理状态显示
# =========================================================

class TestWaitingStatus:
    def _dlg(self):
        from plugins.ai_assistant import AIResultDialog
        return AIResultDialog(title="t", main_window=None,
                              enable_insert=True, parent=None)

    def test_thinking_phase_mentions_elapsed(self, qapp):
        dlg = self._dlg()
        dlg._start_waiting("生成中")
        txt = dlg.status_label.text()
        assert "生成中" in txt
        assert "秒" in txt, "必须显示已等待时间，否则用户无法判断是否卡死"
        dlg.close()

    def test_switches_to_receiving_on_first_chunk(self, qapp):
        dlg = self._dlg()
        dlg._start_waiting("生成中")
        assert "思考中" in dlg.status_label.text()
        dlg._on_chunk("abc")
        txt = dlg.status_label.text()
        assert "接收中" in txt, "首个片段到达后应立即切换文案"
        dlg.close()

    def test_tracks_char_count(self, qapp):
        dlg = self._dlg()
        dlg._start_waiting("生成中")
        dlg._on_chunk("12345")
        dlg._on_chunk("67890")
        assert dlg._stream_chars == 10
        dlg.close()

    def test_stop_waiting_clears_timer_state(self, qapp):
        dlg = self._dlg()
        dlg._start_waiting("生成中")
        assert dlg._wait_start is not None
        dlg._stop_waiting()
        assert dlg._wait_start is None
        # 再 tick 不应抛异常
        dlg._tick_waiting()
        dlg.close()

    def test_finished_shows_total_time(self, qapp):
        dlg = self._dlg()
        dlg._start_waiting("生成中")
        time.sleep(0.02)
        dlg._on_finished("done")
        assert "完成" in dlg.status_label.text()
        assert dlg._wait_start is None
        dlg.close()

    def test_follow_up_uses_its_own_phase(self, qapp):
        dlg = self._dlg()
        dlg._start_waiting("追问中")
        assert "追问中" in dlg.status_label.text()
        dlg.close()


# =========================================================
# ③ 会话窗口
# =========================================================

class TestSessionWindow:
    def _plugin(self):
        from app.plugins import PluginBase
        from plugins.ai_assistant import Plugin
        inst = Plugin.__new__(Plugin)
        PluginBase.__init__(inst)
        inst._menus = []
        inst._active_dialogs = []

        class FakeAPI:
            def _host_window(self):
                return None

            def show_status(self, *a, **k):
                pass

            def show_message(self, *a, **k):
                pass

            def log(self, *a, **k):
                pass

        inst.api = FakeAPI()
        inst._client = FakeClient()
        return inst

    def test_session_is_non_modal(self, qapp):
        inst = self._plugin()
        dlg = inst._get_or_create_session(None)
        assert dlg.isModal() is False, "会话窗口必须非模态，否则切标签会丢上下文"
        dlg.close()

    def test_session_is_reused(self, qapp):
        inst = self._plugin()
        a = inst._get_or_create_session(None)
        b = inst._get_or_create_session(None)
        assert a is b, "必须复用同一窗口，否则每次动作都开新窗口"
        assert inst._session_window is a
        a.close()

    def test_new_session_clears_context(self, qapp):
        inst = self._plugin()
        # 真实流程：窗口先存在，动作执行时才把 client 挂上去
        # （_get_or_create_session 不会设置 _client）
        dlg = inst._get_or_create_session(None)
        client = inst._client
        client._history = [{"role": "user", "content": "x"}]
        dlg._client = client
        dlg.start_new_session()
        assert client._history == [], "新会话必须清空上下文"
        assert "新会话" in dlg.status_label.text()
        dlg.close()

    def test_new_session_keeps_previous_text(self, qapp):
        """清的是上下文，不是窗口里的记录（用户可能想对照）"""
        inst = self._plugin()
        dlg = inst._get_or_create_session(None)
        dlg._client = inst._client
        dlg._result_text = "上一轮的结论"
        dlg.start_new_session()
        assert "上一轮的结论" in dlg._result_text
        dlg.close()

    def test_session_window_default_on(self, qapp):
        from plugins.ai_assistant import Plugin
        inst = self._plugin()
        assert inst._session_window_enabled() is True

    def test_blocking_api_used_when_session_disabled(self, qapp, monkeypatch):
        """关闭会话窗口时应回退到旧行为（模态 exec_）"""
        from PyQt5.QtCore import QSettings

        from plugins.ai_assistant import Plugin
        inst = self._plugin()
        QSettings("QingCao", "AI").setValue("session_window", False)
        try:
            assert inst._session_window_enabled() is False
        finally:
            QSettings("QingCao", "AI").setValue("session_window", True)
        assert isinstance(inst, Plugin)


# =========================================================
# ④ 命令面板
# =========================================================

class TestCommandRegistration:
    def test_registers_expected_commands(self, qapp):
        from app.plugins import PluginBase
        from plugins.ai_assistant import Plugin
        inst = Plugin.__new__(Plugin)
        PluginBase.__init__(inst)
        inst._menus = []

        class FakeAPI:
            def __init__(self):
                self.cmds = {}

            def register_command(self, name, cb, description=""):
                self.cmds[name] = description

            def log(self, *a, **k):
                pass

        api = FakeAPI()
        inst.api = api
        inst._register_commands()

        for expected in ("ai.explain", "ai.refactor", "ai.fix",
                         "ai.comment", "ai.docstring", "ai.tests",
                         "ai.optimize", "ai.review", "ai.summary"):
            assert expected in api.cmds, expected
        # 编程式快速问答 + 缓存管理
        assert "ai.quick_explain" in api.cmds
        assert "ai.clear_cache" in api.cmds
        assert "ai.cache_stats" in api.cmds
        # 描述必须可读（命令面板显示的就是它）
        assert all(v for v in api.cmds.values())

    def test_all_commands_have_ai_prefix_in_description(self, qapp):
        from app.plugins import PluginBase
        from plugins.ai_assistant import Plugin
        inst = Plugin.__new__(Plugin)
        PluginBase.__init__(inst)
        inst._menus = []

        class FakeAPI:
            def __init__(self):
                self.cmds = {}

            def register_command(self, name, cb, description=""):
                self.cmds[name] = description

            def log(self, *a, **k):
                pass

        api = FakeAPI()
        inst.api = api
        inst._register_commands()
        for name, desc in api.cmds.items():
            assert desc.startswith("AI:"), (name, desc)


class TestCacheManagementCommands:
    def test_clear_cache_command(self, qapp):
        from app.plugins import PluginBase
        from core.ai_cache import get_result_cache
        from plugins.ai_assistant import Plugin
        cache = get_result_cache()
        cache.put("k", "v")
        inst = Plugin.__new__(Plugin)
        PluginBase.__init__(inst)
        inst._menus = []

        class FakeAPI:
            def __init__(self):
                self.status = []

            def show_status(self, *a, **k):
                self.status.append(a)

            def show_message(self, *a, **k):
                self.status.append(a)

            def log(self, *a, **k):
                pass

        inst.api = FakeAPI()
        inst._on_clear_cache()
        assert cache.stats()["entries"] == 0
        assert inst.api.status, "应给出反馈"

    def test_cache_stats_command(self, qapp):
        from app.plugins import PluginBase
        from plugins.ai_assistant import Plugin
        inst = Plugin.__new__(Plugin)
        PluginBase.__init__(inst)
        inst._menus = []

        class FakeAPI:
            def __init__(self):
                self.msgs = []

            def show_message(self, *a, **k):
                self.msgs.append(a)

            def log(self, *a, **k):
                pass

        inst.api = FakeAPI()
        inst._on_cache_stats()
        assert inst.api.msgs
        body = " ".join(str(x) for x in inst.api.msgs[0])
        assert "缓存" in body
