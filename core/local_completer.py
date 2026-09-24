# -*- coding: utf-8 -*-
"""本地智能补全（不依赖 AI）"""
import re
import time
from typing import List, Dict, Set, Optional, Tuple
from collections import Counter, defaultdict


class LocalCompleter:
    """本地补全器"""

    def __init__(self):
        self.word_freq: Counter = Counter()  # 全局词频
        self.file_words: Dict[str, Counter] = defaultdict(Counter)
        self.recent_words: List[str] = []  # 最近使用
        self._max_recent = 100
        self._min_word_len = 2

        # 语言关键字
        self.language_keywords = {
            'python': {
                'def', 'class', 'return', 'if', 'else', 'elif',
                'for', 'while', 'in', 'not', 'and', 'or',
                'import', 'from', 'as', 'try', 'except', 'finally',
                'with', 'lambda', 'yield', 'async', 'await',
                'True', 'False', 'None', 'self', 'super',
                'print', 'len', 'range', 'enumerate', 'zip',
                'map', 'filter', 'sorted', 'reversed', 'list',
                'dict', 'set', 'tuple', 'str', 'int', 'float',
                'bool', 'type', 'isinstance', 'hasattr', 'getattr',
                'setattr', 'open', 'input', 'int', 'str',
            },
            'javascript': {
                'function', 'return', 'if', 'else', 'for', 'while',
                'const', 'let', 'var', 'class', 'extends',
                'import', 'export', 'from', 'async', 'await',
                'try', 'catch', 'finally', 'throw', 'new',
                'this', 'null', 'undefined', 'true', 'false',
                'console', 'document', 'window', 'Array',
                'Object', 'String', 'Number', 'Promise',
                'JSON', 'Math', 'Date',
            },
        }

    def update_from_file(self, filepath: str, text: str):
        """从文件更新词频"""
        if not filepath:
            return

        # 提取所有单词
        words = self._extract_words(text)

        # 更新文件的词频
        self.file_words[filepath] = Counter(words)

        # 更新全局词频（衰减）
        for w in words:
            self.word_freq[w] += 1

        # 限制大小
        if len(self.word_freq) > 10000:
            # 只保留最多的 5000 个
            common = self.word_freq.most_common(5000)
            self.word_freq = Counter(dict(common))

    def _extract_words(self, text: str) -> List[str]:
        """提取单词"""
        # 匹配标识符
        pattern = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]{1,40}\b')
        return pattern.findall(text)

    def get_completions(self, prefix: str, filepath: str = "",
                        language: str = "python",
                        limit: int = 20) -> List[Tuple[str, str]]:
        """
        获取补全建议。

        返回:
            [(word, source), ...]
            source: "keyword" / "file" / "global" / "recent"
        """
        if not prefix or len(prefix) < self._min_word_len:
            return []

        prefix_lower = prefix.lower()
        results = []

        # 1. 最近使用（最高优先）
        for w in self.recent_words:
            if w.lower().startswith(prefix_lower):
                results.append((w, "recent"))

        # 2. 语言关键字
        keywords = self.language_keywords.get(language, set())
        for kw in keywords:
            if kw.lower().startswith(prefix_lower):
                results.append((kw, "keyword"))

        # 3. 当前文件词频
        if filepath and filepath in self.file_words:
            for word, count in self.file_words[filepath].most_common(50):
                if word.lower().startswith(prefix_lower):
                    if word not in [r[0] for r in results]:
                        results.append((word, "file"))

        # 4. 全局词频
        for word, count in self.word_freq.most_common(100):
            if word.lower().startswith(prefix_lower):
                if word not in [r[0] for r in results]:
                    results.append((word, "global"))

        # 去重并限制数量
        seen = set()
        unique = []
        for word, source in results:
            if word in seen:
                continue
            seen.add(word)
            unique.append((word, source))
            if len(unique) >= limit:
                break

        return unique

    def record_used(self, word: str):
        """记录使用了某个词"""
        if not word or len(word) < self._min_word_len:
            return

        # 更新最近使用
        if word in self.recent_words:
            self.recent_words.remove(word)
        self.recent_words.insert(0, word)
        if len(self.recent_words) > self._max_recent:
            self.recent_words.pop()

        # 更新词频
        self.word_freq[word] += 1

    def get_word_at_position(self, text: str, pos: int) -> str:
        """获取光标位置的单词"""
        if pos <= 0 or pos > len(text):
            return ""

        # 向左找单词开始
        start = pos
        while start > 0 and (text[start - 1].isalnum() or
                             text[start - 1] == '_'):
            start -= 1

        # 向右找单词结束
        end = pos
        while end < len(text) and (text[end].isalnum() or
                                     text[end] == '_'):
            end += 1

        return text[start:end]


# 全局单例
_instance = None


def get_local_completer():
    global _instance
    if _instance is None:
        _instance = LocalCompleter()
    return _instance