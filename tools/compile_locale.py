#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""翻译文件生成与编译（P1-2）

背景
----
修复前仓库里只有 ``locale/zh_CN/LC_MESSAGES/qingcao.po``：

* 文件头声明 ``charset=UTF-8``，但正文实际是 **GBK 字节**，
  任何 UTF-8 解析器都会失败（gettext 会静默乱码）；
* 全仓**没有任何 .mo 文件**，而 ``gettext.translation()`` 只认
  .mo，因此 ``main.py`` 的国际化永远走 FileNotFoundError 回退；
* ``core/i18n.py`` 声明支持 4 种语言，但只有 1 个语言目录。

本工具做三件事：
1. 把每个 ``.po`` 按声明的编码（必要时自动探测）统一转成 UTF-8；
2. 把 ``.po`` 编译成 gettext 可加载的 ``.mo``（纯 Python 实现，
   不依赖系统 msgfmt）；
3. ``--scaffold`` 会为缺失的语言生成脚手架 .po（msgstr 留空，
   表示"未翻译"，gettext 会回退到 msgid 原文）。

用法::

    python tools/compile_locale.py            # 编译所有语言
    python tools/compile_locale.py --check    # 只检查，不写文件
    python tools/compile_locale.py --scaffold # 为缺失语言生成脚手架
