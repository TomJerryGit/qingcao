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


def format_template(name: str, **kwargs) -> str:
    """格式化模板"""
    template = TEMPLATES.get(name)
    if not template:
        return ""
    code = template.get("code", "")
    try:
        return code.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return code
