#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
剩余 P2/P3 项批量修复
========================
修复 5 项：

  P2-1  outline_panel: 硬编码 50000 → large_file_threshold 偏好
  P2-3  theme_loader: Lexer 颜色按语言分派
  P3-2  command_palette: 使用历史 key 用 action_name
  P3-3  sandbox_policy: DANGEROUS_MODULES 精简
  P3-4  editor.py: LSP 位置转换用字节偏移

特性:
  - 幂等
  - 每项独立处理
  - 修改前备份 *.bak.p3
  - 修改后 compile() 验证

用法:
    python fix_batch_p3.py --dry-run
    python fix_batch_p3.py
    python fix_batch_p3.py --only P2-1,P3-4
    python fix_batch_p3.py --no-backup
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p3"


# ============================================================
# 输出
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


def apply_multi(path: Path,
                sections: List[Tuple[str, str, str]],
                no_backup: bool) -> str:
    """多段原子替换。sections: [(marker, old, new), ...]"""
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    # 幂等：所有 marker 都命中 → 已修复
    if all(m in content for m, _, _ in sections):
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    new_content = content
    for i, (marker, old, new) in enumerate(sections, 1):
        if marker in new_content:
            print_info(f"  段 {i}: 已应用，跳过")
            continue
        cnt = new_content.count(old)
        if cnt == 0:
            print_fail(f"  段 {i}: 锚点未找到")
            for line in old.split('\n')[:3]:
                print(f"      | {line}")
            return 'failed'
        if cnt > 1:
            print_fail(f"  段 {i}: 锚点重复 {cnt} 次")
            return 'failed'
        new_content = new_content.replace(old, new, 1)
        print_info(f"  段 {i}: 已替换")

    if path.suffix == '.py':
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"{path.relative_to(ROOT)}: 语法错误 ({err})")
            return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


# ============================================================
# P2-1: outline_panel 硬编码 50000
# ============================================================
P2_1_MARKER = "P2-1: 从偏好读取 large_file_threshold"

P2_1_OLD = '''                # P2-C6: 限制读取行数
                # 原实现直接 proxy.get_text()，100MB 文件会
                # 卡住主线程几秒甚至 OOM。
                MAX_LINES_READ = 50000
                text = ""
                try:
                    sc = getattr(proxy, 'sc', None)
                    if sc is not None:
                        total = sc.SendScintilla(sc.SCI_GETLINECOUNT)
                        n = min(MAX_LINES_READ, total)
                        lines = [sc.text(i) for i in range(n)]
                        text = "\\n".join(lines)
                    else:
                        text = proxy.get_text()
                except Exception:
                    try:
                        text = proxy.get_text()[:500_000]
                    except Exception:
                        text = ""'''

P2_1_NEW = '''                # P2-C6 + P2-1: 限制读取行数
                # P2-1: 从偏好读取 large_file_threshold，
                # 允许用户在首选项里调整（默认 10MB，按 50
                # 字节/行估算最大行数）。
                try:
                    threshold_mb = self.main_window.prefs.get(
                        "large_file_threshold", 10
                    )
                    max_lines = int(threshold_mb * 1024 * 1024 / 50)
                    max_lines = max(5000, min(max_lines, 200000))
                except Exception:
                    max_lines = 50000

                text = ""
                try:
                    sc = getattr(proxy, 'sc', None)
                    if sc is not None:
                        total = sc.SendScintilla(sc.SCI_GETLINECOUNT)
                        n = min(max_lines, total)
                        lines = [sc.text(i) for i in range(n)]
                        text = "\\n".join(lines)
                    else:
                        text = proxy.get_text()
                except Exception:
                    try:
                        text = proxy.get_text()[:500_000]
                    except Exception:
                        text = ""'''


def fix_p2_1(no_backup: bool) -> str:
    path = ROOT / "ui" / "outline_panel.py"
    return apply_multi(path, [(P2_1_MARKER, P2_1_OLD, P2_1_NEW)],
                       no_backup)


# ============================================================
# P2-3: ThemeLoader Lexer 颜色分派
# ============================================================
P2_3_MARKER = "P2-3: 按 lexer 类型选择样式索引"

