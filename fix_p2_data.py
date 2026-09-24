#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - P2 数据源统一与清理
==================================
修复 9 项 P2 问题（数据源 / 信号 / 清理）。

  C1  welcome_widget.py 的 DAILY_TIPS 与 ui/tips.py 重复
  C2  usage_stats_panel.py 与 core.usage_stats 重复实现
  C3  theme_market.py 直接访问 client._cache（加公开方法）
  C4  main_window._show_daily_tip 手动点击无反应
  C5  main_window 未连接 gsearch.replace_requested
  C6  outline_panel 大文件全量读入内存
  C7  conftest.py 未使用的 monkeypatch 参数
  C8  requirements-dev.txt 缺 mkdocs
  C9  event_bus.py 注释过时 + theme_loader 空调用

特性：
  - 幂等
  - 每项独立处理
  - 修改前备份 *.bak.p2
  - Python 文件修改后 compile() 验证

用法：
    python fix_p2_data.py --dry-run
    python fix_p2_data.py
    python fix_p2_data.py --only C1,C5
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List, Callable

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p2"


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


def apply_replace(path: Path, old: str, new: str,
                  marker: str, no_backup: bool) -> str:
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    if marker and marker in content:
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    cnt = content.count(old)
    if cnt == 0:
        print_fail(f"{path.relative_to(ROOT)}: 锚点未找到")
        for line in old.split('\n')[:3]:
            print(f"      | {line}")
        return 'failed'
    if cnt > 1:
        print_fail(f"{path.relative_to(ROOT)}: 锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(old, new, 1)
    if path.suffix == '.py':
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"{path.relative_to(ROOT)}: 语法错误 ({err})")
            return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


def apply_multi(path: Path,
                replacements: List[Tuple[str, str]],
                marker: str,
                no_backup: bool) -> str:
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    if marker and marker in content:
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

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

    new_content = content
    for old, new in replacements:
        new_content = new_content.replace(old, new, 1)

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
# C1: welcome_widget.py DAILY_TIPS 统一
# ============================================================
C1_MARKER = "# P2-C1: DAILY_TIPS 统一到 ui/tips.py"

C1_OLD = """# 每日技巧
DAILY_TIPS = [
    "按 Ctrl+Shift+P 打开命令面板，模糊搜索所有功能。",
    "按 Ctrl+P 快速切换已打开的文件。",
    "按 Ctrl+R 跳转到当前文件的函数或类。",
    "按 Alt+C 进入列模式，可同时编辑多行文本。",
    "按 Ctrl+D 选中当前单词，再按一次选中下一个相同单词。",
    "按 Ctrl+Shift+R 开始录制宏，Ctrl+Shift+M 回放宏。",
    "选中文本后输入括号或引号可自动包裹。",
    "按 Ctrl+/ 快速注释或取消注释当前行。",
    "按 F11 进入无干扰全屏模式，专心编辑。",
    "按 Ctrl+` 打开 Python 控制台，可执行交互式脚本。",
    "按 Ctrl+Shift+F 进行项目级别的全局搜索。",
    "按 F5 在光标处插入当前日期时间。",
    "拖拽文件到编辑器窗口可直接打开。",
    "双击标签可将标签分离为独立窗口。",
    "中键点击标签可快速关闭标签。",
    "在目录树中按 Alt+点击可快速切换书签。",
    "在编辑器中按住 Ctrl+点击可添加多光标。",
    "按 Ctrl+Shift+Up/Down 可以上下移动整行代码。",
    "按 Ctrl+Shift+D 可以复制当前行到下一行。",
    "通过插件市场可安装 Markdown 预览、AI 助手等扩展。",
    "按 Ctrl+G 快速跳转到指定行。",
    "在状态栏可查看编码、行尾符、Git 分支等信息。",
    "在查找框中输入正则表达式可进行复杂搜索。",
    "在全局搜索中可指定文件类型过滤，如 *.py;*.md。",
    "按 Ctrl+Alt+S 可保存所有未保存的文件。",
]"""

C1_NEW = """# P2-C1: DAILY_TIPS 统一到 ui/tips.py
# 原实现与 ui/tips.py 里的 TIPS 重复定义，维护时容易遗漏。
from ui.tips import TIPS as DAILY_TIPS"""


def fix_c1(no_backup: bool) -> str:
    path = ROOT / "ui" / "welcome_widget.py"
    return apply_replace(path, C1_OLD, C1_NEW,
                         marker=C1_MARKER, no_backup=no_backup)


# ============================================================
# C2: usage_stats_panel.py 复用 core.usage_stats
# ============================================================
C2_MARKER = "# P2-C2: 复用 core.usage_stats"

