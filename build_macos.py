#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""macOS 打包（.app + .dmg）"""
import os
import plistlib
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
# P1-1: 版本号唯一来源 version.py
try:
    from version import __version__ as VERSION
except ImportError:  # pragma: no cover
    # 发布准备时修复：原为硬编码 "2.1.0"（version.py 导入失败时静默
    # 产出过期版本）。改为读 VERSION 文件；两者都不可用则明确报错。
    import os as _os
    _vf = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                        "VERSION")
    try:
        with open(_vf, encoding="utf-8") as _f:
            VERSION = _f.read().strip()
    except OSError:
        VERSION = ""
    if not VERSION:
        raise SystemExit("无法确定版本号：version.py 与 VERSION 均不可用")
APP_NAME = "QingCaoEditor.app"


def create_app_bundle():
    """创建 .app 包"""
    app_dir = os.path.join(ROOT, 'dist', APP_NAME)

    # 目录结构
    contents = os.path.join(app_dir, 'Contents')
    macos = os.path.join(contents, 'MacOS')
    resources = os.path.join(contents, 'Resources')

    for d in [app_dir, contents, macos, resources]:
        os.makedirs(d, exist_ok=True)

    # 复制 PyInstaller 输出
    pyinstaller_output = os.path.join(
        ROOT, 'dist', 'QingCaoEditor'
    )
    if os.path.isdir(pyinstaller_output):
        for item in os.listdir(pyinstaller_output):
            src = os.path.join(pyinstaller_output, item)
            dst = os.path.join(macos, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy(src, dst)

    # Info.plist
    plist_data = {
        'CFBundleName': 'QingCao Editor',
        'CFBundleDisplayName': '青草编辑器',
        'CFBundleIdentifier': 'com.qingcao.editor',
        'CFBundleVersion': VERSION,
        'CFBundleShortVersionString': VERSION,
        'CFBundleExecutable': 'QingCaoEditor',
        'CFBundleIconFile': 'qingcao.icns',
        'CFBundlePackageType': 'APPL',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.14',
        'CFBundleDocumentTypes': [{
            'CFBundleTypeName': 'Text Document',
            'CFBundleTypeRole': 'Editor',
            'LSItemContentTypes': ['public.text', 'public.plain-text'],
        }],
    }

    with open(os.path.join(contents, 'Info.plist'), 'wb') as f:
        plistlib.dump(plist_data, f)

    return app_dir


def create_dmg(app_dir):
    """创建 .dmg 安装包"""
    if not shutil.which('create-dmg'):
        print("[WARN] create-dmg 未安装，跳过 .dmg 构建")
        print("  安装: brew install create-dmg")
        return None

    output = os.path.join(
        ROOT, 'installer',
        'QingCaoEditor_v%s.dmg' % VERSION
    )
    os.makedirs(os.path.dirname(output), exist_ok=True)

    cmd = [
        'create-dmg',
        '--volname', 'QingCao Editor',
        '--window-pos', '200', '120',
        '--window-size', '600', '400',
        '--icon-size', '100',
        '--app-drop-link', '450', '180',
        output,
        app_dir,
    ]

    result = subprocess.run(cmd)
    return output if result.returncode == 0 else None


def main():
    print("=" * 60)
    print("macOS 打包")
    print("=" * 60)

    app_dir = create_app_bundle()
    print("[OK] .app: " + app_dir)

    dmg = create_dmg(app_dir)
    if dmg:
        print("[OK] .dmg: " + dmg)

    return 0


if __name__ == "__main__":
    sys.exit(main())