P2_3_OLD = '''    def _apply_lexer_colors(self, lexer, colors: ThemeColors):
        """应用词法器颜色"""
        try:
            # 通用样式
            lexer.setDefaultColor(QColor(colors.foreground))
            lexer.setDefaultPaper(QColor(colors.background))

            # 常用关键字/注释/字符串/数字样式
            # 大多数 QsciLexer 子类使用相同的索引
            lexer.setColor(QColor(colors.comment), 1)       # 注释
            lexer.setColor(QColor(colors.number), 2)        # 数字
            lexer.setColor(QColor(colors.string), 3)        # 字符串
            lexer.setColor(QColor(colors.character), 4)     # 字符
            lexer.setColor(QColor(colors.keyword), 5)       # 关键字
            lexer.setColor(QColor(colors.class_name), 8)    # 类名
            lexer.setColor(QColor(colors.function_name), 9) # 函数名
            lexer.setColor(QColor(colors.operator), 10)     # 运算符
            lexer.setColor(QColor(colors.identifier), 11)   # 标识符
            lexer.setColor(QColor(colors.decorator), 14)    # 装饰器

            # 背景纸
            for i in range(0, 128):
                try:
                    lexer.setPaper(QColor(colors.background), i)
                except Exception:
                    pass

        except Exception as e:
            print(f"[ThemeLoader] 应用词法器颜色失败: {e}")'''

P2_3_NEW = '''    def _apply_lexer_colors(self, lexer, colors: ThemeColors):
        """应用词法器颜色（P2-3: 按 lexer 类型选择样式索引）

        不同 QsciLexer 子类的样式索引完全不同。例如：
          - Python: keyword=5, class=8, function=9, decorator=14
          - C++:    keyword=5/16, class=19, function=19, decorator=9
          - JavaScript 继承自 CPP，索引与 CPP 一致

        原实现硬编码 Python 的索引，导致 C++/JS 文件主题化失效。
        """
        # 样式索引映射表
        PYTHON_MAP = {
            'comment': 1, 'number': 2, 'string': 3,
            'character': 4, 'keyword': 5, 'class_name': 8,
            'function_name': 9, 'operator': 10,
            'identifier': 11, 'decorator': 14,
        }
        CPP_MAP = {
            'comment': 1, 'number': 4, 'keyword': 5,
            'string': 6, 'character': 7, 'operator': 10,
            'identifier': 11, 'class_name': 19,
            'function_name': 19, 'decorator': 9,
        }

        try:
            lexer.setDefaultColor(QColor(colors.foreground))
            lexer.setDefaultPaper(QColor(colors.background))

            # P2-3: 按 lexer 类型选择样式索引
            style_map = PYTHON_MAP  # 默认
            try:
                from PyQt5.Qsci import (
                    QsciLexerPython, QsciLexerCPP,
                )
                if isinstance(lexer, QsciLexerPython):
                    style_map = PYTHON_MAP
                elif isinstance(lexer, QsciLexerCPP):
                    # JavaScript / TypeScript 继承自 CPP
                    style_map = CPP_MAP
            except Exception:
                pass

            for attr, style_id in style_map.items():
                color = getattr(colors, attr, None)
                if color:
                    try:
                        lexer.setColor(QColor(color), style_id)
                    except Exception:
                        pass

            # 背景纸
            for i in range(0, 128):
                try:
                    lexer.setPaper(QColor(colors.background), i)
                except Exception:
                    pass

        except Exception as e:
            print(f"[ThemeLoader] 应用词法器颜色失败: {e}")'''


def fix_p2_3(no_backup: bool) -> str:
    path = ROOT / "infrastructure" / "theme_loader.py"
    return apply_multi(path, [(P2_3_MARKER, P2_3_OLD, P2_3_NEW)],
                       no_backup)


# ============================================================
# P3-2: command_palette 使用历史 key
# ============================================================
P3_2_MARKER = "P3-2: 生成更唯一的 key"

P3_2_OLD_SCORE = '''    def _get_usage_score(self, item: PaletteItem) -> int:
        """根据使用历史计算加分"""
        key = item.title
        if key not in self._usage_history:
            return 0'''

P3_2_NEW_SCORE = '''    def _usage_key(self, item: PaletteItem) -> str:
        """P3-2: 生成更唯一的 key

        原实现用 item.title 作 key，不同命令（同名）会串用
        同一份历史分数。优先用 action_name；其次回调/数据的 id。
        """
        if item.action_name:
            return f"action:{item.action_name}"
        if item.callback is not None:
            return f"cb:{id(item.callback)}"
        if item.data is not None:
            return f"data:{id(item.data)}"
        return f"title:{item.title}"

    def _get_usage_score(self, item: PaletteItem) -> int:
        """根据使用历史计算加分"""
        key = self._usage_key(item)
        if key not in self._usage_history:
            return 0'''

