# -*- coding: utf-8 -*-
"""拼写检查插件（对标 Notepad++ DSpellCheck）

设计要点：
* 纯插件实现，不侵入宿主；仅 `editor_read` 权限；
* 词典来源优先级：
  1) 可选依赖 `pyspellchecker`（若已安装，质量最好）；
  2) 内置常用词表 + 编程/技术词允许列表（零依赖兜底）；
* 只检查"像英文单词"的 token：跳过全大写（API）、含数字/下划线、
  驼峰、URL/路径、长度不足的词，显著降低误报；
* 结果发布到「问题」面板（warning，code=SPELL001），状态栏给数量。
"""
import os
import re

from app.plugins import PluginBase


# 技术/编程常见词（避免把代码标识符当拼写错误）
_ALLOW = {
    "args", "kwargs", "async", "await", "bool", "byte", "bytes", "cli",
    "config", "cpu", "csv", "def", "dict", "dir", "docstring", "enum",
    "env", "eval", "exec", "false", "fixture", "float", "func", "gui",
    "http", "https", "init", "int", "iter", "json", "lambda", "lint",
    "list", "log", "login", "logout", "main", "min", "max", "none",
    "null", "os", "param", "params", "path", "py", "pyqt", "repo",
    "return", "runtime", "self", "sql", "str", "sync", "tmp", "todo",
    "true", "tuple", "ui", "url", "uuid", "utf", "utils", "var", "www",
    "yaml", "zip",
}

# 零依赖兜底词表（常用英文 + 本项目高频词；不追求全覆盖）
_BUILTIN = {"a", "about", "above", "after", "again", "against", "all", "almost", "along", "already", "also", "although", "always", "am", "among", "an", "and", "another", "any", "anyone", "anything", "are", "around", "as", "ask", "at", "back", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "call", "can", "could", "day", "did", "do", "does", "doing", "done", "down", "during", "each", "early", "even", "ever", "every", "few", "find", "first", "for", "from", "get", "give", "go", "good", "great", "had", "has", "have", "he", "help", "her", "here", "hers", "him", "his", "how", "however", "i", "if", "in", "into", "is", "it", "its", "just", "keep", "know", "last", "later", "least", "less", "let", "like", "little", "long", "look", "made", "make", "many", "may", "me", "might", "more", "most", "much", "must", "my", "need", "never", "new", "next", "no", "not", "now", "number", "of", "off", "often", "on", "once", "one", "only", "or", "other", "our", "out", "over", "own", "part", "people", "per", "perhaps", "place", "point", "put", "quite", "rather", "really", "right", "same", "say", "see", "seem", "she", "should", "show", "side", "since", "small", "so", "some", "something", "still", "such", "sure", "take", "tell", "than", "that", "the", "their", "them", "then", "there", "these", "they", "thing", "think", "this", "those", "though", "through", "time", "to", "too", "toward", "two", "under", "until", "up", "upon", "us", "use", "used", "using", "very", "want", "was", "way", "we", "well", "went", "were", "what", "when", "where", "whether", "which", "while", "who", "whom", "why", "will", "with", "within", "without", "would", "year", "yes", "yet", "you", "your", "editor", "file", "open", "save", "close", "find", "replace", "search", "view", "tool", "window", "help", "setting", "theme", "plugin", "project", "task", "session", "macro", "print", "preview", "export", "import", "document", "line", "column", "cursor", "selection", "bookmark", "folder", "directory", "tab", "panel", "error", "warning", "info", "debug", "test", "build", "release", "version", "update", "install", "spell", "check", "word", "dictionary", "language", "english", "chinese", "text", "content"}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")

# 忽略词/自定义词典文件（每行一个词，# 开头为注释；大小写不敏感）
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
IGNORE_FILE = os.path.join(_ROOT, "data", "spell_ignore.txt")


def load_ignore_words(path=None) -> set:
    """从忽略词文件加载词表（不存在则返回空集）"""
    words = set()
    try:
        with open(path or IGNORE_FILE, encoding="utf-8") as f:
            for line in f:
                word = line.split("#", 1)[0].strip().lower()
                if word:
                    words.add(word)
    except OSError:
        pass
    return words


def _looks_like_english(token: str) -> bool:
    """过滤代码标识符/缩写/URL 等不该判错的内容"""
    if not token or len(token) < 2:
        return False
    if token.isupper():            # API / HTTP
        return False
    if "_" in token or any(c.isdigit() for c in token):
        return False
    if any(c.isupper() for c in token[1:]):   # camelCase / HTTPServer
        return False
    if token.lower() in _ALLOW:
        return False
    return True


