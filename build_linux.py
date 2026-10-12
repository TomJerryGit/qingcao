#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Linux 打包"""
import os
import shutil
import subprocess
import sys
import tarfile


ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, 'dist', 'QingCaoEditor')
# P1-1: 版本号唯一来源 version.py
try:
    from version import __version__ as VERSION
except ImportError:  # pragma: no cover
    VERSION = "2.1.0"


def create_desktop_file():
    """创建 .desktop 文件"""
    content = """[Desktop Entry]
Type=Application
Name=QingCao Editor
Name[zh_CN]=青草编辑器
Comment=Lightweight text editor
Comment[zh_CN]=轻量级文本编辑器
Exec=/opt/qingcao-editor/qingcao-editor %F
Icon=/opt/qingcao-editor/qingcao.png
Terminal=false
Categories=Utility;TextEditor;Development;
MimeType=text/plain;text/x-python;
StartupWMClass=QingCaoEditor
"""
    with open(os.path.join(DIST, 'qingcao-editor.desktop'),
              'w', encoding='utf-8') as f:
        f.write(content)


def create_tarball():
    """创建 tar.gz 包"""
    output = os.path.join(
        ROOT, 'installer',
        'QingCaoEditor_v%s_linux_x64.tar.gz' % VERSION
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)

    with tarfile.open(output, 'w:gz') as tar:
        tar.add(DIST, arcname='qingcao-editor')

    return output


def create_deb_package():
    """创建 .deb 包（需要 dpkg-deb）"""
    if not shutil.which('dpkg-deb'):
        print("[WARN] dpkg-deb 未安装，跳过 .deb 构建")
        return None

    pkg_root = os.path.join(ROOT, 'installer', 'deb_root')
    if os.path.exists(pkg_root):
        shutil.rmtree(pkg_root)

    # DEBIAN/control
    control_dir = os.path.join(pkg_root, 'DEBIAN')
    os.makedirs(control_dir, exist_ok=True)

    with open(os.path.join(control_dir, 'control'),
              'w', encoding='utf-8') as f:
        f.write("""Package: qingcao-editor
Version: %s
Section: editors
Priority: optional
Architecture: amd64
Depends: libc6 (>= 2.31), libglib2.0-0, libgl1
Maintainer: hedongwei <1265338136@qq.com>
Description: Lightweight text editor with LSP and plugin system
 青草编辑器 - 轻量、极速、可扩展的代码编辑器
""" % VERSION)

    # 安装文件
    app_dir = os.path.join(pkg_root, 'opt', 'qingcao-editor')
    shutil.copytree(DIST, app_dir)

    # .desktop
    desktop_dir = os.path.join(pkg_root, 'usr', 'share', 'applications')
    os.makedirs(desktop_dir, exist_ok=True)
    shutil.copy(
        os.path.join(DIST, 'qingcao-editor.desktop'),
        desktop_dir
    )

    # 构建 .deb
    output = os.path.join(
        ROOT, 'installer',
        'qingcao-editor_%s_amd64.deb' % VERSION
    )
    subprocess.run(['dpkg-deb', '--build', pkg_root, output])
    return output


def main():
    print("=" * 60)
    print("Linux 打包")
    print("=" * 60)

    if not os.path.isdir(DIST):
        print("[ERROR] 请先运行 python build.py")
        return 1

    create_desktop_file()
    print("[OK] .desktop 文件已创建")

    tarball = create_tarball()
    print("[OK] tar.gz: " + tarball)

    deb = create_deb_package()
    if deb:
        print("[OK] .deb: " + deb)

    return 0


if __name__ == "__main__":
    sys.exit(main())