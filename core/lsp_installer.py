# -*- coding: utf-8 -*-
"""
青草编辑器 - LSP 服务器自动安装器
============================
职责:
- 检测 LSP 服务器是否已安装
- 自动安装（pip/npm/apt）
- 安装进度反馈
- 安装失败回滚

作者: hedongwei
"""
import os
import shutil
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal


# LSP 服务器配置
LSP_SERVERS = {
    'python': {
        'name': 'Python LSP Server',
        'command': 'pylsp',
        'check_command': ['pylsp', '--version'],
        'install': {
            'pip': [sys.executable, '-m', 'pip', 'install',
                     'python-lsp-server[all]'],
        },
        'extensions': ['.py', '.pyw'],
        'language_id': 'python',
    },
    'javascript': {
        'name': 'TypeScript Language Server',
        'command': 'typescript-language-server',
        'check_command': ['typescript-language-server', '--version'],
        'install': {
            'npm': ['npm', 'install', '-g',
                     'typescript-language-server', 'typescript'],
        },
        'extensions': ['.js', '.jsx', '.ts', '.tsx'],
        'language_id': 'typescript',
    },
    'rust': {
        'name': 'Rust Analyzer',
        'command': 'rust-analyzer',
        'check_command': ['rust-analyzer', '--version'],
        'install': {
            'rustup': ['rustup', 'component', 'add',
                        'rust-analyzer'],
        },
        'extensions': ['.rs'],
        'language_id': 'rust',
    },
    'go': {
        'name': 'gopls',
        'command': 'gopls',
        'check_command': ['gopls', 'version'],
        'install': {
            'go': ['go', 'install',
                    'golang.org/x/tools/gopls@latest'],
        },
        'extensions': ['.go'],
        'language_id': 'go',
    },
    'cpp': {
        'name': 'clangd',
        'command': 'clangd',
        'check_command': ['clangd', '--version'],
        'install': {},  # 需要手动安装
        'extensions': ['.c', '.cpp', '.cc', '.cxx', '.h', '.hpp'],
        'language_id': 'cpp',
    },
    'java': {
        'name': 'Eclipse JDT Language Server',
        'command': 'jdtls',
        'check_command': ['jdtls', '--version'],
        'install': {},
        'extensions': ['.java'],
        'language_id': 'java',
    },
}


class LspInstallResult:
    """安装结果"""

    def __init__(self, success: bool, message: str = "",
                 log: str = ""):
        self.success = success
        self.message = message
        self.log = log

    def __repr__(self):
        return f"<LspInstallResult success={self.success}>"