C2_OLD = """    def _load_stats(self):
        \"\"\"加载统计数据\"\"\"
        result = {
            'basic': {},
            'file_types': {},
            'hourly': {},
            'daily': {},
            'features': {},
        }

        # 从 telemetry 加载
        try:
            from core.telemetry import get_telemetry
            telemetry = get_telemetry()
            result['basic'] = telemetry.get_stats()
        except Exception:
            pass

        # 从 session 历史加载
        try:
            if os.path.exists('session.json'):
                with open('session.json', 'r', encoding='utf-8') as f:
                    session = json.load(f)

                # 文件类型统计
                for finfo in session.get('files', []):
                    fp = finfo.get('filepath') or ''
                    if fp:
                        ext = os.path.splitext(fp)[1].lower()
                        if ext:
                            result['file_types'][ext] = \\
                                result['file_types'].get(ext, 0) + 1
        except Exception:
            pass

        # 从全局词频统计加载
        try:
            from core.local_completer import get_local_completer
            completer = get_local_completer()
            if completer:
                # 最近使用
                result['features']['最近使用的词数'] = len(
                    completer.recent_words
                )
                result['features']['词频库大小'] = len(
                    completer.word_freq
                )
        except Exception:
            pass

        return result"""

C2_NEW = """    def _load_stats(self):
        \"\"\"加载统计数据。

        P2-C2: 复用 core.usage_stats

        原实现自己读 telemetry / session / local_completer，
        字段名和口径与 core.usage_stats 不一致，两处显示可能
        不同。统一走 core.usage_stats.get_snapshot()。
        \"\"\"
        empty = {
            'basic': {}, 'file_types': {},
            'hourly': {}, 'daily': {}, 'features': {},
        }

        try:
            from core.usage_stats import get_usage_stats
            snap = get_usage_stats().get_snapshot(force=True)

            return {
                'basic': {
                    'first_run': snap.first_run,
                    'last_run': snap.last_run,
                    'run_count': snap.run_count,
                    'files_opened': snap.files_opened,
                    'files_saved': snap.files_saved,
                    'searches_run': snap.searches_run,
                    'plugins_loaded': snap.plugins_loaded,
                    'features_used': snap.features_used,
                },
                'file_types': dict(snap.files_by_ext),
                'hourly': dict(snap.hourly_activity),
                'daily': dict(snap.daily_activity),
                'features': {
                    '最近使用的词数': snap.recent_words_count,
                    '词频库大小': snap.word_freq_size,
                },
            }
        except ImportError as e:
            print(f"[UsageStatsDialog] core.usage_stats 不可用: {e}")
            return empty
        except Exception as e:
            print(f"[UsageStatsDialog] 加载统计失败: {e}")
            return empty"""


def fix_c2(no_backup: bool) -> str:
    path = ROOT / "ui" / "usage_stats_panel.py"
    return apply_replace(path, C2_OLD, C2_NEW,
                         marker=C2_MARKER, no_backup=no_backup)


# ============================================================
# C3: theme_market.py clear_cache 公开方法
# ============================================================
C3_MARKER = "# P2-C3: 加 clear_cache 公开方法"

C3_OLD_1 = """    def _load_fallback(self) -> Optional[Dict[str, Any]]:
        \"\"\"读取 resources/theme_fallback.json\"\"\"
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "resources", "theme_fallback.json")
            if not os.path.exists(path):
                return None
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['_from_fallback'] = True
            return data
        except Exception as e:
            print(f"[ThemeMarket] 读取本地兜底失败: {e}")
            return None"""

C3_NEW_1 = """    def _load_fallback(self) -> Optional[Dict[str, Any]]:
        \"\"\"读取 resources/theme_fallback.json\"\"\"
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "resources", "theme_fallback.json")
            if not os.path.exists(path):
                return None
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['_from_fallback'] = True
            return data
        except Exception as e:
            print(f"[ThemeMarket] 读取本地兜底失败: {e}")
            return None

    def clear_cache(self):
        \"\"\"P2-C3: 加 clear_cache 公开方法。

        原来外部直接访问 client._cache = None，破坏封装。
        \"\"\"
        self._cache = None
        self._cache_time = 0.0"""


C3_OLD_2 = """        if url:
            self._settings.setValue("registry_url", url)
            self.client.registry_url = url
        else:
            self._settings.remove("registry_url")
            self.client.registry_url = DEFAULT_MARKET_URL
        self.client._cache = None
        self._load(force=True)

    def _on_reset_url(self):
        self.url_edit.clear()
        self._settings.remove("registry_url")
        self.client.registry_url = DEFAULT_MARKET_URL
        self.client._cache = None
        self._load(force=True)"""

