# -*- coding: utf-8 -*-
"""代码片段管理器"""
import json
import os
from typing import Any, Dict, List, Optional


class Snippet:
    """代码片段"""

    def __init__(self, name, prefix, body, description="",
                 scope=""):
        self.name = name
        self.prefix = prefix
        self.body = body  # 字符串或列表
        self.description = description
        self.scope = scope  # 适用语言

    def to_dict(self):
        return {
            'name': self.name,
            'prefix': self.prefix,
            'body': self.body,
            'description': self.description,
            'scope': self.scope,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            d.get('name', ''),
            d.get('prefix', ''),
            d.get('body', ''),
            d.get('description', ''),
            d.get('scope', ''),
        )


class SnippetManager:
    """片段管理器"""

    def __init__(self, filepath="snippets.json"):
        self.filepath = filepath
        self.snippets: Dict[str, Snippet] = {}
        self._load_builtin()
        self._load_user()

    def _load_builtin(self):
        """加载内置片段"""
        builtin = [
            Snippet("if", "if", "if ${1:condition}:\n    ${2:pass}",
                    "if 语句", "python"),
            Snippet("for", "for", "for ${1:item} in ${2:iterable}:\n    ${3:pass}",
                    "for 循环", "python"),
            Snippet("while", "while", "while ${1:condition}:\n    ${2:pass}",
                    "while 循环", "python"),
            Snippet("def", "def", "def ${1:name}(${2:args}):\n    ${3:pass}",
                    "函数定义", "python"),
            Snippet("class", "class",
                    "class ${1:Name}:\n    def __init__(self${2:, args}):\n        ${3:pass}",
                    "类定义", "python"),
            Snippet("try", "try",
                    "try:\n    ${1:pass}\nexcept ${2:Exception} as e:\n    ${3:pass}",
                    "try/except", "python"),
            Snippet("with", "with",
                    "with ${1:expression} as ${2:var}:\n    ${3:pass}",
                    "with 语句", "python"),
            Snippet("main", "main",
                    "def main():\n    ${1:pass}\n\n\nif __name__ == '__main__':\n    main()",
                    "main 入口", "python"),
            Snippet("import", "import", "import ${1:module}", "import", "python"),
            Snippet("log", "log", "logger.info(f'${1:message}')",
                    "日志语句", "python"),
            Snippet("print", "print", "print(f'${1:value}')", "print", "python"),
        ]
        for s in builtin:
            self.snippets[s.prefix] = s

    def _load_user(self):
        """加载用户片段"""
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, encoding='utf-8') as f:
                data = json.load(f)
            for item in data.get('snippets', []):
                s = Snippet.from_dict(item)
                self.snippets[s.prefix] = s
        except Exception as e:
            print("[Snippets] 加载失败: %s" % e)

    def save_user(self):
        """保存用户片段"""
        try:
            user = [s for s in self.snippets.values()
                    if s.prefix not in self._builtin_prefixes()]
            data = {'snippets': [s.to_dict() for s in user]}
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[Snippets] 保存失败: %s" % e)

    def _builtin_prefixes(self):
        return {'if', 'for', 'while', 'def', 'class', 'try', 'with',
                'main', 'import', 'log', 'print'}

    def get(self, prefix) -> Optional[Snippet]:
        return self.snippets.get(prefix)

    def list_all(self) -> List[Snippet]:
        return list(self.snippets.values())

    def add(self, snippet):
        self.snippets[snippet.prefix] = snippet
        self.save_user()

    def remove(self, prefix):
        if prefix in self.snippets:
            del self.snippets[prefix]
            self.save_user()


# 全局单例
_snippet_manager = None


def get_snippet_manager():
    global _snippet_manager
    if _snippet_manager is None:
        _snippet_manager = SnippetManager()
    return _snippet_manager