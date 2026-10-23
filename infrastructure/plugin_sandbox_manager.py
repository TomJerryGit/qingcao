# -*- coding: utf-8 -*-
"""插件子进程沙箱管理（B-3：opt-in 只读隔离）

设计原则（保证现有插件零影响）：
* **默认关闭**：只有 manifest 显式声明 `"sandbox": true` 的插件才隔离；
* 只读边界：沙箱仅代理 symbols/hover/completion 三个只读扩展点；
* 惰性启动：第一次调用才启动子进程；失败/超时自动降级为空结果并标记
  `degraded`，绝不让宿主阻塞或抛异常；
* 加载器仍可导入插件做兼容性检查，但宿主收集扩展点时应只走本包装器。

后续（B-3b）：PluginManager 在 load_all 时识别 sandbox 插件并跳过正常
激活；capability 收集器（collect_plugin_symbols 等）转发到本模块。
"""
import json
import os

from infrastructure.plugin_sandbox_rpc import (
    ALLOWED_METHODS,
    SandboxError,
    SandboxProcess,
    SandboxTimeout,
)


# 沙箱支持代理的只读扩展点 → 插件方法名
READONLY_METHODS = {
    "symbols": "symbols",
    "hover": "hover",
    "completion": "completion",
}


def is_sandbox_enabled(plugin_dir: str) -> bool:
    """manifest 是否显式声明 sandbox: true（默认 False）"""
    manifest = os.path.join(plugin_dir, "plugin.json")
    try:
        with open(manifest, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("sandbox") is True)
    except (OSError, ValueError):
        return False


def discover_sandboxed_plugins(plugins_dir: str):
    """扫描插件根目录，返回 [(name, path)] —— 仅 sandbox: true 的插件"""
    found = []
    if not os.path.isdir(plugins_dir):
        return found
    for name in sorted(os.listdir(plugins_dir)):
        path = os.path.join(plugins_dir, name)
        if os.path.isdir(path) and is_sandbox_enabled(path):
            found.append((name, path))
    return found


class SandboxedPlugin:
    """一个被隔离插件的只读代理（宿主只通过它与插件交互）"""

    def __init__(self, plugin_dir: str, timeout: float = 5.0):
        self.plugin_dir = os.path.abspath(plugin_dir)
        self.name = os.path.basename(self.plugin_dir.rstrip("\\/"))
        self._timeout = float(timeout)
        self._proc = None
        self.degraded = False
        self.last_error = ""

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def _ensure_process(self):
        if self._proc is not None and self._proc.is_alive():
            return self._proc
        self._proc = SandboxProcess(self.plugin_dir,
                                    timeout=self._timeout)
        return self._proc

    def available(self) -> bool:
        try:
            return self._ensure_process().is_alive()
        except Exception as e:
            self.degraded = True
            self.last_error = str(e)
            return False

    def close(self):
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.close()
            except Exception:
                pass

    def restart(self):
        self.close()
        self.degraded = False
        return self.available()

    # --------------------------------------------------------
    # 只读扩展点代理（失败 → 空结果 + degraded）
    # --------------------------------------------------------
    def symbols(self, text, filepath="", language=""):
        return self._safe_call(
            "symbols", {"text": text or "", "filepath": filepath or "",
                        "language": language or ""}, []) or []

    def hover(self, line, col, filepath="", language=""):
        return self._safe_call(
            "hover", {"line": int(line), "col": int(col),
                      "filepath": filepath or "",
                      "language": language or ""}, "")

    def completion(self, prefix, language="", filepath=""):
        return self._safe_call(
            "completion", {"prefix": prefix or "",
                           "language": language or "",
                           "filepath": filepath or ""}, []) or []

    def describe(self):
        return self._safe_call("describe", {}, {})

    # --------------------------------------------------------
    # 内部
    # --------------------------------------------------------
    def _safe_call(self, method, params, default):
        if method not in ALLOWED_METHODS:
            return default
        if self.degraded and self._proc is None:
            return default
        try:
            proc = self._ensure_process()
            return proc.call(method, params, timeout=self._timeout)
        except SandboxTimeout as e:
            # 超时：重启进程（可能卡死），本次返回默认值
            self.last_error = str(e)
            self.degraded = True
            self.close()
            return default
        except SandboxError as e:
            self.last_error = str(e)
            self.degraded = True
            self.close()
            return default
        except Exception as e:
            self.last_error = str(e)
            self.degraded = True
            self.close()
            return default

    def __repr__(self):
        return "<SandboxedPlugin %s degraded=%s>" % (
            self.name, self.degraded)