C3_NEW_2 = """        if url:
            self._settings.setValue("registry_url", url)
            self.client.registry_url = url
        else:
            self._settings.remove("registry_url")
            self.client.registry_url = DEFAULT_MARKET_URL
        # P2-C3: 用公开方法
        self.client.clear_cache()
        self._load(force=True)

    def _on_reset_url(self):
        self.url_edit.clear()
        self._settings.remove("registry_url")
        self.client.registry_url = DEFAULT_MARKET_URL
        # P2-C3: 用公开方法
        self.client.clear_cache()
        self._load(force=True)"""


def fix_c3(no_backup: bool) -> str:
    path = ROOT / "ui" / "theme_market.py"
    return apply_multi(
        path,
        [(C3_OLD_1, C3_NEW_1), (C3_OLD_2, C3_NEW_2)],
        marker=C3_MARKER,
        no_backup=no_backup,
    )


# ============================================================
# C4: main_window _show_daily_tip manual 参数
# ============================================================
C4_MARKER = "# P2-C4: manual 参数"

C4_OLD_1 = """    def _show_daily_tip(self):
        \"\"\"
        显示每日技巧。

        P2-8: 一天只显示一次（基于 QSettings 记录日期）。
        菜单手动点击同样受此限制（"每日"语义）。
        \"\"\"
        try:
            import datetime

            settings = QSettings(ORG_NAME, "Editor")
            today = datetime.date.today().isoformat()

            last_date = settings.value("last_tip_date", "", type=str)
            if last_date == today:
                return  # 今天已弹过"""

C4_NEW_1 = """    def _show_daily_tip(self, manual: bool = False):
        \"\"\"
        显示每日技巧。

        P2-8: 一天只显示一次（基于 QSettings 记录日期）。
        P2-C4: manual=True 时（菜单手动点击）跳过日期限制，
               否则用户当天已自动弹过，手动点击就没反应了。
        \"\"\"
        try:
            import datetime

            settings = QSettings(ORG_NAME, "Editor")
            today = datetime.date.today().isoformat()

            last_date = settings.value("last_tip_date", "", type=str)
            # P2-C4: manual 参数
            if not manual and last_date == today:
                return  # 今天已弹过，且是自动触发"""


C4_OLD_2 = """        self._add_action(self.help_menu, "💡 每日技巧", None,
                          self._show_daily_tip)"""

C4_NEW_2 = """        # P2-C4: manual 参数
        self._add_action(
            self.help_menu, "💡 每日技巧", None,
            lambda checked=False: self._show_daily_tip(manual=True)
        )"""


def fix_c4(no_backup: bool) -> str:
    path = ROOT / "ui" / "main_window.py"
    return apply_multi(
        path,
        [(C4_OLD_1, C4_NEW_1), (C4_OLD_2, C4_NEW_2)],
        marker=C4_MARKER,
        no_backup=no_backup,
    )


# ============================================================
# C5: main_window 连接 gsearch.replace_requested
# ============================================================
C5_MARKER = "# P2-C5: 连接 replace_requested"

C5_OLD_1 = """            self.gsearch = GlobalSearchPanel(self)
            self.gsearch.match_activated.connect(
                self._on_search_match_activated
            )
            self.addDockWidget(Qt.BottomDockWidgetArea, self.gsearch)
            self.gsearch.hide()"""

C5_NEW_1 = """            self.gsearch = GlobalSearchPanel(self)
            self.gsearch.match_activated.connect(
                self._on_search_match_activated
            )
            # P2-C5: 连接 replace_requested
            # 原实现只连 match_activated，"全部替换"按钮点了没反应。
            self.gsearch.replace_requested.connect(
                self._on_global_replace
            )
            self.addDockWidget(Qt.BottomDockWidgetArea, self.gsearch)
            self.gsearch.hide()"""


C5_OLD_2 = """    def _on_search_match_activated(self, filepath: str, start: int,
                                     end: int, line: int, col: int):
        \"\"\"全局搜索匹配激活\"\"\"
        try:
            proxy = self.tabs.open_file(filepath)
            if proxy and proxy.sc:
                try:
                    proxy.sc.SendScintilla(proxy.sc.SCI_SETSEL, start, end)
                except Exception:
                    pass
                proxy.sc.setCursorPosition(line - 1, col)
                proxy.sc.ensureLineVisible(line - 1)
        except Exception as e:
            print(f"[MainWindow] 搜索跳转失败: {e}")"""

