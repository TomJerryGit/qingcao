# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""AI 请求工作线程（v2.24 从 __init__.py 拆出）。"""

from .ai_common import *  # noqa: F401,F403,F405


class AIWorker(QThread):
    """
    AI 请求线程（流式）。

    信号:
        chunk_received(str): 收到流式片段
        finished_ok(str): 完成（完整文本）
        finished_err(str): 失败（错误信息）
    """

    chunk_received = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

    def __init__(
        self,
        client,
        prompt: str,
        system: str = "",
        parent=None,
        use_history: bool = False,
        max_tokens=None,
    ):
        super().__init__(parent)
        self.client = client
        self.prompt = prompt
        self.system = system
        self._cancelled = False
        # 多轮上下文：True 时该请求会带上之前轮次并记录本轮
        self.use_history = bool(use_history)
        # 按任务分档的 token 上限（None = 用客户端默认）
        self.max_tokens = max_tokens

    def cancel(self):
        """取消请求"""
        self._cancelled = True

    def run(self):
        """
        执行请求。

        修复说明（P1-5）:
            - 原实现中 `except` 块的缩进为 16 空格（比对应的
              `try` 多 4 个空格），导致整个文件编译时报
              SyntaxError: invalid syntax，插件无法加载。
            - 此处修正为 8 空格，与 `try` 对齐。
        """
        try:
            if self.client is None:
                self.finished_err.emit("未配置 AI 客户端")
                return

            # 尝试流式调用
            full_text = ""
            stream_kw = {"use_history": self.use_history}
            if self.max_tokens:
                stream_kw["max_tokens"] = self.max_tokens
            if hasattr(self.client, "chat_stream"):
                try:

                    def _on_chunk(text):
                        self.chunk_received.emit(text)

                    full_text = self.client.chat_stream(
                        prompt=self.prompt,
                        system=self.system,
                        callback=_on_chunk,
                        **stream_kw,
                    )
                except Exception as e:
                    # 流式失败，回退到非流式
                    print(f"[AI插件] 流式失败，回退: {e}")
                    full_text = self.client.chat(
                        prompt=self.prompt,
                        system=self.system,
                        use_history=self.use_history,
                    )
            else:
                # 无流式接口，直接调用
                full_text = self.client.chat(
                    prompt=self.prompt,
                    system=self.system,
                    use_history=self.use_history,
                )

            if self._cancelled:
                self.finished_err.emit("已取消")
                return

            self.finished_ok.emit(full_text or "")

        except Exception as e:
            import traceback

            traceback.print_exc()
            # 翻译常见错误为友好提示
            friendly_msg = self._friendly_error(str(e), self.client)
            self.finished_err.emit(friendly_msg)

    @staticmethod
    def _friendly_error(raw: str, client) -> str:
        """把底层错误翻译为友好的中文提示"""
        provider = getattr(client, "provider", "") if client else ""
        base_url = getattr(client, "base_url", "") if client else ""

        # 连接被拒绝
        if "Connection refused" in raw or "WinError 10061" in raw or "积极拒绝" in raw:
            if provider == "ollama":
                return (
                    "无法连接到 Ollama 服务（localhost:11434）。\n\n"
                    "请尝试：\n"
                    "  1. 启动 Ollama：在终端运行 `ollama serve`\n"
                    "  2. 或从 https://ollama.com/download 安装 Ollama\n"
                    "  3. 或切换 AI 提供商：工具 → AI 助手 → 配置 AI\n"
                )
            return f"无法连接到服务器：{base_url or '未知'}\n\n请检查网络连接，或切换 AI 提供商。"

        # 超时
        if "timeout" in raw.lower() or "timed out" in raw.lower():
            return "请求超时（服务器响应过慢）。\n\n请检查网络，或换一个模型/提供商。"

        # 认证失败
        if "401" in raw or "Unauthorized" in raw or "API Key 无效" in raw:
            return "API Key 无效或未配置。\n\n请打开：工具 → AI 助手 → 配置 AI，重新填写。"

        # 404 / 找不到
        if "404" in raw:
            return (
                f"服务器返回 404（模型或路径不存在）。\n\n"
                f"请检查 Model 名称是否正确。\n"
                f"当前 base_url: {base_url or '未知'}"
            )

        # 限流
        if "429" in raw or "rate limit" in raw.lower():
            return "请求频率超过限制（429）。\n\n请稍后再试，或升级 API 套餐。"

        # 默认：原样返回
        return raw


# ============================================================
# AI 结果对话框
# ============================================================
