# -*- coding: utf-8 -*-
"""插件子进程沙箱 RPC（B-1/B-2：协议 + 宿主）

协议：JSON Lines over stdin/stdout
  请求: {"id": 1, "method": "symbols", "params": {...}}
  响应: {"id": 1, "ok": true, "result": ...}
        {"id": 1, "ok": false, "error": "..."}

设计取舍：
* 仅允许只读扩展点（symbols/hover/completion/describe），最小攻击面；
* 主进程完全不导入插件代码 → 插件语法错误/异常/死循环不会拖垮编辑器；
* 每次调用带超时；崩溃后 `restart()` 可隔离重启；
* 插件 print 输出会被忽略（非 JSON 行跳过），stdout 保留给协议。
"""
import json
import os
import subprocess
import sys
import threading
import time


WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "plugin_sandbox_worker.py")

ALLOWED_METHODS = frozenset({
    "symbols", "hover", "completion", "describe",
    "diagnostics",   # 受限：插件只返回数据，由宿主发布到问题面板
    "add_ignore_word",  # 受限：只允许追加忽略词
})


class SandboxError(RuntimeError):
    """沙箱调用失败（插件异常/协议错误/进程不可用）"""


class SandboxTimeout(SandboxError):
    """沙箱调用超时"""


class SandboxProcess:
    """一个插件沙箱子进程（一次只处理一个同步调用）"""

    def __init__(self, plugin_dir: str, python: str = "",
                 timeout: float = 5.0):
        self.plugin_dir = os.path.abspath(plugin_dir)
        self.timeout = float(timeout)
        self.python = python or sys.executable
        self._proc = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._stderr_tail = ""
        self.start()

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def start(self):
        if not os.path.isdir(self.plugin_dir):
            raise SandboxError("插件目录不存在: %s" % self.plugin_dir)
        self._proc = subprocess.Popen(
            [self.python, "-u", WORKER, self.plugin_dir],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=self.plugin_dir,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        # 就绪握手：worker 加载插件成功会先发 {"ready": true}；
        # 加载失败会发 ready=false 并退出（避免"进程还活着但不可用"竞态）。
        try:
            line = self._readline(min(5.0, self.timeout + 3.0))
            hello = json.loads(line)
        except Exception as e:
            tail = self.stderr_tail(500)
            self.close()
            raise SandboxError("沙箱启动失败: %s%s"
                               % (e, (" | " + tail) if tail else ""))
        if not isinstance(hello, dict) or not hello.get("ready"):
            reason = hello.get("error") if isinstance(hello, dict) else hello
            self.close()
            raise SandboxError("沙箱加载插件失败: %s" % (reason or "未知"))

    def _drain_stderr(self):
        try:
            for line in self._proc.stderr:
                self._stderr_tail = (self._stderr_tail + line)[-4000:]
        except Exception:
            pass

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def restart(self):
        self.close()
        self.start()
        return self

    def close(self, timeout: float = 2.0):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass

    # --------------------------------------------------------
    # 调用
    # --------------------------------------------------------
    def call(self, method: str, params: dict = None, timeout: float = None):
        if method not in ALLOWED_METHODS:
            raise SandboxError("方法不允许在沙箱中调用: %r" % method)
        if not self.is_alive():
            raise SandboxError("沙箱进程未运行")
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            payload = json.dumps(
                {"id": req_id, "method": method,
                 "params": params or {}}, ensure_ascii=False)
            try:
                self._proc.stdin.write(payload + "\n")
                self._proc.stdin.flush()
            except Exception as e:
                raise SandboxError("写入请求失败: %s" % e)
            limit = self.timeout if timeout is None else float(timeout)
            deadline = time.monotonic() + limit
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SandboxTimeout(
                        "调用 %s 超时（%.1fs）" % (method, limit))
                line = self._readline(remaining)
                try:
                    resp = json.loads(line)
                except Exception:
                    continue    # 忽略插件的 print 输出
                if not isinstance(resp, dict):
                    continue
                if resp.get("id") != req_id:
                    continue
                if resp.get("ok"):
                    return resp.get("result")
                raise SandboxError(str(resp.get("error") or "未知错误"))

    def _readline(self, timeout: float) -> str:
        result = {}

        def _read():
            try:
                result["line"] = self._proc.stdout.readline()
            except Exception as e:
                result["error"] = e

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive() or "line" not in result:
            raise SandboxTimeout("读取响应超时")
        return result["line"]

    def describe(self):
        return self.call("describe")

    def stderr_tail(self, limit: int = 1500) -> str:
        return self._stderr_tail[-limit:]

    def __repr__(self):
        return "<SandboxProcess %s alive=%s>" % (
            os.path.basename(self.plugin_dir), self.is_alive())