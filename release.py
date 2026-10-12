#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发布流程脚本"""
import datetime
import json
import os
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(ROOT, 'VERSION')
VERSION_PY = os.path.join(ROOT, 'version.py')
CHANGELOG_FILE = os.path.join(ROOT, 'CHANGELOG.md')


def read_version():
    """读取版本号

    P1-1 修复：优先读 version.py（唯一权威来源），
    其次读 VERSION 文件。
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_qingcao_version", VERSION_PY
        )
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            v = getattr(mod, '__version__', '')
            if v:
                return v
    except Exception:
        pass

    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, encoding='utf-8') as f:
            return f.read().strip()

    raise RuntimeError("无法读取版本号（version.py / VERSION 均不可用）")


def write_version(version):
    """写入版本号

    P1-1 修复：原来只写 VERSION 文件，不更新 version.py，
    导致 bump 之后 version.py 仍是旧值（版本漂移）。
    现在两处同时写入。
    """
    with open(VERSION_FILE, 'w', encoding='utf-8', newline='') as f:
        f.write(version + "\n")

    # 同步 version.py（唯一权威来源）
    try:
        with open(VERSION_PY, encoding='utf-8') as f:
            src = f.read()
        import re
        new_src, n = re.subn(
            r'__version__\s*=\s*["\'][^"\']+["\']',
            '__version__ = "%s"' % version,
            src,
            count=1,
        )
        if n:
            with open(VERSION_PY, 'w', encoding='utf-8', newline='') as f:
                f.write(new_src)
            print("[release] version.py 已同步为 %s" % version)
        else:
            print("[release] 警告：未能在 version.py 中找到 __version__")
    except Exception as e:
        print("[release] 警告：同步 version.py 失败: %s" % e)


def bump_version(current, part='patch'):
    """升级版本号"""
    parts = current.split('.')
    while len(parts) < 3:
        parts.append('0')

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if part == 'major':
        major += 1
        minor = 0
        patch = 0
    elif part == 'minor':
        minor += 1
        patch = 0
    else:
        patch += 1

    return "%d.%d.%d" % (major, minor, patch)


def update_changelog(version, changes):
    """更新 CHANGELOG"""
    today = datetime.date.today().isoformat()

    entry = "## [%s] - %s\n\n" % (version, today)
    for change in changes:
        entry += "- " + change + "\n"
    entry += "\n"

    # 读取现有
    existing = ""
    if os.path.exists(CHANGELOG_FILE):
        with open(CHANGELOG_FILE, encoding='utf-8') as f:
            existing = f.read()

    # 插入到 Unreleased 之后
    header = "# Changelog\n\n"
    if not existing.startswith(header):
        existing = header + existing

    # 找到第一个 ## 之前的位置
    idx = existing.find("\n## ")
    if idx < 0:
        new_content = existing + "\n" + entry
    else:
        new_content = existing[:idx] + "\n" + entry + existing[idx:]

    with open(CHANGELOG_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)


def run_tests():
    """运行测试"""
    print("[1/5] 运行测试...")
    try:
        result = subprocess.run(
            [sys.executable, 'tests/run_all.py'],
            cwd=ROOT
        )
        if result.returncode != 0:
            print("[ERROR] 测试失败")
            return False
        return True
    except Exception as e:
        print("[ERROR] 测试失败: %s" % e)
        return False


def build():
    """构建"""
    print("[2/5] 构建发布包...")
    try:
        result = subprocess.run(
            [sys.executable, 'build.py'],
            cwd=ROOT
        )
        return result.returncode == 0
    except Exception as e:
        print("[ERROR] 构建失败: %s" % e)
        return False


def create_release_zip(version):
    """创建发布 zip"""
    print("[3/5] 创建发布包...")

    dist_dir = os.path.join(ROOT, 'dist', 'QingCaoEditor')
    if not os.path.isdir(dist_dir):
        print("[ERROR] 找不到构建输出: %s" % dist_dir)
        return None

    release_name = "QingCaoEditor_v%s_windows_x64" % version
    release_zip = os.path.join(ROOT, 'dist', release_name + '.zip')

    try:
        shutil.make_archive(
            release_zip[:-4],  # 去掉 .zip
            'zip',
            os.path.dirname(dist_dir),
            os.path.basename(dist_dir),
        )
        print("[OK] 发布包: %s" % release_zip)
        return release_zip
    except Exception as e:
        print("[ERROR] 创建 zip 失败: %s" % e)
        return None


def create_github_release(version, release_zip, notes):
    """创建 GitHub Release（需要 gh CLI）"""
    print("[4/5] 创建 GitHub Release...")

    if not shutil.which('gh'):
        print("[WARN] gh CLI 未安装，跳过自动上传")
        print("  手动上传: %s" % release_zip)
        return False

    tag = "v" + version

    try:
        # 创建 tag
        subprocess.run(
            ['git', 'tag', '-a', tag, '-m', "Release " + tag],
            cwd=ROOT, check=True
        )
        subprocess.run(
            ['git', 'push', 'origin', tag],
            cwd=ROOT, check=True
        )

        # 创建 release
        cmd = [
            'gh', 'release', 'create', tag,
            release_zip,
            '--title', "QingCao Editor v" + version,
            '--notes', notes,
        ]
        result = subprocess.run(cmd, cwd=ROOT)
        return result.returncode == 0
    except Exception as e:
        print("[ERROR] GitHub Release 失败: %s" % e)
        return False


def main():
    if len(sys.argv) < 2:
        print("用法: python release.py <command>")
        print()
        print("命令:")
        print("  version         显示当前版本")
        print("  bump <part>     升级版本 (major/minor/patch)")
        print("  build           只构建")
        print("  release <part>  完整发布流程")
        return 1

    cmd = sys.argv[1]
    current = read_version()

    if cmd == 'version':
        print("当前版本: v%s" % current)
        return 0

    if cmd == 'bump':
        part = sys.argv[2] if len(sys.argv) > 2 else 'patch'
        new_version = bump_version(current, part)
        write_version(new_version)
        print("版本升级: %s -> %s" % (current, new_version))
        return 0

    if cmd == 'build':
        if not build():
            return 1
        print("[OK] 构建完成")
        return 0

    if cmd == 'release':
        part = sys.argv[2] if len(sys.argv) > 2 else 'patch'
        new_version = bump_version(current, part)

        print("=" * 60)
        print("发布流程: %s -> %s" % (current, new_version))
        print("=" * 60)

        # 1. 测试
        if not run_tests():
            return 1

        # 2. 更新版本
        write_version(new_version)
        print("[OK] 版本更新: %s" % new_version)

        # 3. 更新 CHANGELOG
        changes = []
        print("请输入本次变更（每行一条，空行结束）:")
        while True:
            line = input("> ").strip()
            if not line:
                break
            changes.append(line)
        if changes:
            update_changelog(new_version, changes)
            print("[OK] CHANGELOG 已更新")

        # 4. 构建
        if not build():
            return 1

        # 5. 打包
        release_zip = create_release_zip(new_version)
        if not release_zip:
            return 1

        # 6. 上传
        notes = "\n".join("- " + c for c in changes) or "更新发布"
        create_github_release(new_version, release_zip, notes)

        print()
        print("=" * 60)
        print("发布完成: v%s" % new_version)
        print("=" * 60)
        return 0

    print("未知命令: %s" % cmd)
    return 1


if __name__ == "__main__":
    sys.exit(main())