"""
import io
import os
import re
import struct
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_DIR = os.path.join(ROOT, 'locale')
DOMAIN = 'qingcao'
LANGUAGES = ['zh_CN', 'en_US', 'ja_JP', 'ko_KR']


# ============================================================
# PO 解析
# ============================================================
def _unescape(s: str) -> str:
    """还原 PO 字符串转义"""
    return (s.replace('\\n', '\n')
             .replace('\\t', '\t')
             .replace('\\r', '\r')
             .replace('\\"', '"')
             .replace('\\\\', '\\'))


def parse_po(text: str):
    """解析 PO 文本，返回 (header_dict, [(msgid, msgstr), ...])"""
    header = {}
    entries = []

    msgid_parts = []
    msgstr_parts = []
    mode = None
    current_comment = []

    def flush():
        nonlocal msgid_parts, msgstr_parts, mode
        if mode is not None:
            msgid = ''.join(msgid_parts)
            msgstr = ''.join(msgstr_parts)
            if msgid == '':
                # 头部
                for line in msgstr.split('\n'):
                    if ':' in line:
                        k, v = line.split(':', 1)
                        header[k.strip()] = v.strip()
            else:
                entries.append((msgid, msgstr))
        msgid_parts = []
        msgstr_parts = []
        mode = None

    for raw in text.splitlines():
        line = raw.rstrip('\r')
        if not line.strip():
            flush()
            continue
        if line.startswith('#'):
            current_comment.append(line)
            continue
        if line.startswith('msgid '):
            if mode is not None:
                flush()
            mode = 'id'
            msgid_parts.append(_unescape(line[6:].strip()[1:-1]))
        elif line.startswith('msgstr '):
            mode = 'str'
            msgstr_parts.append(_unescape(line[7:].strip()[1:-1]))
        elif line.startswith('msgid_plural'):
            # 复数形式暂不支持，跳过
            continue
        elif line.startswith('"'):
            value = _unescape(line.strip()[1:-1])
            if mode == 'id':
                msgid_parts.append(value)
            elif mode == 'str':
                msgstr_parts.append(value)

    flush()
    return header, entries


# ============================================================
# .mo 生成
# ============================================================
def build_mo(entries, lang: str = '') -> bytes:
    """把 (msgid, msgstr) 列表编译为 .mo 字节流

    重要（P1-2）: 必须在 .mo 中写入 **元数据条目**
    （msgid="" / msgstr="Content-Type: text/plain; charset=UTF-8..."）。
    否则 gettext 不知道编码，会把 msgstr 当 latin-1 字节串返回，
    调用方拿到的是 bytes 而不是 str，界面上仍会乱码。
    """
    meta = (
        "Project-Id-Version: QingCao 2.1\n"
        "Language: %s\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
    ) % lang

    all_entries = [('', meta)]
    all_entries += list(entries)

    pairs = sorted(
        (k.encode('utf-8'), v.encode('utf-8'))
        for k, v in all_entries if v
    )

    offsets = []
    ids = b''
    strs = b''
    for k, v in pairs:
        offsets.append((len(ids), len(k), len(strs), len(v)))
        ids += k + b'\x00'
        strs += v + b'\x00'

    keystart = 7 * 4 + 16 * len(pairs)
    valuestart = keystart + len(ids)

    koffsets = []
    voffsets = []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]

    output = struct.pack(
        "Iiiiiii",
        0x950412de,          # magic
        0,                   # version
        len(pairs),          # number of entries
        7 * 4,               # offset of key table
        7 * 4 + len(pairs) * 8,  # offset of value table
        0,                   # hash table size
        0,                   # hash table offset
    )
    output += struct.pack("i" * len(koffsets), *koffsets)
    output += struct.pack("i" * len(voffsets), *voffsets)
    output += ids
    output += strs
    return output


# ============================================================
# 单语言处理
# ============================================================
def find_po(lang: str) -> str:
    return os.path.join(LOCALE_DIR, lang, 'LC_MESSAGES', f'{DOMAIN}.po')


def find_mo(lang: str) -> str:
    return os.path.join(LOCALE_DIR, lang, 'LC_MESSAGES', f'{DOMAIN}.mo')


def read_po_text(path: str):
    """读取 .po，自动处理编码不一致

    返回 (text, note)。note 非空表示做过编码修正。
    """
    raw = open(path, 'rb').read()
    declared = b'UTF-8'
    m = re.search(rb'charset=([A-Za-z0-9_\-]+)', raw)
    if m:
        declared = m.group(1)
    declared_txt = declared.decode('ascii', 'replace')

    # 先按 UTF-8 试
    try:
        text = raw.decode('utf-8')
        if declared.upper().replace(b'-', b'') not in (b'UTF8', b'UTF8SIG'):
            return text, ('声明 charset=%s，实际为 UTF-8，已统一'
                          % declared_txt)
        return text, ''
    except UnicodeDecodeError:
        pass

    # 再按常见中文编码试
    for enc in ('gbk', 'gb18030', 'big5', 'latin-1'):
        try:
            text = raw.decode(enc)
            return text, ('正文实为 %s（头部却声明 %s），已转换为 UTF-8'
                          % (enc, declared_txt))
        except UnicodeDecodeError:
            continue

    raise RuntimeError('无法解码 %s' % path)


def normalize_po(text: str) -> str:
    """把 PO 头部 charset 统一为 UTF-8，换行统一为 \\n"""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(
        r'(charset=)[A-Za-z0-9_\-]+',
        r'\1UTF-8',
        text,
        count=1,
    )
    return text


def compile_language(lang: str, check_only: bool = False) -> bool:
    """编译单个语言，返回是否成功"""
    po = find_po(lang)
    if not os.path.exists(po):
        print("  [%s] 缺少 .po，跳过" % lang)
        return False

    try:
        text, note = read_po_text(po)
    except Exception as e:
        print("  [%s] 读取失败: %s" % (lang, e))
        return False

    if note:
        print("  [%s] 修正编码: %s" % (lang, note))
        if not check_only:
            text = normalize_po(text)
            io.open(po, 'w', encoding='utf-8', newline='\n').write(text)

    text = normalize_po(text)
    _, entries = parse_po(text)

    if not entries:
        print("  [%s] 没有任何 msgid，跳过" % lang)
        return False

    mo = build_mo(entries, lang=lang)
    translated = sum(1 for _, v in entries if v)
    print("  [%s] %d 条词条（已翻译 %d 条），.mo %d 字节"
          % (lang, len(entries), translated, len(mo)))

    if check_only:
        return True

    mo_path = find_mo(lang)
    os.makedirs(os.path.dirname(mo_path), exist_ok=True)
    with open(mo_path, 'wb') as f:
        f.write(mo)
    return True


# ============================================================
# 脚手架
# ============================================================
SCAFFOLD_HEADER = '''msgid ""
msgstr ""
"Project-Id-Version: QingCao 2.1\\n"
"Language: {lang}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
'''


def scaffold(lang: str, msgids):
    """为缺失语言生成脚手架 .po（msgstr 留空 => 回退到原文）"""
    po = find_po(lang)
    if os.path.exists(po):
        return False
    os.makedirs(os.path.dirname(po), exist_ok=True)
    lines = [SCAFFOLD_HEADER.format(lang=lang)]
    for m in msgids:
        lines.append('msgid "%s"' % m.replace('\\', '\\\\').replace('"', '\\"'))
        lines.append('msgstr ""')
        lines.append('')
    io.open(po, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
    print("  [%s] 已生成脚手架 .po（%d 条待翻译）" % (lang, len(msgids)))
    return True


# ============================================================
# main
# ============================================================
def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    check_only = '--check' in argv
    do_scaffold = '--scaffold' in argv

    print("[compile_locale] 语言目录: %s" % LOCALE_DIR)
    if not os.path.isdir(LOCALE_DIR):
        print("[compile_locale] locale/ 不存在")
        return 1

    if do_scaffold:
        # 以 zh_CN 的 msgid 集合作为基准
        base = find_po('zh_CN')
        msgids = []
        if os.path.exists(base):
            text, _ = read_po_text(base)
            _, entries = parse_po(normalize_po(text))
            msgids = [k for k, _ in entries]
        for lang in LANGUAGES:
            if lang == 'zh_CN':
                continue
            scaffold(lang, msgids)

    ok = 0
    for lang in LANGUAGES:
        if compile_language(lang, check_only):
            ok += 1

    if ok == 0:
        print("[compile_locale] 没有任何语言成功编译")
        return 1
    if not check_only and ok < len(LANGUAGES):
        print("[compile_locale] 提示：可用 --scaffold 为缺失语言生成 .po")
    print("[compile_locale] 完成：%d/%d 语言" % (ok, len(LANGUAGES)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
