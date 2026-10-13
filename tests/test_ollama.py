# -*- coding: utf-8 -*-
"""Ollama 本地模型管理功能测试

覆盖两层：
  * `core/ollama_client.py` —— REST 客户端（**不依赖 Ollama 是否运行**，
    连不上时验证的是优雅降级）
  * `plugins/ai_assistant.OllamaPanel` —— 面板的可构造性与离线状态

设计原则：**不要求本机运行 Ollama**。需要真实服务的用例在检测不到
服务时 skip，避免在 CI 上产生假失败。
"""
import os
import sys

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ollama_client import DEFAULT_HOST, OllamaClient  # noqa: E402


# 服务可用性只在首次调用时探测并缓存。
# 若每次收集用例都调用（skipif 在收集阶段求值），会对未监听端口反复做
# TCP 连接尝试 —— 实测把整个套件从约 20s 拖到约 80s。
_SERVICE_UP = None


def _service_up() -> bool:
    global _SERVICE_UP
    if _SERVICE_UP is None:
        try:
            _SERVICE_UP = OllamaClient().is_running()
        except Exception:
            _SERVICE_UP = False
    return _SERVICE_UP


# =========================================================
# OllamaClient
# =========================================================

class TestOllamaClientOffline:
    """连不上时必须优雅降级，绝不抛异常"""

    def _bad(self):
        # 用一个几乎不可能被占用的端口
        return OllamaClient("http://127.0.0.1:59997")

    def test_is_running_false(self):
        assert self._bad().is_running() is False

    def test_status_text_reports_error(self):
        ok, text = self._bad().status_text()
        assert ok is False
        assert text  # 必须给出可读原因，不能空串

    def test_list_models_returns_empty_not_raise(self):
        ok, models = self._bad().list_models()
        assert ok is False
        assert models == []

    def test_list_running_returns_empty(self):
        ok, running = self._bad().list_running()
        assert ok is False
        assert running == []

    def test_delete_empty_name_rejected(self):
        ok, msg = self._bad().delete_model("")
        assert ok is False and msg

    def test_pull_empty_name_rejected(self):
        ok, msg = self._bad().pull_model("")
        assert ok is False and msg

    def test_version_none_when_offline(self):
        assert self._bad().version() is None


class TestOllamaClientHelpers:
    """不依赖服务的纯函数"""

    def test_format_size(self):
        assert OllamaClient.format_size(0) == "0 B"
        assert OllamaClient.format_size(512) == "512 B"
        assert OllamaClient.format_size(1024) == "1.0 KB"
        assert OllamaClient.format_size(1536) == "1.5 KB"
        assert OllamaClient.format_size(1024 ** 2) == "1.0 MB"
        assert OllamaClient.format_size(1024 ** 3) == "1.0 GB"
        # 非法输入不应抛异常
        assert OllamaClient.format_size(None) == "-"
        assert OllamaClient.format_size("abc") == "-"

    def test_openai_base_url(self):
        assert OllamaClient().openai_base_url() == "http://localhost:11434/v1"
        assert (OllamaClient("http://192.168.1.9:11434/")
                .openai_base_url() == "http://192.168.1.9:11434/v1")

    def test_host_normalised(self):
        # 结尾斜杠会被去掉，避免拼出 //api/tags
        assert OllamaClient("http://h:1/").host == "http://h:1"

    def test_default_host_used_for_empty(self):
        assert OllamaClient("").host == DEFAULT_HOST


@pytest.mark.skipif(not _service_up(), reason="本机未运行 Ollama 服务")
class TestOllamaClientLive:
    """需要真实 Ollama 服务"""

    def test_version_present(self):
        assert OllamaClient().version()

    def test_list_models_shape(self):
        ok, models = OllamaClient().list_models()
        assert ok is True
        for m in models:
            # 每个必备字段都要存在，UI 依赖它们
            for key in ("name", "size", "size_text", "modified_at",
                        "family", "parameter_size", "quantization"):
                assert key in m, "缺少字段 %s" % key
            assert m["name"]

    def test_status_text_ok(self):
        ok, text = OllamaClient().status_text()
        assert ok is True
        assert "运行中" in text


# =========================================================
# OllamaPanel（离屏）
# =========================================================

class TestOllamaPanel:
    """面板必须能离线构造，并在离线时给出提示"""

    def test_panel_constructs_offline(self, qtbot):
        from plugins.ai_assistant import OllamaPanel
        panel = OllamaPanel(plugin=None, auto_refresh=False)
        qtbot.addWidget(panel)
        assert panel.model_list is not None
        assert panel.status_label is not None
        # 未连接时不应崩溃
        summary = panel.status_summary()
        assert isinstance(summary, str) and summary

    def test_panel_status_summary_offline(self):
        from plugins.ai_assistant import OllamaPanel
        panel = OllamaPanel(plugin=None, auto_refresh=False)
        panel._client = OllamaClient("http://127.0.0.1:59997")
        panel._stop_threads(50)
        assert panel.status_summary() == "Ollama: 未启动"

    def test_stop_threads_is_safe_when_idle(self):
        from plugins.ai_assistant import OllamaPanel
        panel = OllamaPanel(plugin=None, auto_refresh=False)
        panel._stop_threads(50)
        panel._stop_threads(50)      # 幂等
        panel.close()


@pytest.mark.skipif(not _service_up(), reason="本机未运行 Ollama 服务")
class TestOllamaPanelLive:
    def test_panel_populates_models(self, qtbot):
        from plugins.ai_assistant import OllamaPanel
        panel = OllamaPanel(plugin=None, auto_refresh=False)
        qtbot.addWidget(panel)
        ok, models = panel._client.list_models()
        # 直接喂数据，避免依赖定时器时序
        panel._populate(models, [])
        assert panel.model_list.count() == len(models)
        if models:
            panel.model_list.setCurrentRow(0)
            assert panel._selected_name() == models[0]["name"]
            assert panel.delete_btn.isEnabled()
            assert panel.use_btn.isEnabled()

    def test_status_summary_online(self):
        from plugins.ai_assistant import OllamaPanel
        panel = OllamaPanel(plugin=None, auto_refresh=False)
        panel._stop_threads(50)
        summary = panel.status_summary()
        assert "Ollama" in summary
        assert "未启动" not in summary
        panel.close()
