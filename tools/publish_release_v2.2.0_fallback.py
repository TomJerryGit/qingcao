# -*- coding: utf-8 -*-
"""v2.2.0 Release 兜底发布（本地已验证 ZIP）

用法（在已 `gh auth login` 的终端里）：
    python tools/publish_release_v2.2.0_fallback.py            # 发布
    python tools/publish_release_v2.2.0_fallback.py --dry-run  # 只检查

行为：
1. 校验本地 ZIP / SHA256 / tag / gh 认证；
2. Release 已存在 → `gh release upload --clobber`；
   Release 不存在 → `gh release create v2.2.0 --verify-tag`；
3. 上传后 `gh release view` 复核资产。

为什么用它而不是 CI：v2.2.0 的 tag 已推送，但私有仓库 Actions 结果
无法在未认证环境确认；本脚本上传的是**本地已真实桌面冒烟验证过**的包。
"""
import argparse
import hashlib
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = r"D:\Programs\gh\bin\gh.exe"
REPO = "TomJerryGit/qingcao"
TAG = "v2.2.0"
ZIP = os.path.join(ROOT, "dist", "QingCaoEditor_v2.2.0_windows_x64.zip")
SHA_FILE = ZIP + ".sha256.txt"


def run(cmd, check=False, capture=True):
    print("  $ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=capture, text=True,
                       encoding="utf-8", errors="replace",
                       cwd=ROOT)
    if capture and r.stdout:
        for line in r.stdout.strip().splitlines()[:8]:
            print("    " + line)
    if capture and r.stderr.strip():
        for line in r.stderr.strip().splitlines()[:5]:
            print("    ! " + line)
    if check and r.returncode != 0:
        raise SystemExit("命令失败 (exit %d)" % r.returncode)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=== 1. 本地产物校验 ===")
    if not os.path.isfile(ZIP):
        raise SystemExit("缺少 ZIP: %s" % ZIP)
    size_mb = os.path.getsize(ZIP) / 1024 / 1024
    h = hashlib.sha256(open(ZIP, "rb").read()).hexdigest().upper()
    print("  ZIP: %.2f MB" % size_mb)
    print("  SHA256: %s" % h)
    if os.path.isfile(SHA_FILE):
        recorded = open(SHA_FILE, encoding="ascii").read().split()[0].upper()
        print("  记录值一致: %s" % (recorded == h))
        if recorded != h:
            raise SystemExit("SHA256 与记录不一致，拒绝上传")

    print("=== 2. gh 认证 / Release 状态 ===")
    auth = subprocess.run([GH, "auth", "status"], capture_output=True,
                          text=True)
    if auth.returncode != 0:
        raise SystemExit(
            "gh 未登录。请先运行： gh auth login\n"
            "（或设置 GH_TOKEN 后重试）")
    print("  gh 已认证")

    view = subprocess.run([GH, "release", "view", TAG, "-R", REPO],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    exists = view.returncode == 0
    print("  Release %s 已存在: %s" % (TAG, exists))
    if exists:
        print(view.stdout[:600])

    if args.dry_run:
        print("\n[dry-run] 不执行上传。")
        return

    files = [ZIP]
    if os.path.isfile(SHA_FILE):
        files.append(SHA_FILE)

    if exists:
        print("=== 3. 追加/覆盖资产 ===")
        run([GH, "release", "upload", TAG] + files + ["--clobber"],
            check=True)
    else:
        print("=== 3. 创建 Release 并上传 ===")
        notes = os.path.join(ROOT, "docs", "release_notes_v2.2.0.md")
        cmd = [GH, "release", "create", TAG, "-R", REPO,
               "--verify-tag",
               "--title", "青草编辑器 v2.2.0",
               "--notes-file", notes] + files
        run(cmd, check=True)

    print("=== 4. 复核 ===")
    run([GH, "release", "view", TAG, "-R", REPO])
    print("\n完成：https://github.com/%s/releases/tag/%s" % (REPO, TAG))


if __name__ == "__main__":
    main()