P3_2_OLD_RECORD = '''    def _record_usage(self, item: PaletteItem):
        """记录使用历史"""
        key = item.title
        now = time.time()'''

P3_2_NEW_RECORD = '''    def _record_usage(self, item: PaletteItem):
        """记录使用历史"""
        # P3-2: 用 _usage_key 生成 key
        key = self._usage_key(item)
        now = time.time()'''


def fix_p3_2(no_backup: bool) -> str:
    path = ROOT / "ui" / "command_palette.py"
    return apply_multi(
        path,
        [
            ("P3-2: 生成更唯一的 key", P3_2_OLD_SCORE, P3_2_NEW_SCORE),
            ("P3-2: 用 _usage_key 生成 key",
             P3_2_OLD_RECORD, P3_2_NEW_RECORD),
        ],
        no_backup,
    )


# ============================================================
# P3-3: sandbox_policy DANGEROUS_MODULES 精简
# ============================================================
P3_3_MARKER = "P3-3: 移除由权限门控的冗余模块"

P3_3_OLD = '''# 这些模块被明确禁止导入（即使有权限也不允许）
DANGEROUS_MODULES: Set[str] = {
    # 进程/系统
    'subprocess', 'multiprocessing', 'threading', 'concurrent',
    'pty', 'pdb', 'faulthandler', 'signal',
    'os.system', 'os.popen', 'os.spawn', 'os.exec',
    'os.fork', 'os.kill',

    # 逃逸相关
    'ctypes', 'cffi', 'cProfile',
    'gc',  # 可用于逃逸
    'atexit',  # 可用于逃逸
    'sys',  # sys.modules 可访问受限
    '__builtin__',
    'builtins',  # 例外：见 _SAFE_BUILTINS 说明

    # 网络（需要 network 权限才可使用）
    'socket', 'ssl', 'http', 'urllib', 'ftplib', 'smtplib',
    'telnetlib', 'xmlrpc', 'requests', 'aiohttp', 'httpx',
    'websocket', 'paramiko',

    # 文件系统（需要 filesystem 权限才可使用）
    'shutil', 'glob', 'tempfile',
    'os.path',  # 部分方法受限

    # 加密/密钥（除非插件明确声明）
    'keyring', 'cryptography', 'Crypto',

    # 其他危险
    'pickle', 'marshal', 'shelve', 'dbm',
    'importlib', 'imp',
    'code', 'codeop',
    'builtins',
    '__future__',
    'nt',  # Windows 内部模块
    'posix',
    'msvcrt',
    'winreg',
}'''

P3_3_NEW = '''# 这些模块被明确禁止导入（即使有权限也不允许）
#
# P3-3: 移除由权限门控的冗余模块
#   - 原实现把 socket / ssl / http / urllib / requests /
#     aiohttp / httpx / websocket / ftplib / smtplib /
#     telnetlib / xmlrpc 等"网络模块"放在这里。
#     但 can_import() 里这些模块由 allow_network 权限控制，
#     且权限分支检查在 DANGEROUS_MODULES 之前，导致
#     这里的条目冗余。
#   - 同理 shutil / glob / tempfile / os.path 由 filesystem
#     权限控制；subprocess / multiprocessing 由 process 权限
#     控制。它们都不应该出现在这里。
#   - 保留的只有"绝对禁止"：沙箱逃逸 / 反序列化漏洞 /
#     动态执行 / 平台内部等，无论什么权限都不允许。
DANGEROUS_MODULES: Set[str] = {
    # ---- 沙箱逃逸 ----
    'ctypes', 'cffi', '_ctypes',
    'gc',           # 可遍历对象图
    'atexit',       # 解释器退出时执行任意代码
    'sys',          # sys.modules 可访问被限制的模块

    # ---- 反序列化漏洞 ----
    'pickle', 'cPickle', 'dill',
    'marshal', 'shelve', 'dbm',

    # ---- 动态导入/执行 ----
    'importlib', 'imp',
    'code', 'codeop',

    # ---- 平台内部 ----
    'nt', 'posix', 'msvcrt', 'winreg', '_winapi',

    # ---- 调试/剖析（可读取栈帧）----
    'faulthandler', 'pdb', 'cProfile',

    # ---- 线程/信号（无权限门控）----
    'threading', 'concurrent',
    'pty', 'signal',

    # 说明:
    #   socket / ssl / http / urllib / requests / aiohttp /
    #   httpx / websocket / ftplib / smtplib / telnetlib /
    #   xmlrpc / paramiko → 由 network 权限控制
    #   shutil / glob / tempfile / os.path → 由 filesystem 权限
    #   subprocess / multiprocessing → 由 process 权限
    #   这些模块不在这里，避免与权限分支语义冲突。
}'''


