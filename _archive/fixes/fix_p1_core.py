#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - P1 核心层修复
============================
修复 4 项 P1 问题（安全 / 并发 / 资源）：

  A1  infrastructure/sandbox_runtime.py
      socket 被列入 INTERNAL_ALLOWED_MODULES → 插件绕过 network 权限。

  A2  infrastructure/plugin_sandbox.py
      start() 中主线程与接收线程同时 poll/recv 同一个 Pipe →
      消息被错误线程消费 / 丢消息 / 偶发崩溃。

  A3  infrastructure/plugin_updater.py
      _download_update 取消时直接 return，未关闭 requests 连接。

  A4  core/content_provider.py
      LocalFileProvider._save_dirty_blocks 未在写前释放 mmap →
      Windows 上 open('r+b') 因文件锁失败。

特性：
  - 幂等
  - 每项独立处理
  - 修改前备份 *.bak.p1core
  - Python 文件修改后 compile() 验证
  - A4 涉及多段替换，整体原子（一段失败则全部不写回）

用法：
    python fix_p1_core.py --dry-run
    python fix_p1_core.py
    python fix_p1_core.py --only A1,A4
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p1core"


# ============================================================
# 输出辅助
# ============================================================
def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 工具
# ============================================================
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


def apply_multi_replace(path: Path,
                        replacements: List[Tuple[str, str]],
                        markers: List[str],
                        no_backup: bool) -> str:
    """
    多项替换（原子）：
      - 所有 markers 只要有一个存在 → 视为"已修复"
      - 所有 old 必须唯一
      - 任一失败则不写回
    """
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    # 幂等：所有 marker 都出现则视为已修复
    if markers and all(m in content for m in markers):
        print_skip(f"{path.relative_to(ROOT)}: 已全部修复")
        return 'skipped'

    # 先检查所有锚点
    for i, (old, _) in enumerate(replacements):
        cnt = content.count(old)
        if cnt == 0:
            print_fail(
                f"{path.relative_to(ROOT)}: 第 {i+1} 段锚点未找到"
            )
            for line in old.split('\n')[:3]:
                print(f"      | {line}")
            return 'failed'
        if cnt > 1:
            print_fail(
                f"{path.relative_to(ROOT)}: 第 {i+1} 段锚点重复 {cnt} 次"
            )
            return 'failed'

    # 依次替换
    new_content = content
    for old, new in replacements:
        new_content = new_content.replace(old, new, 1)

    # 语法验证
    if path.suffix == '.py':
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"{path.relative_to(ROOT)}: 语法错误 ({err})")
            return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


def apply_replace(path: Path,
                  old: str, new: str,
                  marker: str,
                  no_backup: bool) -> str:
    return apply_multi_replace(
        path,
        [(old, new)],
        [marker] if marker else [],
        no_backup,
    )


# ============================================================
# A1: sandbox_runtime.py 移除 socket 白名单
# ============================================================
A1_MARKER = "【安全】socket 必须从白名单移除"

A1_OLD = """    # ---- 网络 setup（SafeFinder 自身需要 import socket）----
    'socket', '_socket',
}"""

A1_NEW = """    # 说明（P1-A1）：
    #   【安全】socket 必须从白名单移除。
    #   原因：SafeFinder.find_spec 对白名单模块直接放行（return None），
    #         不做 policy.can_import 检查。
    #   后果：无 network 权限的插件可以 import socket，
    #         再通过 socket.socket() + 硬编码 IP 直接连网，
    #         完全绕过沙箱策略。
    #
    #   沙箱自身需要 socket 时（install_sandbox_hooks 里给 socket
    #   装 getaddrinfo 拦截），走的是 _ORIGINAL_IMPORT('socket')，
    #   不经 sys.meta_path，因此不需要把它放进白名单。
}"""


def fix_a1(no_backup: bool) -> str:
    path = ROOT / "infrastructure" / "sandbox_runtime.py"
    return apply_replace(path, A1_OLD, A1_NEW,
                         marker=A1_MARKER,
                         no_backup=no_backup)


# ============================================================
# A2: plugin_sandbox.py Pipe 竞争
# ============================================================
A2_MARKER_1 = "self._ready_event = threading.Event()"
A2_MARKER_2 = "msg_type == MSG_TYPE_READY"
A2_MARKER_3 = "A2 已废弃主线程抢读"

# 段 1: start() 中改用 Event
A2_OLD_1 = """                # 启动接收线程
                self._stop_receiver.clear()
                self._receiver_thread = threading.Thread(
                    target=self._receiver_loop,
                    daemon=True,
                    name=f"sandbox_recv_{self.config.name}",
                )
                self._receiver_thread.start()

                # 等待就绪信号
                ready = self._wait_for_ready(timeout=10)

                if ready:"""

A2_NEW_1 = """                # 启动接收线程（唯一读 Pipe 的线程）
                self._stop_receiver.clear()

                # P1-A2: 用 Event 代替主线程直接 poll/recv
                self._ready_event = threading.Event()
                self._ready_ok = False

                self._receiver_thread = threading.Thread(
                    target=self._receiver_loop,
                    daemon=True,
                    name=f"sandbox_recv_{self.config.name}",
                )
                self._receiver_thread.start()

                # 主线程只等 Event（不碰 Pipe）
                got = self._ready_event.wait(timeout=10)
                ready = got and self._ready_ok

                if ready:"""

