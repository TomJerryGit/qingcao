# -*- coding: utf-8 -*-
"""AI 宿主服务（B3）：插件经 RPC 使用宿主 AI 客户端/网络，API Key 不进入子进程。"""

from core.ai_client import (
    AIClientError,
    AIConfigError,
    load_ai_client_from_settings,
    set_ai_client,
)


class AIService:
    def __init__(self, client=None):
        self._client = client
        self._stream_listener = None
        self._sessions = {}
        self._current_session = "default"

    def set_stream_listener(self, fn):
        self._stream_listener = fn

    def _ensure(self):
        if self._client is None:
            self._client = load_ai_client_from_settings()
        return self._client

    def current_session(self):
        return self._current_session

    def set_current_session(self, session):
        name = str(session or "default").strip() or "default"
        self._current_session = name
        self._sessions.setdefault(name, [])
        return {"ok": True, "session": name}

    def session_names(self):
        return sorted(self._sessions)

    def rename_session(self, old, new):
        old = str(old or "").strip() or "default"
        new = str(new or "").strip() or "default"
        if old == new:
            return {"ok": True, "session": new}
        if old not in self._sessions:
            return {"ok": False, "error": "会话不存在"}
        if new in self._sessions:
            return {"ok": False, "error": "目标会话已存在"}
        self._sessions[new] = self._sessions.pop(old)
        if self._current_session == old:
            self._current_session = new
        return {"ok": True, "session": new}

    def delete_session(self, session):
        name = str(session or "").strip() or "default"
        if name not in self._sessions:
            return {"ok": False, "error": "会话不存在"}
        self._sessions.pop(name, None)
        if self._current_session == name:
            self._current_session = "default"
            self._sessions.setdefault("default", [])
        return {"ok": True}

    def reset_history(self, session="default"):
        self._sessions.pop(str(session), None)
        return {"ok": True}

    def run(
        self, prompt, system="", max_tokens=None, stream=False, use_history=False, session="default"
    ):
        if not str(prompt or "").strip():
            return {"ok": False, "error": "empty prompt"}
        client = self._ensure()
        if client is None:
            return {"ok": False, "error": "AI 未配置"}
        try:
            kwargs = {}
            if max_tokens:
                kwargs["max_tokens"] = int(max_tokens)
            if stream:
                chunks = []

                def _cb(chunk):
                    chunks.append(str(chunk))
                    if self._stream_listener is not None:
                        try:
                            self._stream_listener(str(chunk))
                        except Exception:
                            pass

                text = client.chat_stream(
                    prompt=str(prompt),
                    system=str(system or ""),
                    callback=_cb,
                    use_history=use_history,
                    **kwargs,
                )
                return {"ok": True, "text": str(text or ""), "chunks": chunks}
            history = self._sessions.setdefault(str(session), [])
            messages = history + [{"role": "user", "content": str(prompt)}]
            text = client.chat(
                prompt=str(prompt),
                system=str(system or ""),
                messages=messages,
                use_history=False,
                **kwargs,
            )
            history.append({"role": "user", "content": str(prompt)})
            history.append({"role": "assistant", "content": str(text or "")})
            return {"ok": True, "text": str(text or "")}
        except AIConfigError as e:
            return {"ok": False, "error": str(e)}
        except AIClientError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}


_SERVICE = None


def get_ai_service():
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AIService()
    return _SERVICE


def set_ai_service(service):
    global _SERVICE
    _SERVICE = service