def fix_p3_3(no_backup: bool) -> str:
    path = ROOT / "core" / "sandbox_policy.py"
    return apply_multi(path, [(P3_3_MARKER, P3_3_OLD, P3_3_NEW)],
                       no_backup)


# ============================================================
# P3-4: LSP 位置转换
# ============================================================
P3_4_MARKER = "P3-4: LSP character 是 UTF-16 code unit 偏移"

# 段 A: 在 _on_lsp_diagnostics 之前插入 _lsp_pos_to_scintilla
P3_4_A_OLD = '''    def _on_lsp_diagnostics(self, uri: str, diagnostics: List[Dict]):
        """LSP 诊断结果回调"""
        try:'''

P3_4_A_NEW = '''    def _lsp_pos_to_scintilla(self, line: int, character: int) -> int:
        """LSP position → Scintilla 字节偏移

        P3-4: LSP 的 character 是 UTF-16 code unit 偏移，
        SCI_FINDCOLUMN 期望的是"视觉列"，两者对 emoji /
        4 字节 CJK 扩展字符不一致。

        改用：字符偏移 → UTF-8 字节偏移 + 行起始位置。
        （简化：假设 BMP 字符，不处理代理对；对 4 字节 CJK
          扩展字符会略有偏差，但远好于原实现。）
        """
        try:
            if line < 0 or character < 0:
                return -1
            line_text = self.sc.text(line)
            prefix = line_text[:character]
            byte_offset = len(
                prefix.encode('utf-8', errors='replace')
            )
            line_start = self.sc.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMLINE, line
            )
            if line_start < 0:
                return -1
            return line_start + byte_offset
        except Exception:
            return -1

    def _on_lsp_diagnostics(self, uri: str, diagnostics: List[Dict]):
        """LSP 诊断结果回调"""
        try:'''

# 段 B: 替换 SendScintilla 调用
P3_4_B_OLD = '''                    start = self.sc.SendScintilla(
                        QsciScintilla.SCI_FINDCOLUMN,
                        start_line, start_char
                    )
                    end = self.sc.SendScintilla(
                        QsciScintilla.SCI_FINDCOLUMN,
                        end_line, end_char
                    )

                    self.sc.SendScintilla(
                        QsciScintilla.SCI_SETINDICATORCURRENT,
                        INDICATOR_LSP_ERROR
                    )
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_INDICATORFILLRANGE,
                        start, max(1, end - start)
                    )'''

P3_4_B_NEW = '''                    # P3-4: LSP character 是 UTF-16 code unit 偏移，
                    # 用 _lsp_pos_to_scintilla 转成字节偏移
                    start = self._lsp_pos_to_scintilla(
                        start_line, start_char
                    )
                    end = self._lsp_pos_to_scintilla(
                        end_line, end_char
                    )

                    if start < 0 or end < 0:
                        continue

                    self.sc.SendScintilla(
                        QsciScintilla.SCI_SETINDICATORCURRENT,
                        INDICATOR_LSP_ERROR
                    )
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_INDICATORFILLRANGE,
                        start, max(1, end - start)
                    )'''


def fix_p3_4(no_backup: bool) -> str:
    path = ROOT / "core" / "editor.py"
    return apply_multi(
        path,
        [
            ("_lsp_pos_to_scintilla", P3_4_A_OLD, P3_4_A_NEW),
            ("P3-4: LSP character 是 UTF-16 code unit 偏移，",
             P3_4_B_OLD, P3_4_B_NEW),
        ],
        no_backup,
    )


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("P2-1", "outline_panel 硬编码行数", fix_p2_1),
    ("P2-3", "theme_loader Lexer 颜色分派", fix_p2_3),
    ("P3-2", "command_palette 历史 key", fix_p3_2),
    ("P3-3", "sandbox_policy DANGEROUS_MODULES 精简", fix_p3_3),
    ("P3-4", "editor.py LSP 位置转换", fix_p3_4),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="剩余 P2/P3 项批量修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：P2-1,P3-4,...')
    args = parser.parse_args()

    print_header("剩余 P2/P3 项批量修复")
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
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print()
    print("清理备份:")
    print("  Windows:     del /s *.bak.p3")
    print("  Linux/macOS: find . -name '*.bak.p3' -delete")

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