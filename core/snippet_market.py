# -*- coding: utf-8 -*-
"""代码片段库（**本地**）

## 为什么从"网络市场"改成"本地库"

本模块原实现是一个网络市场客户端，`MARKET_API` 指向：

    https://api.github.com/repos/qingcao-editor/snippets/contents

**实测该地址返回 HTTP 404 —— 仓库不存在**。于是：

* 用户点"刷新"永远拿不到内容（代码里有一层 `_use_builtin()` 兜底，
  显示 4 条硬编码示例，看起来"有个市场"，但其实永远是那 4 条）；
* 要真的可用，需要长期运营一个片段仓库（内容、审核、CDN、安全）。

而"导入本地片段包"能提供同样的核心价值（复用别人写好的片段），
且**零运维、零信任风险**（不会执行第三方下载内容）。

因此本模块改为：扫描本地目录里的 `.json` 片段包。

## 片段包格式（简单、可手写、可版本控制）

单个文件可以是：

```json
{"snippets": [
  {"name": "Python 计时装饰器", "language": "python",
   "description": "装饰器测量函数耗时",
   "body": "import time\\n..."},
  {"name": "日志", "language": "python", "body": "..."}
]}
```

或直接是一个数组：

```json
[{"name": "...", "body": "..."}]
```

## 安装（`download_async`）

保持原方法名不变（UI 已依赖），语义改为"登记进本地片段管理器"
（`core/snippets.SnippetManager`）—— 纯本地写入，不发网络请求。
"""
import json
import os
import threading
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


def _app_root() -> str:
    """应用根目录（相对路径会随 cwd 漂移）"""
    try:
        from infrastructure.plugin_loader import app_root_dir
        return app_root_dir()
    except Exception:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 默认片段包目录：<应用根>/data/snippet_packs
DEFAULT_PACK_DIR = os.path.join(_app_root(), "data", "snippet_packs")


