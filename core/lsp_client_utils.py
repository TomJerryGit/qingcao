# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""LSP 客户端工具/能力方法（v2.25 从 lsp_client 拆出）。"""

from core.lsp_client_common import *  # noqa: F401,F403


class LspUtilsMixin:
    def _default_capabilities(self) -> Dict[str, Any]:
        """默认客户端能力"""
        return {
            "workspace": {
                "applyEdit": True,
                "workspaceEdit": {
                    "documentChanges": True,
                },
                "didChangeConfiguration": {
                    "dynamicRegistration": False,
                },
                "didChangeWatchedFiles": {
                    "dynamicRegistration": False,
                },
                "symbol": {
                    "dynamicRegistration": False,
                },
                "executeCommand": {
                    "dynamicRegistration": False,
                },
            },
            "textDocument": {
                "synchronization": {
                    "dynamicRegistration": False,
                    "willSave": True,
                    "willSaveWaitUntil": True,
                    "didSave": True,
                },
                "completion": {
                    "dynamicRegistration": False,
                    "completionItem": {
                        "snippetSupport": True,
                        "commitCharactersSupport": True,
                        "documentationFormat": ["markdown", "plaintext"],
                        "resolveSupport": {
                            "properties": ["documentation", "detail"],
                        },
                    },
                    "completionItemKind": {
                        "valueSet": list(range(1, 26)),
                    },
                },
                "hover": {
                    "dynamicRegistration": False,
                    "contentFormat": ["markdown", "plaintext"],
                },
                "signatureHelp": {
                    "dynamicRegistration": False,
                    "signatureInformation": {
                        "documentationFormat": ["markdown", "plaintext"],
                        "parameterInformation": {
                            "labelOffsetSupport": True,
                        },
                    },
                },
                "references": {
                    "dynamicRegistration": False,
                },
                "documentHighlight": {
                    "dynamicRegistration": False,
                },
                "documentSymbol": {
                    "dynamicRegistration": False,
                    "hierarchicalDocumentSymbolSupport": True,
                    "symbolKind": {
                        "valueSet": list(range(1, 27)),
                    },
                },
                "formatting": {
                    "dynamicRegistration": False,
                },
                "rangeFormatting": {
                    "dynamicRegistration": False,
                },
                "onTypeFormatting": {
                    "dynamicRegistration": False,
                },
                "definition": {
                    "dynamicRegistration": False,
                    "linkSupport": True,
                },
                "codeAction": {
                    "dynamicRegistration": False,
                    "codeActionLiteralSupport": {
                        "codeActionKind": {
                            "valueSet": [
                                "quickfix",
                                "refactor",
                                "refactor.extract",
                                "refactor.inline",
                                "refactor.rewrite",
                                "source",
                                "source.organizeImports",
                            ],
                        },
                    },
                },
                "codeLens": {
                    "dynamicRegistration": False,
                },
                "documentLink": {
                    "dynamicRegistration": False,
                },
                "rename": {
                    "dynamicRegistration": False,
                    "prepareSupport": True,
                },
                "publishDiagnostics": {
                    "relatedInformation": True,
                    "versionSupport": True,
                    "tagSupport": {
                        "valueSet": [1, 2],
                    },
                },
            },
            "window": {
                "workDoneProgress": True,
                "showMessage": {},
                "showDocument": {
                    "support": True,
                },
            },
            "general": {
                "positionEncodings": ["utf-16"],
            },
        }

    @staticmethod
    def path_to_uri(filepath: str) -> str:
        """
        将文件路径转换为 URI。

        参数:
            filepath: 文件路径

        返回:
            file:// 格式的 URI

        修复说明（P1-7）:
            - 原实现在 Windows 路径处理时会再给已带前导 `/` 的路径
              加一次 `/`，导致 `file:////C:/...`（多了一个斜杠）。
            - 已删除多余的盘符加斜杠逻辑，`file://` + `/C:/...`
              即得到正确的 `file:///C:/...`。
        """
        if not filepath:
            return ""

        # Windows 路径处理
        if sys.platform == "win32":
            filepath = filepath.replace("\\", "/")
            if not filepath.startswith("/"):
                filepath = "/" + filepath

        # URL 编码
        from urllib.parse import quote

        # 只编码路径部分，保留 /:
        encoded = quote(filepath, safe="/:")

        return f"file://{encoded}"

    @staticmethod
    def uri_to_path(uri: str) -> str:
        """
        将 URI 转换为文件路径。

        参数:
            uri: file:// 格式的 URI

        返回:
            文件路径
        """
        if not uri:
            return ""

        try:
            parsed = urlparse(uri)
            path = unquote(parsed.path)

            # Windows 路径处理
            if sys.platform == "win32":
                if path.startswith("/") and len(path) > 2 and path[2] == ":":
                    path = path[1:]

            return path
        except Exception:
            return uri

    # ========================================================
    # 信息查询
    # ========================================================
    def get_server_info(self) -> Dict[str, Any]:
        """获取服务器信息"""
        return {
            "state": self._state.name,
            "initialized": self._init_completed,
            "capabilities": self.capabilities,
            "server_info": self.server_info,
            "pending_requests": len(self._pending),
            "open_documents": len(self._open_documents),
            "restart_count": self._restart_count,
        }

    def supports(self, capability: str) -> bool:
        """
        检查服务器是否支持指定能力。

        参数:
            capability: 能力路径，如 "completionProvider" 或
                        "textDocumentSync.change"

        返回:
            是否支持
        """
        parts = capability.split(".")
        current = self.capabilities

        for part in parts:
            if not isinstance(current, dict):
                return False
            if part not in current:
                return False
            current = current[part]

        return bool(current) if current is not None else True

    def get_completion_trigger_characters(self) -> List[str]:
        """获取补全触发字符"""
        provider = self.capabilities.get("completionProvider", {})
        return provider.get("triggerCharacters", [])

    def get_signature_trigger_characters(self) -> List[str]:
        """获取签名帮助触发字符"""
        provider = self.capabilities.get("signatureHelpProvider", {})
        return provider.get("triggerCharacters", [])

    def get_sync_kind(self) -> int:
        """获取文档同步方式（0=无, 1=全量, 2=增量）"""
        sync = self.capabilities.get("textDocumentSync")
        if isinstance(sync, int):
            return sync
        elif isinstance(sync, dict):
            return sync.get("change", 0)
        return 0

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出客户端信息"""
        info = self.get_server_info()
        lines = ["LspClient", "=" * 60]
        lines.append(f"状态: {info['state']}")
        lines.append(f"已初始化: {info['initialized']}")
        lines.append(f"待处理请求: {info['pending_requests']}")
        lines.append(f"已打开文档: {info['open_documents']}")
        lines.append(f"重启次数: {info['restart_count']}")
        lines.append("")

        if self.server_info:
            name = self.server_info.get("name", "未知")
            version = self.server_info.get("version", "?")
            lines.append(f"服务器: {name} v{version}")

        lines.append("")
        lines.append("服务器能力:")
        for key in sorted(self.capabilities.keys()):
            lines.append(f"  - {key}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<LspClient state={self._state.name} "
            f"initialized={self._init_completed} "
            f"pending={len(self._pending)}>"
        )


# ============================================================
# LSP 服务器注册表
# ============================================================

from core.lsp_registry import LspServerRegistry  # noqa: E402,F401
