# -*- coding: utf-8 -*-
"""代码度量"""
import os
import re
from typing import Any, Dict, List


def analyze_python(text):
    """分析 Python 代码"""
    import ast

    metrics = {
        'total_lines': 0,
        'code_lines': 0,
        'comment_lines': 0,
        'blank_lines': 0,
        'classes': 0,
        'functions': 0,
        'methods': 0,
        'imports': 0,
        'longest_function': (0, ''),
        'functions_detail': [],
    }

    lines = text.splitlines()
    metrics['total_lines'] = len(lines)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            metrics['blank_lines'] += 1
        elif stripped.startswith('#'):
            metrics['comment_lines'] += 1
        else:
            metrics['code_lines'] += 1

    # AST 分析
    try:
        tree = ast.parse(text)
    except Exception:
        return metrics

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            metrics['classes'] += 1
        elif isinstance(node, ast.FunctionDef):
            # 判断是否方法（在类里）
            if any(isinstance(p, ast.ClassDef) for p in ast.walk(tree)
                   if hasattr(p, 'body') and node in p.body):
                metrics['methods'] += 1
            else:
                metrics['functions'] += 1

            # 函数长度
            end_line = getattr(node, 'end_lineno',
                                node.lineno + 10)
            length = end_line - node.lineno + 1
            metrics['functions_detail'].append({
                'name': node.name,
                'line': node.lineno,
                'length': length,
                'args': len(node.args.args),
            })
            if length > metrics['longest_function'][0]:
                metrics['longest_function'] = (length, node.name)

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            metrics['imports'] += 1

    return metrics


def calculate_complexity(text):
    """估算圈复杂度（简单版）"""
    # 统计决策点
    decision_keywords = [
        r'\bif\b', r'\belif\b', r'\bfor\b', r'\bwhile\b',
        r'\band\b', r'\bor\b', r'\bexcept\b', r'\bwith\b'
    ]

    complexity = 1
    for line in text.splitlines():
        # 跳过注释
        if line.strip().startswith('#'):
            continue
        for kw in decision_keywords:
            complexity += len(re.findall(kw, line))

    return complexity


def analyze_file(filepath):
    """分析单个文件"""
    try:
        with open(filepath, encoding='utf-8',
                  errors='replace') as f:
            text = f.read()
    except Exception as e:
        return {'error': str(e)}

    ext = os.path.splitext(filepath)[1].lower()

    if ext in ('.py', '.pyw'):
        metrics = analyze_python(text)
        metrics['complexity'] = calculate_complexity(text)
        metrics['language'] = 'Python'
    else:
        # 通用分析
        lines = text.splitlines()
        metrics = {
            'total_lines': len(lines),
            'code_lines': sum(
                1 for l in lines if l.strip() and
                not l.strip().startswith(('#', '//', '/*', '*'))
            ),
            'comment_lines': sum(
                1 for l in lines if l.strip().startswith(
                    ('#', '//', '/*', '*')
                )
            ),
            'blank_lines': sum(1 for l in lines if not l.strip()),
            'language': ext.lstrip('.').upper() or 'Text',
        }

    metrics['filepath'] = filepath
    metrics['size'] = os.path.getsize(filepath)

    return metrics


def analyze_directory(root_path, extensions=None):
    """分析整个目录"""
    if extensions is None:
        extensions = ['.py', '.pyw', '.js', '.ts', '.c', '.cpp',
                      '.h', '.hpp', '.java', '.go', '.rs']

    totals = {
        'files': 0,
        'total_lines': 0,
        'code_lines': 0,
        'comment_lines': 0,
        'blank_lines': 0,
        'size': 0,
    }

    file_metrics = []

    exclude_dirs = {'.git', '__pycache__', 'node_modules',
                    'venv', '.venv', 'build', 'dist'}

    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames
                       if d not in exclude_dirs and
                       not d.startswith('.')]

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in extensions:
                continue

            fpath = os.path.join(dirpath, fname)
            m = analyze_file(fpath)
            if 'error' not in m:
                totals['files'] += 1
                totals['total_lines'] += m.get('total_lines', 0)
                totals['code_lines'] += m.get('code_lines', 0)
                totals['comment_lines'] += m.get('comment_lines', 0)
                totals['blank_lines'] += m.get('blank_lines', 0)
                totals['size'] += m.get('size', 0)
                file_metrics.append(m)

    return {
        'totals': totals,
        'files': file_metrics,
    }