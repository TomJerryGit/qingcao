#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""工作区完整性校验（不依赖 git status）

为什么需要这个工具
------------------
本仓库有 `.gitattributes` 声明 `text eol=lf`。当索引中的 blob 与
工作区文件的行尾不一致时，`git status` 会报大量"已修改"，但这**可能
只是 stat 缓存 / 归一化造成的假象**，内容其实与 HEAD 完全一致。

实测教训（本次会话真实踩到）：
    `git status` 报 83 个文件已修改，而逐文件用 blob 哈希比对，
    工作区、索引、HEAD 三者**完全相同**：

        work  哈希: 352f6aa6b9557835fccb07f66a01bd645a37d99d
        HEAD  哈希: 352f6aa6b9557835fccb07f66a01bd645a37d99d
        index 哈希: 352f6aa6b9557835fccb07f66a01bd645a37d99d

    同时 `git hash-object <file>` 返回的却是 `ca5444ad…`（被过滤器
    归一化后的值）。仅凭 `git status` 会误判仓库"很脏"，甚至引发
    错误的清理/重建操作（本次就因此绕了很大弯路）。

本工具用**内容哈希**（自己算 `blob <len>\\0<data>` 的 SHA-1，绕过
git 的过滤器）逐文件比对工作区与 HEAD，给出可信结论。

用法::

    python tools/verify_worktree.py            # 与 HEAD 比对
    python tools/verify_worktree.py --rev X    # 与指定提交比对
    python tools/verify_worktree.py --quiet    # 只输出结论

退出码: 0 = 完全一致；1 = 存在差异（并列出文件）
"""
import hashlib
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git(*args, binary=False):
    r = subprocess.run(
        ['git'] + list(args), cwd=ROOT, capture_output=True,
    )
    if binary:
        return r.stdout
    return r.stdout.decode('utf-8', errors='replace')


def _try_reconfigure_stdout():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def blob_sha1(data: bytes) -> str:
    """按 git 的对象格式计算 blob 哈希（不经过任何 filters）"""
    h = hashlib.sha1()
    h.update(b'blob %d\0' % len(data))
    h.update(data)
    return h.hexdigest()


def main(argv=None):
    _try_reconfigure_stdout()
    argv = argv if argv is not None else sys.argv[1:]

    rev = 'HEAD'
    quiet = '--quiet' in argv
    if '--rev' in argv:
        i = argv.index('--rev')
        if i + 1 < len(argv):
            rev = argv[i + 1]

    files = [f for f in _git('ls-tree', '-r', '--name-only', rev)
             .splitlines() if f.strip()]
    if not files:
        print('[verify_worktree] 无法读取 %s 的文件清单' % rev)
        return 1

    same, differ, missing = [], [], []
    for f in files:
        path = os.path.join(ROOT, f)
        if not os.path.isfile(path):
            missing.append(f)
            continue
        with open(path, 'rb') as fh:
            work = fh.read()
        head = _git('show', '%s:%s' % (rev, f), binary=True)
        if blob_sha1(work) == blob_sha1(head):
            same.append(f)
        else:
            differ.append(f)

    if not quiet:
        print('[verify_worktree] 比对目标: %s' % rev)
        print('[verify_worktree] 树内文件数: %d' % len(files))
        print('  内容一致 : %d' % len(same))
        print('  内容不同 : %d' % len(differ))
        print('  工作区缺失: %d' % len(missing))

        # 附上 git status 的对比，帮助识别"假象"
        porcelain = [l for l in _git('status', '--porcelain').splitlines()
                     if l.strip()]
        if porcelain and not differ and not missing:
            print()
            print('  注意：git status 报告 %d 项，但内容哈希全部一致 ——'
                  % len(porcelain))
            print('  这是 .gitattributes 的 eol 归一化导致的 stat 假象，'
                  '非真实差异。')
            print('  如需让 status 也变干净，可执行（建议独立提交）：')
            print('      git add --renormalize .')
            print('      git commit -m "chore: 统一行尾为 LF"')

    if differ:
        print()
        print('[verify_worktree] 内容不同的文件（%d）:' % len(differ))
        for f in differ[:50]:
            print('  - ' + f)
        if len(differ) > 50:
            print('  ... 其余 %d 个' % (len(differ) - 50))
    if missing:
        print()
        print('[verify_worktree] 工作区缺失的文件（%d）:' % len(missing))
        for f in missing[:20]:
            print('  - ' + f)

    ok = not differ and not missing
    if not quiet:
        print()
        print('[verify_worktree] 结论: %s' % ('一致' if ok else '存在差异'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
