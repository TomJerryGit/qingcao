# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""文件/配置/网络/进程职责（v2.24 从 plugin_api.py 拆出）。"""

from app.plugin_api_common import *  # noqa: F401,F403,F405


class DataMixin:
    def read_file(self, filepath: str, encoding: str = "utf-8") -> Optional[str]:
        """
        读取文件内容。

        参数:
            filepath: 文件路径
            encoding: 编码

        返回:
            文件内容或 None（失败时）
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        try:
            with open(filepath, encoding=encoding, errors="replace") as f:
                return f.read()
        except Exception as e:
            self.show_status(f"读取文件失败: {e}", 3000, "error")
            return None

    def read_file_bytes(self, filepath: str) -> Optional[bytes]:
        """读取文件二进制内容"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        try:
            with open(filepath, "rb") as f:
                return f.read()
        except Exception as e:
            self.show_status(f"读取文件失败: {e}", 3000, "error")
            return None

    def write_file(self, filepath: str, content: str, encoding: str = "utf-8") -> bool:
        """
        写入文件。

        参数:
            filepath: 文件路径
            content: 内容
            encoding: 编码

        返回:
            是否成功
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "w", encoding=encoding) as f:
                f.write(content)
            return True
        except Exception as e:
            self.show_status(f"写入文件失败: {e}", 3000, "error")
            return False

    def write_file_bytes(self, filepath: str, content: bytes) -> bool:
        """写入文件二进制内容"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(content)
            return True
        except Exception as e:
            self.show_status(f"写入文件失败: {e}", 3000, "error")
            return False

    def file_exists(self, filepath: str) -> bool:
        """检查文件是否存在"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        return os.path.exists(filepath)

    def is_directory(self, path: str) -> bool:
        """检查是否为目录"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        return os.path.isdir(path)

    def list_directory(self, path: str) -> List[str]:
        """列出目录内容"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return []
        try:
            return os.listdir(path)
        except Exception:
            return []

    def get_plugin_data_dir(self) -> str:
        """
        获取插件私有数据目录。

        P0-3 修复：原实现"无需额外权限"即可写盘，成为绕过
        filesystem 权限的写文件后门（app/plugins.py 旧版
        1021-1032 行）。现在要求 filesystem 权限。
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return ""
        try:
            os.makedirs(self._data_dir, exist_ok=True)
        except Exception:
            pass
        return self._data_dir

    # ========================================================
    # 配置读写
    # ========================================================

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        读取插件配置。

        配置存储于 QSettings 中，以插件名为前缀。
        """
        try:
            settings = QSettings("QingCao", f"Plugin_{self.plugin_name}")
            return settings.value(key, default)
        except Exception:
            return default

    def set_config(self, key: str, value: Any):
        """写入插件配置"""
        try:
            settings = QSettings("QingCao", f"Plugin_{self.plugin_name}")
            settings.setValue(key, value)
        except Exception as e:
            self.show_status(f"保存配置失败: {e}", 3000, "error")

    def save_plugin_config(self, data: Dict[str, Any]) -> bool:
        """保存插件配置（JSON 格式到数据目录）

        P0-3: 需要 filesystem 权限（同 get_plugin_data_dir）。
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        try:
            config_path = os.path.join(self.get_plugin_data_dir(), "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.show_status(f"保存插件配置失败: {e}", 3000, "error")
            return False

    def load_plugin_config(self) -> Dict[str, Any]:
        """加载插件配置"""
        try:
            config_path = os.path.join(self.get_plugin_data_dir(), "config.json")
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    # ========================================================
    # 网络请求
    # ========================================================

    def http_get(
        self, url: str, timeout: int = 10, headers: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        HTTP GET 请求。

        参数:
            url: 请求 URL
            timeout: 超时秒数
            headers: 自定义请求头

        返回:
            响应文本或 None
        """
        if not self.require_permission(PERMISSION_NETWORK):
            return None
        try:
            import requests

            resp = requests.get(url, timeout=timeout, headers=headers)
            return resp.text
        except Exception as e:
            self.show_status(f"网络请求失败: {e}", 3000, "error")
            return None

    def http_post(
        self,
        url: str,
        data: Any = None,
        json_data: Any = None,
        timeout: int = 10,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """HTTP POST 请求"""
        if not self.require_permission(PERMISSION_NETWORK):
            return None
        try:
            import requests

            resp = requests.post(url, data=data, json=json_data, timeout=timeout, headers=headers)
            return resp.text
        except Exception as e:
            self.show_status(f"网络请求失败: {e}", 3000, "error")
            return None

    def download_file(self, url: str, filepath: str, timeout: int = 30) -> bool:
        """下载文件"""
        if not self.require_permission(PERMISSION_NETWORK):
            return False
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        try:
            import requests

            resp = requests.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            self.show_status(f"下载失败: {e}", 3000, "error")
            return False

    # ========================================================
    # 剪贴板
    # ========================================================

    def get_clipboard(self) -> str:
        """获取剪贴板文本"""
        if not self.require_permission(PERMISSION_CLIPBOARD):
            return ""
        try:
            return QApplication.clipboard().text()
        except Exception:
            return ""

    def set_clipboard(self, text: str):
        """设置剪贴板文本"""
        if not self.require_permission(PERMISSION_CLIPBOARD):
            return
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    # ========================================================
    # 进程与终端
    # ========================================================

    def run_command(
        self, command: str, cwd: Optional[str] = None, timeout: int = 30
    ) -> Optional[str]:
        """
        执行系统命令并返回输出。

        参数:
            command: 命令
            cwd: 工作目录
            timeout: 超时秒数

        返回:
            标准输出或 None
        """
        if not self.require_permission(PERMISSION_PROCESS):
            return None
        try:
            import subprocess

            result = subprocess.run(
                command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout + result.stderr
        except Exception as e:
            self.show_status(f"命令执行失败: {e}", 3000, "error")
            return None

    def run_python(self, code: str) -> Optional[str]:
        """
        在当前进程执行 Python 代码（危险，需谨慎）。

        返回:
            输出字符串或 None
        """
        if not self.require_permission(PERMISSION_PROCESS):
            return None
        try:
            import io
            from contextlib import redirect_stderr, redirect_stdout

            stdout_cap = io.StringIO()
            stderr_cap = io.StringIO()
            with redirect_stdout(stdout_cap), redirect_stderr(stderr_cap):
                exec(code, {})
            return stdout_cap.getvalue() + stderr_cap.getvalue()
        except Exception as e:
            return f"错误: {e}"

    # ========================================================
    # 命令注册
    # ========================================================
