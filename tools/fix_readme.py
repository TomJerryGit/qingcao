#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""README 代码块结构重建（P2）

问题回顾
--------
原 README 的代码栅栏被批量脚本删掉了，只剩下裸语言标记
（bash / json / python / text）。此前的逐行启发式修复又引入了
"空围栏对"和"正文被包进代码块"等新问题，需要一次性重建。

重建规则（确定性强，不再逐行猜测）
--------------------------------
1. 任何独立成行的裸语言标记 → 该行替换为开栅栏 ```<lang>；
2. 代码块结束条件（满足任一即闭合）：
     * 遇到下一个裸语言标记（它是下一块的开头）；
     * 遇到空行之后紧跟的**正文行**（Markdown 标题 / 列表 /
       引用 / 表格 / 已知段落开头 / 含中文的说明句）；
3. 已经存在的合法栅栏原样保留（不重复插入）。

用法::

    python tools/fix_readme.py --check
    python tools/fix_readme.py
"""
import io
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, 'README.md')

LANG_MARKERS = {
    'bash', 'sh', 'shell', 'json', 'python', 'py', 'text', 'txt',
    'yaml', 'yml', 'ini', 'toml', 'javascript', 'js', 'html', 'css',
    'sql', 'powershell', 'ps1',
}

MD_RE = re.compile(r'^(#{1,6}\s|[-*+]\s|\d+\.\s|>\s|\|)')

# 已知正文小标题（无缩进、无标点）
PROSE_TITLES = {
    '方式三：从 pip 安装（实验性）', '基本操作', '快捷键速查',
    '切换云端模型', '权限列表', '一键生成插件骨架', '配置文件位置',
    '便携模式', '命令行选项', '环境准备', '项目结构', '代码检查',
    '运行测试', '打包', '截图', '常见问题', '贡献', '提交 PR 前',
    '报告 Bug', '许可证', '联系方式', '致谢', '目录结构',
    'plugin.json 示例', '__init__.py 示例', '权限说明',
}

CJK_RE = re.compile(r'[\u4e00-\u9fff]')
EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF\u2699\u26A1\u2728]')


def is_prose(line: str) -> bool:
    """该行是否属于 Markdown 正文（而非代码）"""
    s = line.strip()
    if not s:
        return False
    if line.startswith((' ', '\t')):
        return False
    if MD_RE.match(s):
        return True
    if EMOJI_RE.match(s):
        return True
    if s.rstrip('：:') in PROSE_TITLES:
        return True
    # 含中文且不像代码（无 = ( ) { } < > 等），视为说明文字
    if CJK_RE.search(s) and not re.search(r'[=(){}\[\]<>;]', s):
        return True
    return False


def rebuild(text: str):
    lines = text.split('\n')
    out = []
    changes = []
    i = 0
    n = len(lines)
    in_code = False
    lang = ''

    while i < n:
        line = lines[i]
        s = line.strip()

        # 已存在的栅栏：保留，维护状态
        if line.startswith('```'):
            out.append(line)
            in_code = not in_code
            i += 1
            continue

        # 裸语言标记（不在代码块内）→ 开栅栏
        if s in LANG_MARKERS and not in_code and not line.startswith((' ', '\t')):
            out.append('```' + s)
            in_code = True
            lang = s
            changes.append('L%d: 开栅栏 ```%s' % (i + 1, s))
            i += 1
            continue

        if in_code:
            # 代码是否继续？
            if not s:
                out.append(line)
                i += 1
                continue
            # 下一个裸语言标记 → 当前块结束
            if s in LANG_MARKERS and not line.startswith((' ', '\t')):
                out.append('```')
                out.append('```' + s)
                changes.append('L%d: 闭合后开新块 ```%s' % (i + 1, s))
                lang = s
                i += 1
                continue
            # 正文 → 闭合代码块，正文留在外面
            if is_prose(line):
                out.append('```')
                out.append('')
                changes.append('L%d: 正文前闭合代码块' % (i + 1))
                in_code = False
                lang = ''
                continue  # 不前进，让正文走正常分支
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    if in_code:
        out.append('```')
        changes.append('文件末尾: 补闭合栅栏')

    return '\n'.join(out), changes


def audit(text: str):
    fences = [l for l in text.split('\n') if l.startswith('```')]
    return len(fences), len(fences) % 2


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    check = '--check' in argv

    text = io.open(README, encoding='utf-8').read()
    new_text, changes = rebuild(text)
    total, odd = audit(new_text)

    print('[fix_readme] 计划调整 %d 处' % len(changes))
    for c in changes[:40]:
        print('  - ' + c)
    print('[fix_readme] 重建后栅栏数: %d（%s）'
          % (total, '奇数，仍未闭合' if odd else '偶数，成对'))

    if check:
        return 1 if odd else 0

    io.open(README, 'w', encoding='utf-8', newline='\n').write(new_text)
    print('[fix_readme] 已写入 README.md')
    return 0


if __name__ == '__main__':
    sys.exit(main())
