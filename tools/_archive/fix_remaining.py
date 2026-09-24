#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 剩余修复
========================
修复 3 项：

  R1  plugin_updater.py 的 A3 修复（重做）
      上次 fix_p1_core.py 的 A3 只替换到 return 处，
      没包含 except 分支，导致 finally 后出现孤儿 except。
      本次用完整 try/except/finally 结构重写。

  R2  requirements-dev.txt 的 C8 修复（重做）
      文件有 UTF-8 BOM，utf-8 无法解码。
      改用 utf-8-sig 读取。

  R3  .gitignore 补 *.bak.* 规则
      避免修复脚本产生的备份文件再次被提交。

用法：
    python fix_remaining.py --dry-run
    python fix_remaining.py
"""

import re
import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.remaining"


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


def read_text_smart(path: Path) -> str:
    """自动处理 BOM / 编码。"""
    # 先探测 BOM
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    if raw.startswith(b'\xef\xbb\xbf'):
        try:
            return raw.decode('utf-8-sig')
        except Exception:
            pass
    for enc in ('utf-8', 'gbk', 'latin-1'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode('utf-8', errors='replace')


def backup(path: Path) -> bool:
    bak = Path(str(path) + BACKUP_SUFFIX)
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        print_info(f"已备份: {bak.name}")
        return True
    except Exception as e:
        print_fail(f"备份失败: {e}")
        return False


def write_back(path: Path, content: str, no_backup: bool) -> bool:
    if not no_backup and not backup(path):
        return False
    try:
        # 写回时统一用 UTF-8（无 BOM）
        path.write_text(content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败: {e}")
        return False


def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


# ============================================================
# R1: plugin_updater.py A3 重做
# ============================================================
R1_MARKER = "# R1 修复：finally 保证 resp 关闭"

R1_OLD = '''            try:
                import requests
                resp = requests.get(
                    url, timeout=DOWNLOAD_TIMEOUT, stream=True
                )

                if resp.status_code != 200:
                    print(f"[PluginUpdater] 下载失败: HTTP {resp.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None

                # 获取总大小
                total_size = int(resp.headers.get('content-length', 0))

                # 流式下载
                chunks = []
                downloaded = 0

                for chunk in resp.iter_content(chunk_size=8192):
                    if self._cancelled:
                        return None

                    chunks.append(chunk)
                    downloaded += len(chunk)

                    if total_size > 0 and progress_callback:
                        pct = 5 + int((downloaded / total_size) * 50)
                        progress_callback(
                            pct,
                            f"下载中 {downloaded // 1024}/{total_size // 1024} KB"
                        )

                return b''.join(chunks)

            except ImportError:
                # urllib 回退
                try:
                    import urllib.request
                    with urllib.request.urlopen(
                        url, timeout=DOWNLOAD_TIMEOUT
                    ) as f:
                        return f.read()
                except Exception as e:
                    print(f"[PluginUpdater] urllib 下载失败: {e}")
            except Exception as e:
                print(f"[PluginUpdater] 下载异常: {e}")'''

R1_NEW = '''            resp = None
            try:
                import requests
                resp = requests.get(
                    url, timeout=DOWNLOAD_TIMEOUT, stream=True
                )

                if resp.status_code != 200:
                    print(f"[PluginUpdater] 下载失败: HTTP {resp.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None

                # 获取总大小
                total_size = int(resp.headers.get('content-length', 0))

                # 流式下载
                chunks = []
                downloaded = 0

                for chunk in resp.iter_content(chunk_size=8192):
                    if self._cancelled:
                        return None

                    chunks.append(chunk)
                    downloaded += len(chunk)

                    if total_size > 0 and progress_callback:
                        pct = 5 + int((downloaded / total_size) * 50)
                        progress_callback(
                            pct,
                            f"下载中 {downloaded // 1024}/{total_size // 1024} KB"
                        )

                return b''.join(chunks)

            except ImportError:
                # urllib 回退
                try:
                    import urllib.request
                    with urllib.request.urlopen(
                        url, timeout=DOWNLOAD_TIMEOUT
                    ) as f:
                        return f.read()
                except Exception as e:
                    print(f"[PluginUpdater] urllib 下载失败: {e}")
            except Exception as e:
                print(f"[PluginUpdater] 下载异常: {e}")
            finally:
                # R1 修复：finally 保证 resp 关闭
                # 原 A3 修复只替换到 return 处，未包含 except 分支，
                # 导致 finally 后出现孤儿 except。
                if resp is not None:
                    try:
                        resp.close()
                    except Exception:
                        pass'''


def fix_r1(no_backup: bool) -> str:
    path = ROOT / "infrastructure" / "plugin_updater.py"
    if not path.exists():
        print_fail("plugin_updater.py 不存在")
        return 'failed'

    content = read_text_smart(path)

    # 幂等
    if R1_MARKER in content:
        print_skip("R1 已修复")
        return 'skipped'

    cnt = content.count(R1_OLD)
    if cnt == 0:
        print_fail("R1 锚点未找到")
        print_info("可能 A3 已部分应用或文件已改动")
        return 'failed'
    if cnt > 1:
        print_fail(f"R1 锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(R1_OLD, R1_NEW, 1)

    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"R1 语法错误: {err}")
        return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok("R1 plugin_updater.py 已修复")
    return 'applied'


# ============================================================
# R2: requirements-dev.txt C8 重做
# ============================================================
R2_MARKER = "# R2 修复：mkdocs 已补齐"


def fix_r2(no_backup: bool) -> str:
    path = ROOT / "requirements-dev.txt"
    if not path.exists():
        print_fail("requirements-dev.txt 不存在")
        return 'failed'

    content = read_text_smart(path)
    if not content:
        print_fail("文件内容为空")
        return 'failed'

    # 幂等
    if 'mkdocs' in content and R2_MARKER in content:
        print_skip("R2 已修复")
        return 'skipped'

    if 'mkdocs' in content:
        # 有 mkdocs，加 marker 即可
        new_content = content.rstrip() + "\n\n" + R2_MARKER + "\n"
    else:
        # 追加 mkdocs 段
        addition = (
            "\n\n"
            "# " + R2_MARKER.strip("# ") + "\n"
            "mkdocs>=1.5.0\n"
            "mkdocs-material>=9.0.0\n"
        )
        new_content = content.rstrip() + addition

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok("R2 requirements-dev.txt 已修复（BOM 已清理）")
    return 'applied'


# ============================================================
# R3: .gitignore 补 *.bak.*
# ============================================================
R3_MARKER = "# R3 修复：忽略所有 *.bak.* 备份"

R3_ADDITIONS = [
    "",
    "# R3 修复：忽略所有 *.bak.* 备份",
    "*.bak.*",
    "*.bak",
    "*.tmp",
]


def fix_r3(no_backup: bool) -> str:
    path = ROOT / ".gitignore"
    if not path.exists():
        print_fail(".gitignore 不存在")
        return 'failed'

    content = read_text_smart(path)

    if R3_MARKER in content or "*.bak.*" in content:
        print_skip("R3 已修复")
        return 'skipped'

    if not content.endswith('\n'):
        content += '\n'
    content += '\n'.join(R3_ADDITIONS) + '\n'

    if not write_back(path, content, no_backup):
        return 'failed'

    print_ok("R3 .gitignore 已补 *.bak.* 规则")
    return 'applied'


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("R1", "plugin_updater.py A3 重做", fix_r1),
    ("R2", "requirements-dev.txt C8 重做", fix_r2),
    ("R3", ".gitignore 补 *.bak.*", fix_r3),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="青草编辑器剩余修复")
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='')
    args = parser.parse_args()

    print_header("青草编辑器剩余修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    fixes = FIXES
    if args.only:
        only = {x.strip().upper() for x in args.only.split(',')}
        fixes = [f for f in fixes if f[0] in only]

    if args.dry_run:
        print_info(f"[DRY-RUN] 将处理 {len(fixes)} 项：")
        for pid, name, _ in fixes:
            print_info(f"  {pid}: {name}")
        return 0

    results = []
    for pid, name, fn in fixes:
        print_header(f"{pid}: {name}")
        r = fn(args.no_backup)
        results.append((pid, name, r))

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    applied = skipped = failed = 0
    for pid, name, r in results:
        mark = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {mark} {pid}: {name} [{r}]")
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    print()
    if failed:
        print(f"✗ {failed} 项失败")
        return 1
    print(f"✓ 完成（应用 {applied} 项，跳过 {skipped} 项）")
    print()
    print("验证：")
    print("  python -c \"import ast; ast.parse(open('infrastructure/plugin_updater.py', encoding='utf-8').read()); print('OK')\"")
    print("  pip install -r requirements-dev.txt --dry-run")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)