class LspInstaller(QObject):
    """
    LSP 安装器。

    信号:
        install_started(str): 开始安装（语言名）
        install_progress(str, str): 进度（语言名, 消息）
        install_finished(str, bool, str): 完成
    """

    install_started = pyqtSignal(str)
    install_progress = pyqtSignal(str, str)
    install_finished = pyqtSignal(str, bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    # ========================================================
    # 检测
    # ========================================================
    def is_installed(self, language: str) -> bool:
        """检测语言服务器是否已安装"""
        config = LSP_SERVERS.get(language)
        if not config:
            return False

        command = config.get('command', '')
        if not command:
            return False

        return shutil.which(command) is not None

    def detect_all(self) -> Dict[str, bool]:
        """检测所有语言服务器"""
        result = {}
        for lang in LSP_SERVERS.keys():
            result[lang] = self.is_installed(lang)
        return result

    def get_version(self, language: str) -> Optional[str]:
        """获取服务器版本"""
        config = LSP_SERVERS.get(language)
        if not config:
            return None

        check_cmd = config.get('check_command')
        if not check_cmd:
            return None

        try:
            result = subprocess.run(
                check_cmd,
                capture_output=True,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='replace',
            )
            if result.returncode == 0:
                # 取第一行
                output = (result.stdout or result.stderr).strip()
                return output.split('\n')[0][:100]
        except Exception:
            pass
        return None

    def get_install_method(self, language: str) -> Optional[str]:
        """获取推荐的安装方式"""
        config = LSP_SERVERS.get(language)
        if not config:
            return None

        install = config.get('install', {})
        if not install:
            return None

        # 检测系统可用的安装器
        methods = list(install.keys())
        for method in ['pip', 'npm', 'rustup', 'go']:
            if method in methods and shutil.which(method):
                return method

        return methods[0] if methods else None

    def get_install_command(self, language: str
                              ) -> Optional[List[str]]:
        """获取安装命令"""
        config = LSP_SERVERS.get(language)
        if not config:
            return None

        method = self.get_install_method(language)
        if not method:
            return None

        return config.get('install', {}).get(method)

    def get_manual_install_hint(self, language: str) -> str:
        """获取手动安装提示"""
        config = LSP_SERVERS.get(language)
        if not config:
            return ""

        name = config.get('name', language)
        install = config.get('install', {})

        if not install:
            return f"{name} 需要手动安装。\n请参考官方文档。"

        lines = [f"安装 {name}:", ""]
        if 'pip' in install:
            lines.append("  pip install python-lsp-server[all]")
        if 'npm' in install:
            lines.append("  npm install -g typescript-language-server typescript")
        if 'rustup' in install:
            lines.append("  rustup component add rust-analyzer")
        if 'go' in install:
            lines.append("  go install golang.org/x/tools/gopls@latest")

        return '\n'.join(lines)

    # ========================================================
    # 安装
    # ========================================================
    def install_async(self, language: str):
        """异步安装"""
        t = threading.Thread(
            target=self._install_worker,
            args=(language,),
            daemon=True,
        )
        t.start()

    def _install_worker(self, language: str):
        """安装工作线程"""
        self.install_started.emit(language)

        try:
            # 检查已安装
            if self.is_installed(language):
                self.install_finished.emit(
                    language, True, "已安装"
                )
                return

            command = self.get_install_command(language)
            if not command:
                hint = self.get_manual_install_hint(language)
                self.install_finished.emit(
                    language, False,
                    "无法自动安装。\n\n" + hint
                )
                return

            self.install_progress.emit(
                language, "执行: " + ' '.join(command)
            )

            # 执行安装
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,  # 5 分钟超时
                encoding='utf-8',
                errors='replace',
            )

            log = (result.stdout or '') + '\n' + (result.stderr or '')

            if result.returncode == 0:
                # 验证
                if self.is_installed(language):
                    self.install_finished.emit(
                        language, True, "安装成功"
                    )
                else:
                    self.install_finished.emit(
                        language, False,
                        "安装命令执行成功，但未检测到可执行文件。\n"
                        "请重启终端或编辑器。"
                    )
            else:
                self.install_finished.emit(
                    language, False,
                    f"安装失败（退出码 {result.returncode}）\n\n"
                    + log[:500]
                )

        except subprocess.TimeoutExpired:
            self.install_finished.emit(
                language, False, "安装超时（>5 分钟）"
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.install_finished.emit(
                language, False, f"安装异常: {e}"
            )

    # ========================================================
    # 信息
    # ========================================================
    def list_languages(self) -> List[str]:
        """列出支持的语言"""
        return list(LSP_SERVERS.keys())

    def get_server_info(self, language: str) -> Dict[str, Any]:
        """获取服务器信息"""
        config = LSP_SERVERS.get(language, {})
        return {
            'language': language,
            'name': config.get('name', language),
            'command': config.get('command', ''),
            'extensions': config.get('extensions', []),
            'language_id': config.get('language_id', language),
            'installed': self.is_installed(language),
            'version': self.get_version(language),
            'install_method': self.get_install_method(language),
        }

    def dump(self) -> str:
        """导出状态"""
        lines = ["LSP 安装器", "=" * 60]
        for lang in self.list_languages():
            info = self.get_server_info(lang)
            status = "✓" if info['installed'] else "✗"
            version = info['version'] or "(未安装)"
            lines.append(
                f"  {status} {lang:15s} {info['name']:30s} {version}"
            )
        return "\n".join(lines)


# 全局单例
_instance = None


def get_lsp_installer() -> LspInstaller:
    global _instance
    if _instance is None:
        _instance = LspInstaller()
    return _instance