class SnippetLibrary(QObject):
    """本地代码片段库

    对外接口与旧的 `SnippetMarketClient` 保持一致（`fetch_async` /
    `download_async` + 4 个信号），这样 UI 层几乎不用改。
    """

    fetch_completed = pyqtSignal(list)     # 片段列表
    fetch_failed = pyqtSignal(str)
    download_completed = pyqtSignal(str)   # 安装后的片段 prefix
    download_failed = pyqtSignal(str)

    def __init__(self, parent=None, source_dir: Optional[str] = None):
        super().__init__(parent)
        self._source_dir = source_dir or DEFAULT_PACK_DIR
        self._ensure_dir()

    # ---------- 目录 ----------
    @property
    def source_dir(self) -> str:
        """当前片段包目录"""
        return self._source_dir

    def set_source_dir(self, path: str) -> bool:
        """切换片段包目录（用户在对话框里选）"""
        try:
            path = os.path.abspath(os.path.expanduser(path or ""))
            if not path or not os.path.isdir(path):
                return False
            self._source_dir = path
            # 记住选择，下次打开直接用它
            try:
                from PyQt5.QtCore import QSettings
                QSettings("QingCao", "Editor").setValue(
                    "snippet_pack_dir", path
                )
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _ensure_dir(self):
        try:
            os.makedirs(self._source_dir, exist_ok=True)
        except Exception:
            pass

    @staticmethod
    def saved_source_dir() -> str:
        """读取用户上次选择的片段包目录（没有则用默认）"""
        try:
            from PyQt5.QtCore import QSettings
            val = QSettings("QingCao", "Editor").value(
                "snippet_pack_dir", "", type=str
            )
            if val and os.path.isdir(val):
                return val
        except Exception:
            pass
        return DEFAULT_PACK_DIR

    # ---------- 读取 ----------
    def fetch_async(self, language: str = "", force: bool = False):
        """异步读取本地片段包（保持原异步接口）"""
        t = threading.Thread(
            target=self._fetch, args=(language, force), daemon=True
        )
        t.start()

    def _fetch(self, language: str, force: bool):
        try:
            snippets = self.scan()
            self.fetch_completed.emit(snippets)
        except Exception as e:
            self.fetch_failed.emit(str(e))

    def scan(self) -> List[Dict[str, Any]]:
        """扫描片段包目录，返回片段 dict 列表

        坏文件不影响其它文件（逐个 try/except），并在控制台提示。
        """
        result: List[Dict[str, Any]] = []
        self._ensure_dir()
        try:
            names = sorted(os.listdir(self._source_dir))
        except Exception as e:
            print(f"[片段库] 读取目录失败: {e}")
            return result

        for name in names:
            if not name.lower().endswith(".json"):
                continue
            path = os.path.join(self._source_dir, name)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[片段库] 跳过无法解析的 {name}: {e}")
                continue

            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("snippets") or []
                # 允许"单片段文件"
                if not items and data.get("body"):
                    items = [data]
            else:
                continue

            for item in items:
                if not isinstance(item, dict) or not item.get("body"):
                    continue
                entry = dict(item)
                entry.setdefault("name", name)
                entry.setdefault("language", "")
                entry.setdefault("description", "")
                entry["source_file"] = path
                result.append(entry)

        return result

    # ---------- 安装到本地片段管理器 ----------
    def download_async(self, snippet):
        """把片段登记进本地片段库（方法名保持向后兼容，无网络请求）"""
        t = threading.Thread(
            target=self._install, args=(snippet,), daemon=True
        )
        t.start()

    def _install(self, snippet):
        try:
            from core.snippets import Snippet, get_snippet_manager

            name = (snippet.get("name") or "").strip()
            if not name:
                self.download_failed.emit("片段缺少名称")
                return

            # prefix 用片段名（去空格小写）；若被占用则加序号，
            # 避免"导入第二条同名片段时静默覆盖第一条"。
            base = "".join(ch for ch in name.lower() if ch.isalnum() or
                           ch in "-_")
            base = base or "snippet"
            mgr = get_snippet_manager()
            prefix = base
            idx = 2
            while prefix in mgr.snippets and \
                    mgr.snippets[prefix].body != snippet.get("body", ""):
                prefix = "%s_%d" % (base, idx)
                idx += 1

            s = Snippet(
                name=name,
                prefix=prefix,
                body=snippet.get("body", ""),
                description=snippet.get("description", ""),
                scope=snippet.get("language", ""),
            )
            mgr.add(s)
            self.download_completed.emit(s.prefix)
        except Exception as e:
            self.download_failed.emit(str(e))

    # ---------- 内置示例 ----------
    @staticmethod
    def builtin_snippets() -> List[Dict[str, Any]]:
        """内置示例片段（片段包目录为空时展示，让用户知道格式）"""
        return [
            {"name": "Python 快速日志", "language": "python",
             "description": "一行日志配置（内置示例）",
             "body": "import logging\nlogging.basicConfig(level=logging.INFO)\n"
                     "logger = logging.getLogger(__name__)"},
            {"name": "Python 计时装饰器", "language": "python",
             "description": "装饰器测量函数耗时（内置示例）",
             "body": "import time\nimport functools\n\n\ndef timer(func):\n"
                     "    @functools.wraps(func)\n    def wrap(*args, **kwargs):\n"
                     "        start = time.time()\n"
                     "        result = func(*args, **kwargs)\n"
                     "        print(f\"{func.__name__}: {time.time()-start:.3f}s\")\n"
                     "        return result\n    return wrap"},
            {"name": "JS Fetch 封装", "language": "javascript",
             "description": "统一的 fetch 封装（内置示例）",
             "body": "async function request(url, options = {}) {\n"
                     "  const resp = await fetch(url, {\n"
                     "    headers: { \"Content-Type\": \"application/json\" },\n"
                     "    ...options\n  });\n"
                     "  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);\n"
                     "  return resp.json();\n}"},
        ]


# 向后兼容别名：旧的 import 路径/类名仍可用
SnippetMarketClient = SnippetLibrary
# 旧常量（已不用于网络请求，保留避免外部 import 报错）
CACHE_DIR = os.path.join(_app_root(), "data", "snippet_cache")
