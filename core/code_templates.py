# -*- coding: utf-8 -*-
"""代码模板"""
import datetime
from typing import Dict, List


def get_author():
    """获取作者名"""
    try:
        from PyQt5.QtCore import QSettings
        settings = QSettings("QingCao", "Editor")
        return settings.value("author_name", "anonymous", type=str)
    except Exception:
        return "anonymous"


TEMPLATES = {
    # Python
    "py_class": {
        "name": "Python 类",
        "code": '''class {name}:
    """{docstring}"""

    def __init__(self{args}):
        {init_body}

    def {method}(self):
        {method_body}
''',
        "placeholders": ["name", "docstring", "args",
                          "init_body", "method", "method_body"],
    },
    "py_function": {
        "name": "Python 函数",
        "code": '''def {name}({args}):
    """
    {docstring}

    Args:
        {args_doc}

    Returns:
        {return_doc}
    """
    {body}
''',
        "placeholders": ["name", "args", "docstring",
                          "args_doc", "return_doc", "body"],
    },
    "py_test": {
        "name": "Python 测试",
        "code": '''# -*- coding: utf-8 -*-
"""测试 {module_name}"""
import unittest
from {module_path} import {target}


class Test{name}(unittest.TestCase):
    """测试类"""

    def setUp(self):
        """测试前准备"""
        pass

    def tearDown(self):
        """测试后清理"""
        pass

    def test_{test_name}(self):
        """测试 {test_desc}"""
        # Arrange
        {arrange}

        # Act
        result = {action}

        # Assert
        self.assertEqual(result, {expected})


if __name__ == "__main__":
    unittest.main()
''',
        "placeholders": ["module_name", "module_path", "target",
                          "name", "test_name", "test_desc",
                          "arrange", "action", "expected"],
    },
    "py_main": {
        "name": "Python 主程序",
        "code": '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
{name}
====================
Author: {author}
Date: {date}
"""

import sys


def main():
    """主函数"""
    {body}
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
        "placeholders": ["name", "author", "date", "body"],
    },

    # JavaScript
    "js_function": {
        "name": "JavaScript 函数",
        "code": '''/**
 * {docstring}
 * @param {{ {param_types} }} {params}
 * @returns {{ {return_type} }}
 */
function {name}({params}) {{
    {body}
}}
''',
        "placeholders": ["docstring", "param_types", "params",
                          "return_type", "name", "body"],
    },
    "js_class": {
        "name": "JavaScript 类",
        "code": '''class {name} {{
    constructor({args}) {{
        {init_body}
    }}

    {method}({method_args}) {{
        {method_body}
    }}
}}

module.exports = {name};
''',
        "placeholders": ["name", "args", "init_body",
                          "method", "method_args", "method_body"],
    },

    # 项目文件
    "gitignore": {
        "name": ".gitignore",
        "code": '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
build/
dist/
*.egg-info/
.eggs/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# 项目特定
data/
logs/
backup/
*.log
''',
        "placeholders": [],
    },
    "readme": {
        "name": "README.md",
        "code": '''# {project_name}

{description}

## 安装

```bash
pip install -r requirements.txt

## 使用

```bash
python main.py
```

## 目录结构

```
project/
├── main.py
├── requirements.txt
└── README.md
```

## 许可证

MIT License
''',
        "placeholders": ["project_name", "description"],
    },
}


# ============================================================
# 辅助函数
# ============================================================
def get_template(name: str) -> dict:
    """获取指定模板"""
    return TEMPLATES.get(name, {})


def list_templates() -> List[str]:
    """列出所有模板名"""
    return list(TEMPLATES.keys())


def get_template_placeholders(template_name: str) -> List[str]:
    """取某个模板需要填充的占位符列表（供 UI 生成输入框）"""
    return list(TEMPLATES.get(template_name, {}).get("placeholders") or [])


def format_template(template_name: str, **kwargs) -> str:
    """格式化模板

    ★ 修复（实测发现）：形参原名为 `name`，与模板占位符 `{name}` **冲突**

        调用 `format_template("py_class", name="MyClass")` 会抛
        `TypeError: format_template() got multiple values for argument 'name'`
        —— 也就是说"给类名赋值"这个最基本的用法直接不可用。
        现把形参改名为 `template_name`（位置调用保持兼容）。

    ★ 同时修掉"占位符缺失时原样返回未格式化代码"的问题：

        原实现 `except (KeyError...) return code` 会把 `{docstring}` 这类
        占位符**原样**留在生成的文件里，用户拿到的是语法错误的一段代码。
        现在缺失的占位符统一填空字符串，生成结果始终是合法文本。
    """
    template = TEMPLATES.get(template_name)
    if not template:
        return ""
    code = template.get("code", "")

    # 缺失的占位符填空串（而不是让整段格式化失败、原样返回带 {xxx} 的代码）
    fill = {ph: "" for ph in (template.get("placeholders") or [])}
    fill.update({k: ("" if v is None else str(v)) for k, v in kwargs.items()})
    try:
        return code.format_map(_SafeDict(fill))
    except (IndexError, ValueError) as e:
        print("[代码模板] 格式化 %s 失败: %s" % (template_name, e))
        return code


class _SafeDict(dict):
    """`format_map` 用的字典：缺失键返回空串而不是抛 KeyError"""

    def __missing__(self, key):        # noqa: D105
        return ""
