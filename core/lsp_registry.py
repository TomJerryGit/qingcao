# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""LSP 服务器注册表（v2.24 拆出）。"""

from core.lsp_client_common import *


class LspServerRegistry:
    """
    LSP 服务器注册表。

    管理不同语言的 LSP 服务器命令。
    """

    _servers: Dict[str, Dict[str, Any]] = {
        "python": {
            "command": ["pylsp"],
            "extensions": [".py", ".pyw"],
            "install": [sys.executable, "-m", "pip", "install", "python-lsp-server"],
            "language_id": "python",
        },
        "javascript": {
            "command": ["typescript-language-server", "--stdio"],
            "extensions": [".js", ".jsx", ".ts", ".tsx"],
            "install": ["npm", "install", "-g", "typescript-language-server", "typescript"],
            "language_id": "javascript",
        },
        "rust": {
            "command": ["rust-analyzer"],
            "extensions": [".rs"],
            "install": ["rustup", "component", "add", "rust-analyzer"],
            "language_id": "rust",
        },
        "go": {
            "command": ["gopls"],
            "extensions": [".go"],
            "install": ["go", "install", "golang.org/x/tools/gopls@latest"],
            "language_id": "go",
        },
        "cpp": {
            "command": ["clangd"],
            "extensions": [".cpp", ".cc", ".cxx", ".h", ".hpp", ".c"],
            "install": [],  # 需手动安装
            "language_id": "cpp",
        },
        "java": {
            "command": ["jdtls"],
            "extensions": [".java"],
            "install": [],
            "language_id": "java",
        },
    }

    @classmethod
    def register(cls, language: str, config: Dict[str, Any]):
        """注册语言服务器"""
        cls._servers[language] = config

    @classmethod
    def get(cls, language: str) -> Optional[Dict[str, Any]]:
        """获取语言服务器配置"""
        return cls._servers.get(language)

    @classmethod
    def detect_language(cls, filepath: str) -> Optional[str]:
        """
        根据文件路径检测语言。

        参数:
            filepath: 文件路径

        返回:
            语言标识或 None
        """
        if not filepath:
            return None

        ext = os.path.splitext(filepath)[1].lower()

        for lang, config in cls._servers.items():
            if ext in config.get("extensions", []):
                return lang

        return None

    @classmethod
    def get_command(cls, language: str) -> Optional[List[str]]:
        """获取指定语言的启动命令"""
        config = cls._servers.get(language)
        if config:
            return config.get("command")
        return None

    @classmethod
    def list_languages(cls) -> List[str]:
        """列出所有支持的语言"""
        return list(cls._servers.keys())


# ============================================================
# 模块测试
# ============================================================
