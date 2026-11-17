# -*- coding: utf-8 -*-
"""AI 宿主服务（B3）：插件经 RPC 使用宿主 AI 客户端/网络，API Key 不进入子进程。"""

import io
import json
import os

from core.ai_client import (
    AIClientError,
    AIConfigError,
    load_ai_client_from_settings,
    load_secret,
    save_secret,
    set_ai_client,
)


class AIService:
    def __init__(self, client=None, history_path=None, encrypt=False, cipher_key=None):
        self._client = client
        self._stream_listener = None
        self._sessions = {}
        self._current_session = "default"
        self._history_path = history_path
        self._encrypt = bool(encrypt)
        self._cipher_key = cipher_key
        self.reload_history()

    def _fernet(self):
        if not self._encrypt:
            return None
        try:
            from cryptography.fernet import Fernet
        except Exception:
            return None
        key = self._cipher_key
        if not key:
            key = load_secret("ai_sessions_key", "")
            if not key:
                key = Fernet.generate_key().decode("ascii")
                save_secret("ai_sessions_key", key)
        try:
            return Fernet(key.encode("ascii") if isinstance(key, str) else key)
        except Exception:
            return None

    def reload_history(self):
        if not self._history_path or not os.path.isfile(self._history_path):
            return False
        try:
            raw = io.open(self._history_path, encoding="utf-8").read()
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("encrypted"):
                fernet = self._fernet()
                if fernet is None:
                    return False
                data = json.loads(fernet.decrypt(str(data.get("data", "")).encode("utf-8")))
            sessions = data.get("sessions") or {}
            if not isinstance(sessions, dict):
                return False
            self._sessions = {str(k): list(v) for k, v in sessions.items() if isinstance(v, list)}
            self._current_session = str(data.get("current") or "default")
            self._sessions.setdefault(self._current_session, [])
            return True
        except Exception:
            return False

    def save_history(self):
        if not self._history_path:
            return False
        try:
            parent = os.path.dirname(self._history_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            tmp = self._history_path + ".tmp"
            payload = {
                "version": 1,
                "current": self._current_session,
                "sessions": self._sessions,
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            fernet = self._fernet()
            if fernet is not None:
                text = json.dumps(
                    {
                        "version": 1,
                        "encrypted": True,
                        "data": fernet.encrypt(text.encode("utf-8")).decode("ascii"),
                    }
                )
            io.open(tmp, "w", encoding="utf-8", newline="\n").write(text)
            os.replace(tmp, self._history_path)
            return True
        except Exception:
            return False

    def get_session(self, name):
        return [dict(m) for m in self._sessions.get(str(name), [])]

    def search_sessions(self, query, session=None, limit=100,
                        role=None, current_only=False):
        q = str(query or "").strip().lower()
        if not q:
            return {"ok": True, "matches": [], "count": 0}
        if current_only:
            session = self._current_session
        names = [str(session)] if session else list(self._sessions)
        wanted_role = str(role or "").strip().lower()
        matches = []
        for name in names:
            for idx, msg in enumerate(self._sessions.get(name, [])):
                content = str((msg or {}).get("content", ""))
                role = str((msg or {}).get("role", ""))
                if wanted_role and role.lower() != wanted_role:
                    continue
                if q in content.lower() or q in role.lower():
                    matches.append(
                        {
                            "session": name,
                            "index": idx,
                            "role": role,
                            "content": content[:200],
                        }
                    )
                    if len(matches) >= max(1, int(limit)):
                        return {"ok": True, "matches": matches, "count": len(matches)}
        return {"ok": True, "matches": matches, "count": len(matches)}

    def export_sessions(self, path, names=None):
        sessions = self._sessions
        if names is not None:
            wanted = {str(n) for n in names}
            sessions = {k: v for k, v in self._sessions.items() if k in wanted}
        payload = {
            "version": 1,
            "current": self._current_session,
            "sessions": sessions,
        }
        try:
            io.open(path, "w", encoding="utf-8", newline="\n").write(
                json.dumps(payload, ensure_ascii=False, indent=2)
            )
            return {"ok": True, "count": len(sessions)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _read_import(self, path):
        data = json.load(io.open(path, encoding="utf-8"))
        if isinstance(data, dict) and data.get("encrypted"):
            fernet = self._fernet()
            if fernet is None:
                raise ValueError("需要加密密钥")
            data = json.loads(fernet.decrypt(str(data.get("data", "")).encode("utf-8")))
        sessions = data.get("sessions")
        if not isinstance(sessions, dict):
            raise ValueError("格式错误")
        return {str(k): list(v) for k, v in sessions.items() if isinstance(v, list)}

    def preview_import(self, path, conflict="rename"):
        try:
            imported = self._read_import(path)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        new = []
        conflicts = []
        for name in imported:
            if name not in self._sessions:
                new.append(name)
                continue
            if conflict == "skip":
                conflicts.append({"name": name, "action": "skip", "result": name})
            elif conflict == "overwrite":
                conflicts.append({"name": name, "action": "overwrite", "result": name})
            else:
                base = name
                idx = 2
                candidate = name
                while candidate in self._sessions:
                    candidate = "%s (%d)" % (base, idx)
                    idx += 1
                conflicts.append({"name": name, "action": "rename", "result": candidate})
        return {"ok": True, "new": new, "conflicts": conflicts, "count": len(imported)}

    def import_sessions(self, path, merge=True, conflict="rename"):
        try:
            data = json.load(io.open(path, encoding="utf-8"))
            if isinstance(data, dict) and data.get("encrypted"):
                fernet = self._fernet()
                if fernet is None:
                    return {"ok": False, "error": "需要加密密钥"}
                data = json.loads(fernet.decrypt(str(data.get("data", "")).encode("utf-8")))
            sessions = data.get("sessions")
            if not isinstance(sessions, dict):
                return {"ok": False, "error": "格式错误"}
            imported = {str(k): list(v) for k, v in sessions.items() if isinstance(v, list)}
            if not merge:
                self._sessions = imported
                self.save_history()
                return {
                    "ok": True,
                    "count": len(imported),
                    "renamed": 0,
                    "skipped": 0,
                    "overwritten": 0,
                }
            stats = {"renamed": 0, "skipped": 0, "overwritten": 0}
            for name, messages in imported.items():
                if name not in self._sessions:
                    self._sessions[name] = messages
                    continue
                if conflict == "skip":
                    stats["skipped"] += 1
                elif conflict == "overwrite":
                    self._sessions[name] = messages
                    stats["overwritten"] += 1
                else:
                    base = name
                    idx = 2
                    while name in self._sessions:
                        name = "%s (%d)" % (base, idx)
                        idx += 1
                    self._sessions[name] = messages
                    stats["renamed"] += 1
            self._sessions.setdefault(self._current_session, [])
            self.save_history()
            return {"ok": True, "count": len(imported), **stats}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
        self.save_history()
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
        self.save_history()
        return {"ok": True, "session": new}

    def delete_session(self, session):
        name = str(session or "").strip() or "default"
        if name not in self._sessions:
            return {"ok": False, "error": "会话不存在"}
        self._sessions.pop(name, None)
        if self._current_session == name:
            self._current_session = "default"
            self._sessions.setdefault("default", [])
        self.save_history()
        return {"ok": True}

    def reset_history(self, session="default"):
        self._sessions.pop(str(session), None)
        self.save_history()
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
            self.save_history()
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
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _SERVICE = AIService(history_path=os.path.join(root, "data", "ai_host_sessions.json"))
    return _SERVICE


def set_ai_service(service):
    global _SERVICE
    _SERVICE = service
