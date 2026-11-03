# -*- coding: utf-8 -*-
"""i18n 可翻译语料定义（v2.19 收口工具）

从 AST 中只提取**用户可见**字符串（UI 控件/对话框/菜单/状态栏/HTML 文案），
排除 docstring、日志、print、测试与代码片段。

    python tools/i18n_scope.py            # 统计
    python tools/i18n_scope.py --write    # 写 locale/zh_CN/translatable.json
"""

import argparse
import ast
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "locale", "zh_CN", "translatable.json")

# 用户可见调用/构造：函数名或属性名命中即收集其字符串参数
UI_CALLS = {
    "QLabel",
    "QPushButton",
    "QCheckBox",
    "QRadioButton",
    "QGroupBox",
    "QToolButton",
    "QAction",
    "QListWidgetItem",
    "QTreeWidgetItem",
    "QMessageBox",
    "QInputDialog",
    "QFileDialog",
    "QLineEdit",
    "setText",
    "setTitle",
    "setToolTip",
    "setStatusTip",
    "setWhatsThis",
    "setPlaceholderText",
    "setWindowTitle",
    "showMessage",
    "addAction",
    "addItem",
    "addTab",
    "setTabText",
    "setCurrentText",
    "setSuffix",
    "setPrefix",
    "information",
    "warning",
    "critical",
    "question",
    "getText",
    "getItem",
    "getOpenFileName",
    "getSaveFileName",
    "getExistingDirectory",
}

EXCLUDE_PREFIX = ("[", "===", "print(", "TODO", "FIXME")
EXCLUDE_SUBSTR = ("测试", "test_", "assert ")


def _has_cjk(s):
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def _is_docstring(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _docstrings(tree):
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and _is_docstring(body[0].value):
                docs.add(id(body[0].value))
    return docs


def _call_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def extract_file(path):
    src = io.open(path, encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    docs = _docstrings(tree)
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) not in UI_CALLS:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if not _is_docstring(arg) or id(arg) in docs:
                continue
            s = arg.value.strip()
            if not s or not _has_cjk(s):
                continue
            if s.startswith(EXCLUDE_PREFIX) or any(x in s for x in EXCLUDE_SUBSTR):
                continue
            found.add(s)
    return found


def collect(root=ROOT):
    corpus = set()
    files = 0
    for sub in ("ui",):
        base = os.path.join(root, sub)
        for dirpath, dirnames, names in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for n in names:
                if not n.endswith(".py"):
                    continue
                files += 1
                corpus |= extract_file(os.path.join(dirpath, n))
    return corpus, files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    corpus, files = collect()
    if args.write:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        io.open(OUT, "w", encoding="utf-8", newline="\n").write(
            json.dumps(sorted(corpus), ensure_ascii=False, indent=2)
        )
    print(
        "[i18n-scope] ui 文件=%d 可翻译语料=%d%s"
        % (files, len(corpus), " -> " + OUT if args.write else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
