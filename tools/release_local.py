# -*- coding: utf-8 -*-
"""本地一键发布工具（不依赖 GitHub Actions / 网络）

用途：GitHub Actions 额度用尽或网络不稳时，在本地完成：
  1. 读取 VERSION（唯一版本源）
  2. 可选构建（python build.py），校验 exe FileVersion
  3. 打包 dist/QingCaoEditor-v<ver>-windows.zip + .sha256.txt
  4. 生成发布计划 JSON（资产、哈希、说明文件、网页上传清单）

用法：
    python tools/release_local.py                # 构建 + 打包 + 计划
    python tools/release_local.py --no-build     # 跳过构建（复用 dist）
    python tools/release_local.py --dry-run      # 只检查与打印计划
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
APP_DIR = os.path.join(DIST, "QingCaoEditor")


def get_version() -> str:
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def find_notes(version: str) -> str:
    path = os.path.join(ROOT, "docs", "release_notes_v%s.md" % version)
    if os.path.exists(path):
        return path
    return os.path.join(ROOT, "CHANGELOG.md")


def exe_path() -> str:
    return os.path.join(APP_DIR, "QingCaoEditor.exe")


def check_exe_version(version: str) -> str:
    """用 PowerShell 读取 exe FileVersion，返回发现值"""
    exe = exe_path()
    if not os.path.exists(exe):
        raise SystemExit("构建产物缺失: %s" % exe)
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Item '%s').VersionInfo.FileVersion" % exe],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60).stdout.strip()
        return out
    except Exception as e:
        print("[警告] 无法读取 FileVersion: %s" % e)
        return ""


def build() -> None:
    print("[1/4] 构建 (python build.py) ...")
    rc = subprocess.call([sys.executable, "build.py"], cwd=ROOT)
    if rc != 0:
        raise SystemExit("构建失败，退出码 %d" % rc)


def package(version: str):
    print("[2/4] 打包 ZIP + SHA256 ...")
    zip_path = os.path.join(DIST, "QingCaoEditor-v%s-windows.zip" % version)
    if not os.path.isdir(APP_DIR):
        raise SystemExit("缺少目录: %s" % APP_DIR)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(APP_DIR):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, APP_DIR)
                zf.write(full, rel)
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest().upper()
    sha_path = zip_path + ".sha256.txt"
    with open(sha_path, "w", encoding="ascii", newline="\n") as f:
        f.write("%s  %s\n" % (digest, os.path.basename(zip_path)))
    print("    ZIP: %s (%.2f MB)" % (zip_path, os.path.getsize(zip_path) / 1048576))
    print("    SHA256: %s" % digest)
    return zip_path, sha_path, digest


def make_plan(version, zip_path, sha_path, digest, notes):
    print("[3/4] 生成发布计划 ...")
    plan = {
        "version": version,
        "tag": "v%s" % version,
        "title": "青草编辑器 v%s" % version,
        "notes": os.path.relpath(notes, ROOT),
        "assets": [
            {"path": zip_path, "size": os.path.getsize(zip_path)},
            {"path": sha_path, "size": os.path.getsize(sha_path)},
        ],
        "sha256": digest,
        "steps": [
            "打开 GitHub → Releases → 选择 tag v%s" % version,
            "粘贴 %s 的全部内容作为 Release 正文"
            % os.path.relpath(notes, ROOT),
            "上传 %s 与 %s" % (os.path.basename(zip_path),
                              os.path.basename(sha_path)),
            "Publish release",
        ],
    }
    out = os.path.join(DIST, "release_plan_v%s.json" % version)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("    计划: %s" % out)
    return plan


def main():
    ap = argparse.ArgumentParser(description="本地一键发布")
    ap.add_argument("--no-build", action="store_true", help="跳过构建")
    ap.add_argument("--dry-run", action="store_true", help="只检查，不构建/打包")
    args = ap.parse_args()

    version = get_version()
    print("版本: %s" % version)
    notes = find_notes(version)
    print("发布说明: %s" % os.path.relpath(notes, ROOT))

    if args.dry_run:
        print("[dry-run] exe: %s 存在=%s"
              % (exe_path(), os.path.exists(exe_path())))
        print("  FileVersion: %s" % check_exe_version(version))
        print("[dry-run] 跳过构建与打包")
        return 0

    if not args.no_build:
        build()
        print("[检查] FileVersion: %s" % check_exe_version(version))
    else:
        print("[跳过构建] 复用 existing dist")
        print("[检查] FileVersion: %s" % check_exe_version(version))

    zip_path, sha_path, digest = package(version)
    plan = make_plan(version, zip_path, sha_path, digest, notes)
    print("[4/4] 完成。网页上传步骤：")
    for i, s in enumerate(plan["steps"], 1):
        print("    %d. %s" % (i, s))
    return 0


if __name__ == "__main__":
    sys.exit(main())