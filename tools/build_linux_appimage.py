# -*- coding: utf-8 -*-
"""Linux AppImage 构建（v2.23 P1-3）。

在 Ubuntu CI 中运行：依赖 apt 的 PyQt5/QScintilla + pip 的 pyinstaller。
    python3 tools/build_linux_appimage.py
产物：dist/QingCaoEditor-x86_64.AppImage
"""

import os
import shutil
import subprocess
import sys
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
APPDIR = os.path.join(DIST, "AppDir")
APPIMAGE = os.path.join(DIST, "QingCaoEditor-x86_64.AppImage")
APPIMAGETOOL_URLS = [
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage",
    "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage",
]


def run(cmd, **kw):
    print("[linux-build]", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def make_icon(path):
    from PIL import Image, ImageDraw

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, size - 8, size - 8), radius=48, fill=(46, 160, 67, 255))
    d.rectangle((64, 96, 192, 120), fill=(255, 255, 255, 255))
    d.rectangle((64, 140, 160, 164), fill=(255, 255, 255, 255))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def build_pyinstaller():
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "QingCaoEditor",
        "--hidden-import",
        "PyQt5.Qsci",
        "--hidden-import",
        "PyQt5.QtNetwork",
        "--exclude-module",
        "winpty",
        "--exclude-module",
        "pywinpty",
        "--paths",
        ROOT,
        "--add-data",
        os.path.join(ROOT, "themes") + ":themes",
        "--add-data",
        os.path.join(ROOT, "plugins") + ":plugins",
        "--add-data",
        os.path.join(ROOT, "locale") + ":locale",
        "--add-data",
        os.path.join(ROOT, "docs") + ":docs",
        os.path.join(ROOT, "main.py"),
    ]
    run(args)


def make_appdir():
    if os.path.isdir(APPDIR):
        shutil.rmtree(APPDIR)
    bin_dir = os.path.join(APPDIR, "usr", "bin", "QingCaoEditor")
    os.makedirs(bin_dir, exist_ok=True)
    shutil.copytree(os.path.join(DIST, "QingCaoEditor"), bin_dir, dirs_exist_ok=True)
    apprun = os.path.join(APPDIR, "AppRun")
    with open(apprun, "w", encoding="utf-8", newline="\n") as f:
        f.write(
            '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
            'exec "$HERE/usr/bin/QingCaoEditor/QingCaoEditor" "$@"\n'
        )
    os.chmod(apprun, 0o755)
    desktop = os.path.join(APPDIR, "qingcao-editor.desktop")
    with open(desktop, "w", encoding="utf-8", newline="\n") as f:
        f.write(
            "[Desktop Entry]\nType=Application\nName=QingCao Editor\n"
            "Comment=QingCao Editor\nExec=QingCaoEditor\n"
            "Icon=qingcao-editor\nCategories=Development;TextEditor;\n"
            "Terminal=false\n"
        )
    icon_path = os.path.join(APPDIR, "qingcao-editor.png")
    make_icon(icon_path)
    os.makedirs(
        os.path.join(APPDIR, "usr", "share", "icons", "hicolor", "256x256", "apps"), exist_ok=True
    )
    shutil.copy2(
        icon_path,
        os.path.join(
            APPDIR, "usr", "share", "icons", "hicolor", "256x256", "apps", "qingcao-editor.png"
        ),
    )


def fetch_appimagetool():
    tool = os.path.join(DIST, "appimagetool")
    if os.path.isfile(tool) and os.access(tool, os.X_OK):
        return tool
    last = None
    for url in APPIMAGETOOL_URLS:
        try:
            print("[linux-build] 下载", url)
            urllib.request.urlretrieve(url, tool)
            os.chmod(tool, 0o755)
            return tool
        except Exception as e:  # pragma: no cover - 网络差异
            last = e
    raise RuntimeError("appimagetool 下载失败: %s" % last)


def build_appimage():
    tool = fetch_appimagetool()
    env = dict(os.environ)
    env["ARCH"] = "x86_64"
    run([tool, "--appimage-extract-and-run", APPDIR, APPIMAGE], env=env)
    print("[linux-build] 产物:", APPIMAGE)


def main():
    build_pyinstaller()
    make_appdir()
    build_appimage()
    return 0


if __name__ == "__main__":
    sys.exit(main())
