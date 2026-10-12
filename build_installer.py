#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建 Windows 安装程序"""
import os
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
ISS_FILE = os.path.join(ROOT, 'installer.iss')
VERSION_ISS_FILE = os.path.join(ROOT, 'installer_version.iss')


def generate_version_iss() -> bool:
    """C4 修复：生成 installer_version.iss，供 installer.iss #include"""
    try:
        # P1-1: 版本号唯一来源 version.py
        try:
            from version import __version__
        except ImportError:  # pragma: no cover
            __version__ = "2.1.0"

        content = (
            '; 此文件由 build_installer.py 自动生成，请勿手动编辑\n'
            f'#define MyAppVersion "{__version__}"\n'
        )
        with open(VERSION_ISS_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[OK] 版本文件: installer_version.iss (v%s)" % __version__)
        return True
    except Exception as e:
        print("[WARN] 生成版本文件失败: %s" % e)
        return False


def find_inno_setup():
    """查找 Inno Setup 编译程序"""
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # 检查 PATH
    found = shutil.which('iscc')
    if found:
        return found
    return None


def main():
    print("=" * 60)
    print("青草编辑器 - 安装包构建")
    print("=" * 60)

    # 1. 检查 Inno Setup
    iscc = find_inno_setup()
    if not iscc:
        print("[ERROR] 未找到 Inno Setup")
        print()
        print("请从以下地址下载并安装:")
        print("  https://jrsoftware.org/isdl.php")
        print()
        print("或使用 chocolatey:")
        print("  choco install innosetup")
        return 1

    print("[OK] Inno Setup: " + iscc)

    # 2. 检查 dist
    dist = os.path.join(ROOT, 'dist', 'QingCaoEditor')
    if not os.path.isdir(dist):
        print("[ERROR] 未找到构建输出: " + dist)
        print("请先运行: python build.py")
        return 1

    print("[OK] 构建输出: " + dist)

    # 3. 检查图标
    icon = os.path.join(ROOT, 'resources', 'icons', 'qingcao.ico')
    if not os.path.exists(icon):
        print("[WARN] 图标不存在: " + icon)

    # 4. 生成版本文件（C4 修复）
    generate_version_iss()

    # 5. 运行 Inno Setup 编译
    print()
    print("[RUN] 编译安装包...")
    cmd = [iscc, ISS_FILE]

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("[ERROR] 编译失败")
        return result.returncode

    # 5. 显示结果
    installer_dir = os.path.join(ROOT, 'installer')
    if os.path.isdir(installer_dir):
        files = [f for f in os.listdir(installer_dir)
                 if f.endswith('.exe')]
        if files:
            latest = max(
                [os.path.join(installer_dir, f) for f in files],
                key=os.path.getmtime
            )
            size_mb = os.path.getsize(latest) / 1024 / 1024
            print()
            print("=" * 60)
            print("[OK] 安装包构建成功！")
            print("  文件: " + latest)
            print("  大小: %.1f MB" % size_mb)
            print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())