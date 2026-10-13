# -*- coding: utf-8 -*-
"""Ollama 本地服务 REST 客户端

背景
----
编辑器已支持 `ollama` provider（走 OpenAI 兼容端点
`http://localhost:11434/v1`），但模型下拉框用的是**硬编码列表**，
用户本地实际装了哪些模型界面上看不到，只能手工输入名称。

本模块封装 Ollama 的**原生 REST API**，用于：

  * 列出已安装模型（`GET /api/tags`）
  * 列出内存中已加载的模型（`GET /api/ps`）
  * 拉取新模型并汇报进度（`POST /api/pull`，流式 NDJSON）
  * 删除模型（`DELETE /api/delete`）
  * 连通性探测（`GET /api/version`）

设计要点
--------
* **只用标准库**（`urllib`），不新增依赖；`requests` 可选但非必需。
* **流式拉取用回调**，不阻塞调用方；`pull_model` 在**工作线程**中调用，
  通过 `progress` 回调把进度交回调用方（由调用方负责投递回主线程）。
* 所有方法**不抛异常**，统一返回 `(ok, message/data)` 或 `None`，
  便于 UI 直接展示 —— 与本项目"宽 except"风格不同，这里显式返回错误。
"""
import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple


DEFAULT_HOST = "http://localhost:11434"

# 单次请求超时（拉取模型是流式，另设 A 长超时）
REQUEST_TIMEOUT = 8
PULL_TIMEOUT = 3600            # 拉取大模型可能很久
LIST_TIMEOUT = 15              # /api/tags 在冷启动时可能较慢


class OllamaClient:
    """Ollama 原生 REST 客户端（无第三方依赖）"""

    def __init__(self, host: str = DEFAULT_HOST):
        self.host = (host or DEFAULT_HOST).rstrip("/")

    # --------------------------------------------------------
    # 内部工具
    # --------------------------------------------------------
    def _url(self, path: str) -> str:
        return "%s%s" % (self.host, path)

    def _request(self, path: str, method: str = "GET",
                 payload: Optional[Dict[str, Any]] = None,
                 timeout: int = REQUEST_TIMEOUT):
        """发一个 JSON 请求，返回 (ok, data_or_errmsg)"""
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(self._url(path), data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return True, {}
                try:
                    return True, json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    return True, {"raw": raw.decode("utf-8", "replace")}
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            return False, "HTTP %s %s" % (e.code, body)
        except urllib.error.URLError as e:
            return False, "连接失败: %s" % (e.reason,)
        except socket.timeout:
            return False, "请求超时"
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, e)

    # --------------------------------------------------------
    # 状态
    # --------------------------------------------------------
    def is_running(self) -> bool:
        """服务是否在运行（不抛异常）"""
        ok, _ = self._request("/api/version", timeout=3)
        return ok

    def version(self) -> Optional[str]:
        ok, data = self._request("/api/version", timeout=3)
        if ok and isinstance(data, dict):
            return data.get("version")
        return None

    def status_text(self) -> Tuple[bool, str]:
        """返回 (是否运行, 可展示的状态文本)"""
        ok, data = self._request("/api/version", timeout=4)
        if not ok:
            return False, "未连接（%s）" % data
        ver = data.get("version") if isinstance(data, dict) else ""
        return True, ("运行中" + (" v%s" % ver if ver else ""))

    # --------------------------------------------------------
    # 模型列表
    # --------------------------------------------------------
    @staticmethod
    def format_size(num_bytes: Any) -> str:
        """把字节数格式化成人类可读"""
        try:
            n = float(num_bytes)
        except (TypeError, ValueError):
            return "-"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024 or unit == "TB":
                return ("%.1f %s" % (n, unit)) if unit != "B" else ("%d B" % n)
            n /= 1024.0
        return "-"

    def list_models(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """列出已安装模型。

        返回 (ok, models)。每个元素至少含 name / size / modified_at /
        size_text / family。
        """
        ok, data = self._request("/api/tags", timeout=LIST_TIMEOUT)
        if not ok:
            return False, []
        models = []
        for m in (data or {}).get("models", []) or []:
            details = m.get("details") or {}
            name = m.get("name") or m.get("model") or ""
            models.append({
                "name": name,
                "size": m.get("size", 0),
                "size_text": self.format_size(m.get("size", 0)),
                "modified_at": (m.get("modified_at") or "")[:19].replace("T", " "),
                "family": details.get("family") or "",
                "parameter_size": details.get("parameter_size") or "",
                "quantization": details.get("quantization_level") or "",
            })
        models.sort(key=lambda x: x["name"])
        return True, models

    def model_names(self) -> List[str]:
        ok, models = self.list_models()
        return [m["name"] for m in models] if ok else []

    def list_running(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """列出内存中已加载的模型（/api/ps）"""
        ok, data = self._request("/api/ps", timeout=REQUEST_TIMEOUT)
        if not ok:
            return False, []
        out = []
        for m in (data or {}).get("models", []) or []:
            out.append({
                "name": m.get("name") or m.get("model") or "",
                "size": m.get("size", 0),
                "size_text": self.format_size(m.get("size", 0)),
                "expires_at": (m.get("expires_at") or "")[:19].replace("T", " "),
            })
        return True, out

    # --------------------------------------------------------
    # 拉取 / 删除
    # --------------------------------------------------------
    def pull_model(self, name: str,
                   progress: Optional[Callable[[Dict[str, Any]], bool]] = None
                   ) -> Tuple[bool, str]:
        """拉取模型（流式）。

        参数:
            name: 模型名，如 "qwen2.5:7b"
            progress: 回调，收到每个 NDJSON 事件；返回 False 可中止

        返回:
            (ok, message)
        """
        if not name or not name.strip():
            return False, "模型名不能为空"
        payload = json.dumps({"name": name.strip(),
                              "stream": True}).encode("utf-8")
        req = urllib.request.Request(
            self._url("/api/pull"), data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=PULL_TIMEOUT) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if progress is not None:
                        try:
                            if progress(event) is False:
                                return False, "已取消"
                        except Exception:
                            pass
                    if event.get("error"):
                        return False, str(event["error"])
            return True, "拉取完成"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            return False, "HTTP %s %s" % (e.code, body)
        except urllib.error.URLError as e:
            return False, "连接失败: %s" % (e.reason,)
        except socket.timeout:
            return False, "拉取超时"
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, e)

    def delete_model(self, name: str) -> Tuple[bool, str]:
        """删除模型"""
        if not name:
            return False, "模型名不能为空"
        ok, data = self._request("/api/delete", method="DELETE",
                                 payload={"name": name})
        if ok:
            return True, "已删除 %s" % name
        return False, str(data)

    def show_model(self, name: str) -> Tuple[bool, Dict[str, Any]]:
        """获取模型详情（/api/show）"""
        if not name:
            return False, {}
        ok, data = self._request("/api/show", method="POST",
                                 payload={"name": name})
        return ok, (data if isinstance(data, dict) else {})

    # --------------------------------------------------------
    # 让编辑器 AI 配置直接可用的辅助
    # --------------------------------------------------------
    def openai_base_url(self) -> str:
        """编辑器 AI 配置里应填的 Base URL（OpenAI 兼容端点）"""
        return "%s/v1" % self.host
