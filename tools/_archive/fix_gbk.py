#-*- coding: utf-8 -*-
"""批量将 GBK 编码的 Python 文件转为 UTF-8"""
import os
import sys

TARGET_DIRS = ['app', 'core', 'ui', 'infrastructure',
               'plugins', 'tests', 'tools']
SKIP_DIRS = {'__pycache__', '.git', '_archived_tools',
             'venv', '.venv', 'env'}


def detect_encoding(filepath):
    """检测文件编码"""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except Exception:
        return None

    if not data:
        return 'utf-8'

    # BOM 检测
    if data.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    if data.startswith(b'\xff\xfe') or data.startswith(b'\xfe\xff'):
        return 'utf-16'

    # UTF-8 优先
    try:
        data.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    # GBK
    try:
        data.decode('gbk')
        return 'gbk'
    except UnicodeDecodeError:
        pass

    # GB18030
    try:
        data.decode('gb18030')
        return 'gb18030'
    except UnicodeDecodeError:
        pass

    return None


def fix_file(filepath, encoding):
    """转换编码为 UTF-8"""
    try:
        with open(filepath, 'r', encoding=encoding) as f:
            text = f.read()

        # 规范化换行为 \n
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)

        return True
    except Exception as e:
        print('  FAIL: %s (%s)' % (filepath, e))
        return False


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    fixed = 0
    checked = 0
    skipped = 0

    for target in TARGET_DIRS:
        base = os.path.join(root, target)
        if not os.path.isdir(base):
            continue

        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

            for fname in filenames:
                if not fname.endswith('.py'):
                    continue

                full = os.path.join(dirpath, fname)
                checked += 1

                enc = detect_encoding(full)
                if enc is None:
                    print('  SKIP: 未知编码 %s' % full)
                    skipped += 1
                    continue

                if enc == 'utf-8':
                    continue

                rel = os.path.relpath(full, root)
                print('  [%s] %s' % (enc, rel))

                if fix_file(full, enc):
                    fixed += 1

    print()
    print('=' * 60)
    print('检查 %d 个文件，修复 %d 个，跳过 %d 个'
          % (checked, fixed, skipped))
    print('=' * 60)


if __name__ == '__main__':
    main()