# 段 2: _handle_message 增加 READY 分支
A2_OLD_2 = """        elif msg_type == MSG_TYPE_PONG:
            self._last_pong = time.time()"""

A2_NEW_2 = """        elif msg_type == MSG_TYPE_READY:
            # P1-A2: 就绪信号由接收线程处理，通知主线程
            self._ready_ok = bool(message.get('success', False))
            self._ready_event.set()

        elif msg_type == MSG_TYPE_PONG:
            self._last_pong = time.time()"""

# 段 3: _wait_for_ready 改为 no-op（保留方法名兼容）
A2_OLD_3 = """    def _wait_for_ready(self, timeout: float = 10) -> bool:
        \"\"\"等待就绪信号\"\"\"
        start = time.time()

        while time.time() - start < timeout:
            if not self.is_alive:
                return False

            try:
                if self._parent_conn.poll(0.1):
                    message = self._parent_conn.recv()
                    if message and message.get('type') == MSG_TYPE_READY:
                        return message.get('success', False)
            except Exception:
                pass

        return False"""

A2_NEW_3 = """    def _wait_for_ready(self, timeout: float = 10) -> bool:
        \"\"\"A2 已废弃主线程抢读。

        P1-A2 修复说明：
            原实现让主线程直接 poll/recv Pipe，与 _receiver_loop
            线程竞争，导致：
              1. 消息可能被错误线程消费（multiprocessing.Connection
                 不是线程安全的）
              2. 主线程吞掉 LOG 等其他消息
              3. 停止时接收线程访问已关闭的连接 → OSError

            现改为：只有 _receiver_loop 读 Pipe，主线程通过
            self._ready_event（threading.Event）等待。

            本方法保留为兼容入口（外部可能调用），直接等 Event。
        \"\"\"
        if not hasattr(self, '_ready_event') or self._ready_event is None:
            return False
        got = self._ready_event.wait(timeout=timeout)
        return got and getattr(self, '_ready_ok', False)"""


def fix_a2(no_backup: bool) -> str:
    path = ROOT / "infrastructure" / "plugin_sandbox.py"

    # 幂等：如果所有新内容都在，则跳过
    if path.exists():
        try:
            content = path.read_text(encoding='utf-8')
            if (A2_MARKER_1 in content
                    and "self._ready_ok = bool(message.get('success', False))" in content
                    and A2_MARKER_3 in content):
                print_skip("plugin_sandbox.py: 已全部修复")
                return 'skipped'
        except Exception:
            pass

    return apply_multi_replace(
        path,
        [
            (A2_OLD_1, A2_NEW_1),
            (A2_OLD_2, A2_NEW_2),
            (A2_OLD_3, A2_NEW_3),
        ],
        markers=[],
        no_backup=no_backup,
    )


# ============================================================
# A3: plugin_updater.py 取消时关闭连接
# ============================================================
A3_MARKER = "A3 修复：用 try/finally 保证 resp.close()"

A3_OLD = """        for attempt in range(MAX_RETRIES):
            if self._cancelled:
                return None

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

                return b''.join(chunks)"""

A3_NEW = """        for attempt in range(MAX_RETRIES):
            if self._cancelled:
                return None

            resp = None
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
                        # A3 修复：cancel 时也要 close（由 finally 处理）
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

            finally:
                # A3 修复：用 try/finally 保证 resp.close()
                # 原实现 cancel 时直接 return，导致请求连接泄漏。
                if resp is not None:
                    try:
                        resp.close()
                    except Exception:
                        pass"""


def fix_a3(no_backup: bool) -> str:
    path = ROOT / "infrastructure" / "plugin_updater.py"
    return apply_replace(path, A3_OLD, A3_NEW,
                         marker=A3_MARKER,
                         no_backup=no_backup)


# ============================================================
# A4: content_provider.py 释放 mmap
# ============================================================
A4_MARKER = "A4 修复：先释放 mmap 再开文件"

A4_OLD = """    def _save_dirty_blocks(self, target: str) -> bool:
        \"\"\"仅写入脏块（原地更新）\"\"\"
        # 关闭 mmap 以释放文件锁
        if self._mmap:
            try:
                self._mmap.flush()
            except Exception:
                pass

        try:
            # 使用可写文件句柄
            with open(target, 'r+b') as f:
                for block_id, data in self._dirty_blocks.items():
                    offset = block_id * self._block_size
                    f.seek(offset)
                    f.write(bytes(data))
                f.flush()
                os.fsync(f.fileno())

            # 更新状态
            self._dirty_blocks.clear()
            self._state = (FileState.READONLY if self._readonly
                           else FileState.OPENED)

            # 刷新 mmap
            if self._mmap:
                try:
                    self._mmap.flush()
                except Exception:
                    pass

            # 更新 mtime
            try:
                self._mtime = os.path.getmtime(target)
                self._size = os.path.getsize(target)
            except Exception:
                pass

            return True

        except Exception as e:
            print(f"[LocalFileProvider] 脏块保存失败: {e}")
            return False"""