class Plugin(PluginBase):
    NAME = "spell_check"
    VERSION = "1.0.0"
    DESCRIPTION = "英文拼写检查（可选 pyspellchecker）"
    AUTHOR = "QingCao Editor"

    def __init__(self):
        super().__init__()
        self._checker = None
        self._status_item = None
        self._ignore = set()
        self._ignore_path = IGNORE_FILE

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def on_activate(self):
        self.api.log("拼写检查插件已激活")
        self.api.register_settings_schema([
            {"key": "enabled", "label": "启用拼写检查",
             "type": "bool", "default": True},
            {"key": "min_word_length", "label": "最短检查长度",
             "type": "int", "default": 4, "min": 2, "max": 12},
            {"key": "max_diagnostics", "label": "最多报告数量",
             "type": "int", "default": 200, "min": 10, "max": 2000},
        ])
        try:
            from spellchecker import SpellChecker
            self._checker = SpellChecker()
        except Exception:
            self._checker = None

        self._ignore = load_ignore_words(self._ignore_path)
        self.api.add_menu("工具/拼写检查/检查当前文档", self.check_current)
        self.api.add_menu("工具/拼写检查/清除结果", self.clear)
        self.api.add_menu("工具/拼写检查/重新加载忽略词",
                          self.reload_ignore)
        self.api.add_menu("工具/拼写检查/编辑忽略词…",
                          self.open_ignore_file)

    def on_deactivate(self):
        self.api.log("拼写检查插件已停用")
        try:
            self.api.clear_diagnostics()
        except Exception:
            pass

    # --------------------------------------------------------
    # 核心：检查
    # --------------------------------------------------------
    def _known(self, word: str) -> bool:
        low = word.lower()
        if low in self._ignore:
            return True
        if self._checker is not None:
            try:
                return low in self._checker
            except Exception:
                pass
        return low in _BUILTIN

    def _check_text(self, text: str, min_length: int = 4,
                    limit: int = 200):
        """返回诊断列表（不依赖 API，便于单测）"""
        issues = []
        if not text:
            return issues
        for line_no, line in enumerate(text.splitlines()):
            for match in _WORD_RE.finditer(line):
                token = match.group(0)
                if len(token) < max(2, min_length):
                    continue
                if not _looks_like_english(token):
                    continue
                if self._known(token):
                    continue
                issues.append({
                    "line": line_no,
                    "col": match.start(),
                    "severity": "warning",
                    "message": "可能是拼写错误：%s" % token,
                    "code": "SPELL001",
                })
                if len(issues) >= limit:
                    return issues
        return issues

    def reload_ignore(self):
        """重新加载忽略词文件"""
        self._ignore = load_ignore_words(self._ignore_path)
        self.api.show_status(
            "已加载 %d 个忽略词" % len(self._ignore), 2500, "info")

    def open_ignore_file(self):
        """打开（不存在则创建）忽略词文件"""
        try:
            os.makedirs(os.path.dirname(self._ignore_path), exist_ok=True)
            if not os.path.exists(self._ignore_path):
                with open(self._ignore_path, "w", encoding="utf-8") as f:
                    f.write("# 拼写检查忽略词 / 自定义词典\n"
                            "# 每行一个词，# 开头为注释，大小写不敏感\n")
            from PyQt5.QtCore import QUrl
            from PyQt5.QtGui import QDesktopServices
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(self._ignore_path))
            self.api.show_status("已打开忽略词文件", 2500, "info")
        except Exception as e:
            self.api.show_status("打开忽略词文件失败: %s" % e, 3000,
                                 "warning")

    def check_current(self):
        text = self._get_current_text()
        if not text:
            self.api.show_status("没有可检查的内容", 2500, "info")
            return
        issues = self._check_text(text, limit=200)
        n = self.api.publish_diagnostics(issues)
        if n:
            self.api.show_status("发现 %d 处可疑拼写" % n, 3000, "warning")
        else:
            self.api.show_status("未发现拼写问题", 2500, "success")

    def clear(self):
        try:
            self.api.clear_diagnostics()
            self.api.show_status("已清除拼写检查结果", 2000, "info")
        except Exception:
            pass

    # --------------------------------------------------------
    # 工具
    # --------------------------------------------------------
    def _get_current_text(self) -> str:
        for name in ("get_current_text", "get_text", "current_text"):
            fn = getattr(self.api, name, None)
            if callable(fn):
                try:
                    return fn() or ""
                except Exception:
                    continue
        try:
            editor = self.api.current_editor()
            if editor is not None:
                return editor.text()
        except Exception:
            pass
        return ""
