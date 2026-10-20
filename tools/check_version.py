#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""版本一致性检查（P1-1）

检查全仓版本号是否与 ``version.py`` 保持一致，防止再次出现
"CHANGELOG 已发布 2.1.0、代码里全是 2.0.0" 这类版本漂移。

用法:
    python -m tools.check_version          # 检查，失败时退出码 1
    python -m tools.check_version -v       # 打印每个文件的实际值

检查项:
    1. version.py 的 __version__ 可解析
    2. VERSION 文件与 version.py 一致
    3. installer.iss 的 MyAppVersion 与 version.py 一致
    4. 生产代码中不再出现硬编码的应用版本字面量
       （app/ / core/ / ui/ / infrastructure/ / main.py / build*.py）
    5. README 徽章与发行包名与 version.py 一致
"""
import io
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 允许包含版本字面量的文件（示例/测试/文档/归档不参与检查）
SKIP_DIRS = {
    '__pycache__', '_archive', '.git', 'tools', 'tests', 'docs',
    '1.0 QingCaoEditor_Others', 'node_modules',
}
SKIP_FILES = {
    'version.py',           # 权威来源
    'VERSION',              # 由 release.py 同步
    'CHANGELOG.md',         # 历史记录，天然包含各版本号
    'fake_version.py',
}


def read_text(path):
    with io.open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def get_authoritative_version():
    """读取 version.py 中的 __version__"""
    path = os.path.join(ROOT, 'version.py')
    src = read_text(path)
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', src, re.M)
    if not m:
        raise SystemExit("[check_version] 无法从 version.py 解析 __version__")
    return m.group(1)


def iter_source_files():
    """遍历需要检查的源码文件"""
    exts = ('.py', '.md', '.iss', '.yml', '.yaml')
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            if name.endswith('.bak') or '.bak.' in name:
                continue
            if not name.endswith(exts):
                continue
            yield os.path.join(dirpath, name)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    verbose = '-v' in argv or '--verbose' in argv

    version = get_authoritative_version()
    print("[check_version] 权威版本: %s (version.py)" % version)

    problems = []

    # ---- 1. VERSION 文件 ----
    vpath = os.path.join(ROOT, 'VERSION')
    if os.path.exists(vpath):
        file_ver = read_text(vpath).strip()
        if file_ver != version:
            problems.append("VERSION 文件为 %r，应为 %r" % (file_ver, version))
        elif verbose:
            print("  OK  VERSION = %s" % file_ver)
    else:
        problems.append("缺少 VERSION 文件")

    # ---- 2. installer.iss ----
    iss = os.path.join(ROOT, 'installer.iss')
    if os.path.exists(iss):
        m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', read_text(iss))
        if m:
            if m.group(1) != version:
                problems.append(
                    "installer.iss MyAppVersion = %r，应为 %r"
                    % (m.group(1), version)
                )
            elif verbose:
                print("  OK  installer.iss = %s" % m.group(1))
        else:
            problems.append("installer.iss 中找不到 MyAppVersion")

    # ---- 3. README ----
    readme = os.path.join(ROOT, 'README.md')
    if os.path.exists(readme):
        src = read_text(readme)
        for m in re.finditer(r'badge/version-([0-9]+\.[0-9]+\.[0-9]+)', src):
            if m.group(1) != version:
                problems.append(
                    "README 版本徽章为 %r，应为 %r" % (m.group(1), version)
                )
        for m in re.finditer(
            r'QingCaoEditor(?:_Setup)?_v([0-9]+\.[0-9]+\.[0-9]+)', src
        ):
            if m.group(1) != version:
                problems.append(
                    "README 发行包名为 %r，应为 %r" % (m.group(1), version)
                )

    # ---- 4. 生产代码中的过期应用版本字面量 ----
    # 说明：插件/主题自带的版本号（1.0.0 等）是合法的，不能
    # 一律报错。这里只检查"曾经是应用版本号"的历史字面量，
    # 它们出现即说明有人又把应用版本硬编码进了代码。
    # 历史上发布过的版本号：出现即说明有人又把版本硬编码回来了。
    # 发布 2.2.0 时补充：2.1.0 曾是 build.py / main.py 的“兜底字面量”，
    # 导致 version.py 导入失败时静默产出过期版本（现已改为读 VERSION 文件）。
    stale_versions = {
        '2.1.0', '2.0.0', '1.9.9', '1.9.0', '1.8.0', '1.0.0-app',
    } - {version}

    # 插件 API 版本（2.0.0）是独立契约，允许出现在固定常量中
    api_version_ok = {
        'CURRENT_API_VERSION', 'API_VERSION',
        'MIN_SUPPORTED_APP_VERSION', 'api_version',
        'min_app_version', 'max_app_version',
    }
    # 明确用于测试/演示的代码块（自测 main、版本比较样例）
    selftest_markers = (
        "if __name__ == '__main__'", 'if __name__ == "__main__"',
    )

    literal = re.compile(r'["\']([0-9]+\.[0-9]+\.[0-9]+)["\']')
    for path in iter_source_files():
        rel = os.path.relpath(path, ROOT)
        top = rel.split(os.sep)[0]
        if top not in ('app', 'core', 'ui', 'infrastructure', 'main.py',
                       'build.py', 'build_installer.py', 'build_linux.py',
                       'build_macos.py', 'release.py'):
            continue
        try:
            lines = read_text(path).splitlines()
        except Exception:
            continue

        # 找到自测块起始行，其后的内容不参与检查
        selftest_at = None
        for i, line in enumerate(lines):
            if any(m in line for m in selftest_markers):
                selftest_at = i
                break

        for i, line in enumerate(lines, 1):
            if selftest_at is not None and i - 1 >= selftest_at:
                continue
            # 跳过注释行：文档里引用历史版本号（如“原兜底是 2.1.0”）
            # 是合法说明，不应被当成硬编码
            if line.lstrip().startswith('#'):
                continue
            for m in literal.finditer(line):
                found = m.group(1)
                if found not in stale_versions:
                    continue
                if any(k in line for k in api_version_ok):
                    continue
                problems.append(
                    "%s:%d 出现过期应用版本字面量 %r"
                    "（请从 version.py 导入，勿硬编码）"
                    % (rel, i, found)
                )

    # ---- 汇总 ----
    if problems:
        print("\n[check_version] 发现 %d 处版本不一致:" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1

    print("[check_version] 全部一致 - OK")
    return 0


if __name__ == '__main__':
    sys.exit(main())