C5_NEW_2 = """    def _on_search_match_activated(self, filepath: str, start: int,
                                     end: int, line: int, col: int):
        \"\"\"全局搜索匹配激活\"\"\"
        try:
            proxy = self.tabs.open_file(filepath)
            if proxy and proxy.sc:
                try:
                    proxy.sc.SendScintilla(proxy.sc.SCI_SETSEL, start, end)
                except Exception:
                    pass
                proxy.sc.setCursorPosition(line - 1, col)
                proxy.sc.ensureLineVisible(line - 1)
        except Exception as e:
            print(f"[MainWindow] 搜索跳转失败: {e}")

    def _on_global_replace(self, pattern: str, replace_text: str,
                            file_results: dict):
        \"\"\"P2-C5: 全局搜索 → 全部替换。

        参数:
            pattern: 搜索模式
            replace_text: 替换文本
            file_results: {filepath: [SearchMatch, ...]}
        \"\"\"
        if not pattern or not file_results:
            return

        try:
            from core.search import (
                SearchOptions, SearchEngine, ReplaceEngine
            )
            from core.content_provider import LocalFileProvider

            total = 0
            abs_paths = set()

            for filepath in file_results:
                abs_paths.add(os.path.abspath(filepath))
                try:
                    provider = LocalFileProvider()
                    provider.open(filepath)
                    try:
                        options = SearchOptions(pattern=pattern)
                        engine = SearchEngine(provider, options)
                        result = engine.search()
                        if result.is_empty:
                            continue

                        replace_engine = ReplaceEngine(provider)
                        n = replace_engine.replace_all(
                            result, replace_text,
                            is_regex=options.is_regex,
                            pattern=pattern,
                        )
                        provider.save(filepath)
                        total += n
                    finally:
                        provider.close()
                except Exception as e:
                    print(f"[MainWindow] 替换 {filepath} 失败: {e}")

            # 刷新已打开的受影响文件
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if not hasattr(w, 'proxy') or not w.proxy:
                    continue
                fp = None
                try:
                    if w.proxy.document:
                        fp = w.proxy.document.filepath
                except Exception:
                    pass
                if fp and os.path.abspath(fp) in abs_paths:
                    try:
                        if w.proxy.document:
                            w.proxy.document.reload()
                        if w.proxy.sc and w.proxy.document:
                            w.proxy.sc.setText(
                                w.proxy.document.get_text()
                            )
                    except Exception:
                        pass

            self.status_bar.showMessage(f"已替换 {total} 处", 3000)

        except Exception as e:
            print(f"[MainWindow] 全局替换失败: {e}")"""


def fix_c5(no_backup: bool) -> str:
    path = ROOT / "ui" / "main_window.py"
    return apply_multi(
        path,
        [(C5_OLD_1, C5_NEW_1), (C5_OLD_2, C5_NEW_2)],
        marker=C5_MARKER,
        no_backup=no_backup,
    )


# ============================================================
# C6: outline_panel 大文件限制读取
# ============================================================
C6_MARKER = "# P2-C6: 限制读取行数"

C6_OLD = """            # 文件或语言变化 → 重新解析
            if (filepath != self._current_filepath or
                    language != self._current_language):
                self._current_filepath = filepath
                self._current_language = language

                text = (proxy.get_text() if hasattr(proxy, 'get_text')
                        else proxy.sc.text())
                self._current_symbols = self.parser.parse(
                    text, language, filepath
                )"""

C6_NEW = """            # 文件或语言变化 → 重新解析
            if (filepath != self._current_filepath or
                    language != self._current_language):
                self._current_filepath = filepath
                self._current_language = language

                # P2-C6: 限制读取行数
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
                        text = ""

                self._current_symbols = self.parser.parse(
                    text, language, filepath
                )"""


def fix_c6(no_backup: bool) -> str:
    path = ROOT / "ui" / "outline_panel.py"
    return apply_replace(path, C6_OLD, C6_NEW,
                         marker=C6_MARKER, no_backup=no_backup)


# ============================================================
# C7: conftest.py 删除 monkeypatch
# ============================================================
C7_MARKER = "# P2-C7: monkeypatch 未使用，已移除"

C7_OLD = """@pytest.fixture
def preferences(qapp, tmp_path, monkeypatch):
    \"\"\"隔离的 Preferences 实例（不污染用户真实设置）\"\"\""""

C7_NEW = """# P2-C7: monkeypatch 未使用，已移除
@pytest.fixture
def preferences(qapp, tmp_path):
    \"\"\"隔离的 Preferences 实例（不污染用户真实设置）\"\"\""""