A4_NEW = """    def _save_dirty_blocks(self, target: str) -> bool:
        \"\"\"仅写入脏块（原地更新）。

        A4 修复：先释放 mmap 再开文件。

        原实现在写完脏块后才 mmap.flush()，但在写入过程中
        mmap 仍持有文件映射。Windows 上 open('r+b') 会因
        文件被 mmap 锁定而抛 PermissionError。Linux/macOS
        允许，但 flush 语义也不可靠。

        修复流程：
            1. 先 mmap.flush() + mmap.close()，释放文件锁
            2. open('r+b') 写脏块
            3. 重新建立 mmap（保持 provider 可读）
        \"\"\"
        # ---- 1. 释放 mmap ----
        if self._mmap:
            try:
                self._mmap.flush()
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None

        # ---- 2. 写脏块 ----
        try:
            # 使用可写文件句柄
            with open(target, 'r+b') as f:
                for block_id, data in self._dirty_blocks.items():
                    offset = block_id * self._block_size
                    f.seek(offset)
                    f.write(bytes(data))
                f.flush()
                os.fsync(f.fileno())

            # 更新状态
            self._dirty_blocks.clear()
            self._state = (FileState.READONLY if self._readonly
                           else FileState.OPENED)

            # 更新 mtime / size
            try:
                self._mtime = os.path.getmtime(target)
                self._size = os.path.getsize(target)
            except Exception:
                pass

            # ---- 3. 重建 mmap ----
            self._reopen_mmap()

            return True

        except Exception as e:
            print(f"[LocalFileProvider] 脏块保存失败: {e}")
            # 失败时也要尽量恢复 mmap 状态
            self._reopen_mmap()
            return False

    def _reopen_mmap(self):
        \"\"\"重建 mmap（A4 新增，供 _save_dirty_blocks 内部调用）。

        在关闭 mmap 写盘后调用，保持 provider 后续读操作可用。
        \"\"\"
        if not self._file:
            return
        if self._size <= 0:
            return
        try:
            access = (mmap.ACCESS_READ if self._readonly
                      else mmap.ACCESS_WRITE)
            self._mmap = mmap.mmap(
                self._file.fileno(), 0, access=access
            )
        except (ValueError, OSError):
            self._mmap = None"""


def fix_a4(no_backup: bool) -> str:
    path = ROOT / "core" / "content_provider.py"
    return apply_replace(path, A4_OLD, A4_NEW,
                         marker=A4_MARKER,
                         no_backup=no_backup)


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("A1", "sandbox_runtime.py 移除 socket 白名单", fix_a1),
    ("A2", "plugin_sandbox.py 修 Pipe 竞争", fix_a2),
    ("A3", "plugin_updater.py 修取消泄漏", fix_a3),
    ("A4", "content_provider.py 释放 mmap 再写", fix_a4),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="青草编辑器 P1 核心层修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：A1,A2,...')
    args = parser.parse_args()

    print_header("青草编辑器 P1 核心层修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    fixes = FIXES
    if args.only:
        only = {x.strip().upper() for x in args.only.split(',')}
        fixes = [f for f in fixes if f[0] in only]

    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 将处理 {len(fixes)} 项：")
        for pid, name, _ in fixes:
            print_info(f"  {pid}: {name}")
        print()
        print("  去掉 --dry-run 即可应用。")
        return 0

    results = []
    for pid, name, fn in fixes:
        print_header(f"{pid}: {name}")
        r = fn(args.no_backup)
        results.append((pid, name, r))

    # 汇总
    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)

    applied = skipped = failed = 0
    for pid, name, r in results:
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: {name} [{r}]")
        if r == 'applied':
            applied += 1
        elif r == 'skipped':
            skipped += 1
        else:
            failed += 1

    print()
    if failed > 0:
        print("=" * 60)
        print(f"✗ 有 {failed} 项失败，请检查上方输出")
        print("=" * 60)
        return 1

    print("=" * 60)
    print(f"✓ 完成（应用 {applied} 项，跳过 {skipped} 项）")
    print("=" * 60)
    print()
    print("验证步骤:")
    print("  1. 语法验证:")
    print("     python -c \"import ast; "
          "[ast.parse(open(f, encoding='utf-8').read()) "
          "for f in ['infrastructure/sandbox_runtime.py', "
          "'infrastructure/plugin_sandbox.py', "
          "'infrastructure/plugin_updater.py', "
          "'core/content_provider.py']]; print('OK')\"")
    print("  2. 沙箱自测:")
    print("     python infrastructure/sandbox_runtime.py")
    print("  3. 手动验证 A1:")
    print("     在无 network 权限的插件里 import socket，应被拒绝")
    print("  4. 手动验证 A4:")
    print("     打开文件 → 编辑 → 保存 → 应成功")
    print()
    print("清理备份:")
    print("  Windows:     del /s *.bak.p1core")
    print("  Linux/macOS: find . -name '*.bak.p1core' -delete")

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