# -*- coding: utf-8 -*-
"""代码片段市场客户端"""
import os
import json
import time
import threading
from typing import List, Dict, Any, Optional
from PyQt5.QtCore import QObject, pyqtSignal


# 片段市场 API（示例地址，可替换为你的服务器）
MARKET_API = "https://api.github.com/repos/qingcao-editor/snippets/contents"

CACHE_DIR = "data/snippet_cache"
CACHE_TTL = 3600  # 1 小时


class SnippetMarketClient(QObject):
    """片段市场客户端"""

    fetch_completed = pyqtSignal(list)  # 片段列表
    fetch_failed = pyqtSignal(str)
    download_completed = pyqtSignal(str)  # 片段文件路径
    download_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        os.makedirs(CACHE_DIR, exist_ok=True)

    def fetch_async(self, language="", force=False):
        """异步拉取片段列表"""
        t = threading.Thread(
            target=self._fetch, args=(language, force), daemon=True
        )
        t.start()

    def _fetch(self, language, force):
        """实际拉取"""
        cache_file = os.path.join(CACHE_DIR, "index.json")

        # 检查缓存
        if not force and os.path.exists(cache_file):
            try:
                if time.time() - os.path.getmtime(cache_file) < CACHE_TTL:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.fetch_completed.emit(data.get('snippets', []))
                    return
            except Exception:
                pass

        # 从远程拉取
        try:
            try:
                import requests
                resp = requests.get(MARKET_API, timeout=10)
                if resp.status_code != 200:
                    # 使用内置示例数据
                    self._use_builtin()
                    return
                items = resp.json()
            except ImportError:
                self._use_builtin()
                return

            # 解析
            snippets = []
            for item in items:
                if isinstance(item, dict) and item.get('type') == 'file':
                    name = item.get('name', '')
                    if name.endswith('.json'):
                        snippets.append({
                            'name': os.path.splitext(name)[0],
                            'path': item.get('path', ''),
                            'download_url': item.get('download_url', ''),
                            'sha': item.get('sha', ''),
                        })

            # 缓存
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({'snippets': snippets, 'ts': time.time()},
                          f, ensure_ascii=False)

            self.fetch_completed.emit(snippets)
        except Exception as e:
            self.fetch_failed.emit(str(e))
            self._use_builtin()

    def _use_builtin(self):
        """使用内置示例数据"""
        builtin = [
            {'name': 'Python 快速日志', 'language': 'python',
             'description': '一行日志配置',
             'body': 'import logging\nlogging.basicConfig(level=logging.INFO)\nlogger = logging.getLogger(__name__)'},
            {'name': 'Python 计时装饰器', 'language': 'python',
             'description': '装饰器测量函数耗时',
             'body': 'import time\nimport functools\n\ndef timer(func):\n    @functools.wraps(func)\n    def wrap(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        print(f"{func.__name__}: {time.time()-start:.3f}s")\n        return result\n    return wrap'},
            {'name': 'JS Fetch 封装', 'language': 'javascript',
             'description': '统一的 fetch 封装',
             'body': 'async function request(url, options = {}) {\n  const resp = await fetch(url, {\n    headers: { "Content-Type": "application/json" },\n    ...options\n  });\n  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);\n  return resp.json();\n}'},
            {'name': 'SQL 分页查询', 'language': 'sql',
             'description': '标准分页查询',
             'body': 'SELECT *\nFROM table_name\nWHERE condition\nORDER BY id DESC\nLIMIT 20 OFFSET 0;'},
        ]
        self.fetch_completed.emit(builtin)

    def download_async(self, snippet):
        """下载片段"""
        t = threading.Thread(
            target=self._download, args=(snippet,), daemon=True
        )
        t.start()

    def _download(self, snippet):
        """实际下载"""
        try:
            from core.snippets import get_snippet_manager, Snippet

            mgr = get_snippet_manager()

            s = Snippet(
                name=snippet.get('name', ''),
                prefix=snippet.get('name', '').split()[0].lower(),
                body=snippet.get('body', ''),
                description=snippet.get('description', ''),
                scope=snippet.get('language', ''),
            )
            mgr.add(s)

            self.download_completed.emit(s.prefix)
        except Exception as e:
            self.download_failed.emit(str(e))