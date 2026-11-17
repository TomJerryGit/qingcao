# -*- coding: utf-8 -*-
"""AI 结果应用前校验：Python 语法 / JSON / 空结果。"""

import ast
import json
import os


def validate_result(code, filepath=""):
    text = (code or "").strip()
    if not text:
        return (False, "结果为空")
    ext = os.path.splitext(str(filepath or ""))[1].lower()
    if ext == ".py":
        try:
            ast.parse(text)
        except SyntaxError as e:
            return (False, "Python 语法错误：第 %s 行 %s" % (e.lineno, e.msg))
    elif ext == ".json" or text[:1] in ("{", "["):
        try:
            json.loads(text)
        except Exception as e:
            return (False, "JSON 校验失败：%s" % e)
    return (True, "")