def fix_c7(no_backup: bool) -> str:
    path = ROOT / "tests" / "conftest.py"
    return apply_replace(path, C7_OLD, C7_NEW,
                         marker=C7_MARKER, no_backup=no_backup)


# ============================================================
# C8: requirements-dev.txt 补 mkdocs
# ============================================================
C8_MARKER = "# P2-C8: 补 mkdocs"

C8_OLD = """pyinstaller>=6.0.0"""

C8_NEW = """pyinstaller>=6.0.0

# P2-C8: 补 mkdocs
# 文档由 mkdocs.yml 定义，README 也提到文档生成
mkdocs>=1.5.0
mkdocs-material>=9.0.0"""


def fix_c8(no_backup: bool) -> str:
    path = ROOT / "requirements-dev.txt"
    return apply_replace(path, C8_OLD, C8_NEW,
                         marker=C8_MARKER, no_backup=no_backup)


# ============================================================
# C9: 注释修正 + 空调用删除
# ============================================================
C9A_MARKER = "# P2-C9: 已从 PySide6 迁移到 PyQt5"

C9A_OLD = """本文件为全局事件总线模块，包含：
- 所有强类型事件数据类（dataclass）
- 事件总线类（基于 PySide6 pyqtSignal）"""

C9A_NEW = """本文件为全局事件总线模块，包含：
- 所有强类型事件数据类（dataclass）
- 事件总线类（基于 PyQt5 pyqtSignal）
# P2-C9: 已从 PySide6 迁移到 PyQt5"""


C9B_MARKER = "# P2-C9: 删除对 no-op 方法的调用"

C9B_OLD = """            # ============ 通过 Scintilla API 设置更多样式 ============
            self._apply_scintilla_styles(editor, colors)"""

C9B_NEW = """            # ============ 通过 Scintilla API 设置更多样式 ============
            # P2-C9: 删除对 no-op 方法的调用
            # _apply_scintilla_styles 已改为 no-op（见方法内注释），
            # 调用它没有意义，反而增加阅读负担。
            # 颜色已由 apply() 中的高层 API 设置。"""


def fix_c9(no_backup: bool) -> str:
    # 9a: event_bus.py 注释
    r1 = apply_replace(
        ROOT / "app" / "event_bus.py",
        C9A_OLD, C9A_NEW, marker=C9A_MARKER, no_backup=no_backup,
    )
    # 9b: theme_loader.py 删空调用
    r2 = apply_replace(
        ROOT / "infrastructure" / "theme_loader.py",
        C9B_OLD, C9B_NEW, marker=C9B_MARKER, no_backup=no_backup,
    )
    if 'failed' in (r1, r2):
        return 'failed'
    if 'applied' in (r1, r2):
        return 'applied'
    return 'skipped'


# ============================================================
# 主流程
# ============================================================
FIXES: List[Tuple[str, str, Callable[[bool], str]]] = [
    ("C1", "welcome_widget DAILY_TIPS 统一", fix_c1),
    ("C2", "usage_stats_panel 复用 core.usage_stats", fix_c2),
    ("C3", "theme_market 加 clear_cache", fix_c3),
    ("C4", "main_window 每日技巧 manual 参数", fix_c4),
    ("C5", "main_window 连接 gsearch.replace_requested", fix_c5),
    ("C6", "outline_panel 大文件限制读取", fix_c6),
    ("C7", "conftest 删除 monkeypatch", fix_c7),
    ("C8", "requirements-dev 补 mkdocs", fix_c8),
    ("C9", "注释修正 + 空调用删除", fix_c9),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="青草编辑器 P2 数据源统一与清理"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：C1,C2,...')
    args = parser.parse_args()

    print_header("青草编辑器 P2 数据源统一与清理")
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
          "for f in ['ui/welcome_widget.py', "
          "'ui/usage_stats_panel.py', 'ui/theme_market.py', "
          "'ui/main_window.py', 'ui/outline_panel.py', "
          "'tests/conftest.py', 'app/event_bus.py', "
          "'infrastructure/theme_loader.py']]; print('OK')\"")
    print("  2. 启动编辑器: python main.py")
    print("  3. 验证 C1: 欢迎页'换一条技巧'，应与帮助菜单的一致")
    print("  4. 验证 C4: 帮助 → 每日技巧，应能弹出（即使今天已自动弹过）")
    print("  5. 验证 C5: 全局搜索 → 全部替换，应真正替换")
    print("  6. 跑测试: python tests/run_all.py")
    print()
    print("清理备份:")
    print("  Windows:     del /s *.bak.p2")
    print("  Linux/macOS: find . -name '*.bak.p2' -delete")

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