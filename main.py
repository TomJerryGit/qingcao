#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为青草编辑器的启动入口，包含：
- 国际化设置（core.i18n）
- 全局异常处理与崩溃上报（core.crash_reporter）
- 便携模式检测
- 启动画面
- 主窗口延迟加载
- 崩溃恢复检测（旧版 backup/autosave_*）
- 自动备份恢复（backup/autosave 目录）
- 首次启动向导（ui.first_run_wizard）
- 自动更新检查（core.updater）
- 遥测（core.telemetry）
- 主题加载（infrastructure.theme_loader）
- 日志轮转
- 命令行参数解析
- 会话恢复

修复记录:
- setup_locale: 拆分为 _detect_language + 加载逻辑，独立处理
  "PyQt5 缺失"与"core.i18n 导入失败"两类异常（P3-5）。
  之前两类异常混在同一个 try 中，PyQt5 缺失时回退路径会二次
  import PyQt5 而再次失败。
- setQuitOnLastWindowClosed: 从 False 改为 True（P0）。
  原值与 closeEvent 中未显式 quit() 的组合导致应用"关不掉"。
- deferred_init: 新增草稿恢复调用（P0-2）。生产者
  `core/document.py::_save_draft` 每 60 秒写 backup/drafts/*.draft，
  但读取端 `SessionManager.check_and_recover_drafts()` 原先**零调用点**
  —— 只写不读，崩溃后未保存正文 100% 丢失。现已接线（见
  `_render_recovered_drafts` / `_notify_draft_recovery`）。

待接线契约（P0-10：requirements.txt 承诺的"文件 → 导出 → PDF"）
--------------------------------------------------------------
`requirements.txt` 第 69-72 行声明"用于『文件 → 导出 → PDF』
（core.exporter）"，但 `core/exporter.py` 目前**全仓零引用**
（只在 `build.py` 的 hiddenimports 名单里出现），菜单里也没有"导出"项。
`core/exporter.py` 归 task-10，下面是**已确认可用**的调用契约，
接线时按此实现即可（`ui/main_window.py` 的菜单结构不在本次修复范围内）：

    from core.exporter import Exporter

    # 1) 取当前编辑器正文与元信息
    proxy = self.tabs.current_proxy()              # EditorProxy
    text  = proxy.sc.text()                        # 真实字符文本（str）
    doc   = proxy.document                         # core.document.Document
    path  = getattr(doc, 'filepath', '') or ''
    title = os.path.basename(path) or "未命名"
    language = getattr(doc, 'language', '') or "text"

    # 2) HTML（同步，返回 str；由调用方写文件）
    html = Exporter.to_html(text, title=title, language=language)
    #    写: open(out_path, 'w', encoding='utf-8').write(html)

    # 3) Markdown（同步，返回 str）
    md = Exporter.to_markdown(text, title=title, language=language)

    # 4) PDF（同步，返回 (ok: bool, message: str)；缺 reportlab 时
    #    ok=False 且 message 为 "需要安装 reportlab: pip install reportlab"）
    ok, msg = Exporter.to_pdf(text, out_path, title=title)
    if not ok:
        QMessageBox.warning(self, "PDF 导出失败", msg)

    # 5) 整个会话报告（配合 tabs.get_all_tabs_info()；注意其中的
    #    char_count 已在 P0-8 中改为**真实字符数**）
    report = Exporter.session_to_markdown(self.tabs.get_all_tabs_info())

建议的菜单接入点（不改现有菜单结构，新增一个"文件 → 导出"子菜单）:
    文件(&F) → 导出 → HTML... / Markdown... / PDF...
"""

import atexit
import datetime
import os
import shutil
import sys
import time
import traceback


def _force_utf8_stdio():
    """强制 stdout/stderr 使用 UTF-8（容忍无法编码的字符）

    ★ 与 build.py 同源的缺陷：

        英文 Windows 的控制台/管道默认编码是 cp1252，而本程序会输出中文
        （`--version`、日志、错误提示）。此时 Python 用 locale 编码写
        stdout 会直接崩：

            UnicodeEncodeError: 'charmap' codec can't encode ...

        实测：`QingCaoEditor.exe --version` 在 `PYTHONIOENCODING=cp1252`
        且输出被管道捕获时**退出码 1 且无版本输出** —— 英文系统用户
        或者脚本里调用都会踩到。中文系统（cp936）能编码中文，
        所以开发机上不会暴露。

    `errors='replace'` 保证极端环境下最多显示 `?`，绝不因为打印而中断。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


_force_utf8_stdio()


# ============================================================
# 版本信息
# ============================================================
# C4 修复：版本号统一从 version.py 读取
#
# 发布准备时修复：原兜底是**硬编码 "2.1.0"** —— 一旦 version.py 导入失败
# （打包环境路径异常等），程序会报告一个过期版本号，且 check_version
# 不检查兜底字面量。现改为读 VERSION 文件；两者都不可用则明确报错，
# 绝不再显示猜测的版本号。
try:
    from version import __version__
except ImportError:
    _version_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "VERSION"
    )
    try:
        with open(_version_file, encoding='utf-8') as _f:
            __version__ = _f.read().strip()
    except OSError:
        __version__ = ""
    if not __version__:
        raise SystemExit(
            "[main] 无法确定版本号：version.py 导入失败，且读取 %s 失败"
            % _version_file
        )

__author__ = "hedongwei"
__email__ = "1265338136@qq.com"
__copyright__ = "Copyright (c) 2024-2025 hedongwei"
__license__ = "MIT"


# ============================================================
# 应用常量
# ============================================================
APP_NAME = "青草编辑器"
APP_NAME_EN = "QingCao Editor"
ORG_NAME = "QingCao"
ORG_DOMAIN = "qingcao-editor"
APP_ID = "com.qingcao.editor"

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCES_DIR = os.path.join(ROOT_DIR, "resources")
LOCALE_DIR = os.path.join(ROOT_DIR, "locale")
THEMES_DIR = os.path.join(ROOT_DIR, "themes")
PLUGINS_DIR = os.path.join(ROOT_DIR, "plugins")
DATA_DIR = os.path.join(ROOT_DIR, "data")
BACKUP_DIR = os.path.join(ROOT_DIR, "backup")
LOGS_DIR = os.path.join(ROOT_DIR, "logs")

# 日志文件
CRASH_LOG = os.path.join(ROOT_DIR, "crash.log")
RUNTIME_LOG = os.path.join(LOGS_DIR, "runtime.log")

# 默认主题
DEFAULT_THEME = os.path.join(RESOURCES_DIR, "qingcao_theme.qss")

# 日志轮转阈值（10 MB）
LOG_MAX_SIZE = 10 * 1024 * 1024


# ============================================================
# 目录初始化
# ============================================================
def ensure_directories():
    """确保所有必需目录存在

    修复说明（草稿目录不一致 · 根因是"两处各自定义"）：
        原先 `core/document.py` 把未保存草稿写到 `<ROOT>/backup/drafts`，
        而这里建的是 `<ROOT>/data/drafts` —— **同一个概念在两处独立
        定义**，路径必然漂移。

        现在改为**直接复用写入端的唯一定义** `DocumentModel._draft_dir()`，
        从根上消除"两处不一致"的可能（而不是把某一处改成另一处的字面量，
        那样下次改动仍会漂移）。
    """
    # 草稿目录：以写入端（core/document.py 的 Document）为唯一事实来源
    try:
        from core.document import Document
        drafts_dir = Document._draft_dir()
    except Exception:
        # 极端兜底：与 core/document.py 的历史默认保持一致
        drafts_dir = os.path.join(BACKUP_DIR, "drafts")

    for d in [RESOURCES_DIR, LOCALE_DIR, THEMES_DIR, PLUGINS_DIR,
              DATA_DIR, BACKUP_DIR, LOGS_DIR,
              os.path.join(BACKUP_DIR, "autosave"),
              drafts_dir,
              os.path.join(DATA_DIR, "crashes"),
              os.path.join(DATA_DIR, "telemetry"),
              os.path.join(DATA_DIR, "snapshots"),
              os.path.join(DATA_DIR, "plugin_cache"),
              os.path.join(DATA_DIR, "plugin_backups"),
              os.path.join(DATA_DIR, "backups"),
              os.path.join(DATA_DIR, "update_cache"),
              ]:
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


# ============================================================
# 便携模式检测
# ============================================================
def is_portable():
    """
    检测是否处于便携模式。
    如果可执行文件所在目录或项目根目录存在 portable.txt 文件，
    则认为处于便携模式，所有配置和数据均写入程序目录下。
    """
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = ROOT_DIR

    markers = ['portable.txt', 'portable', '.portable']
    for m in markers:
        if os.path.exists(os.path.join(exe_dir, m)):
            return True
    return False


def instance_settings_dir(base_dir: str, pid: int,
                          new_window: bool) -> str:
    """多实例：新窗口实例使用独立的设置目录"""
    if not new_window:
        return base_dir
    return os.path.join(base_dir, "instances", str(pid))


def instance_pid_alive(pid: int) -> bool:
    """判断进程是否存活（Windows 安全实现，不用 os.kill）"""
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong(0)
            ok = ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return True


def cleanup_stale_instance_dirs(data_dir: str) -> int:
    """删除已退出实例的配置目录（instance_pid_alive 为假）"""
    import shutil
    inst = os.path.join(data_dir, "instances")
    if not os.path.isdir(inst):
        return 0
    removed = 0
    for name in os.listdir(inst):
        try:
            pid = int(name)
        except ValueError:
            continue
        if pid == os.getpid() or instance_pid_alive(pid):
            continue
        try:
            shutil.rmtree(os.path.join(inst, name), ignore_errors=True)
            removed += 1
        except Exception:
            continue
    return removed


def setup_portable_mode():
    """配置便携/多实例模式下的 QSettings"""
    new_window = os.environ.get("QINGCAO_NEW_WINDOW") == "1"
    try:
        from PyQt5.QtCore import QSettings

        if is_portable():
            data_dir = os.path.join(ROOT_DIR, "data")
        elif new_window:
            # QApplication 创建前 QStandardPaths 不可靠，显式使用 AppData
            base = (os.environ.get("APPDATA")
                    or os.path.join(os.path.expanduser("~"), "AppData",
                                    "Roaming"))
            data_dir = os.path.join(base, "QingCao", "QingCaoEditor",
                                    "data")
        else:
            return
        try:
            cleanup_stale_instance_dirs(data_dir)
        except Exception:
            pass
        data_dir = instance_settings_dir(data_dir, os.getpid(),
                                         new_window)
        os.makedirs(data_dir, exist_ok=True)
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat,
                          QSettings.UserScope, data_dir)
        QSettings.setPath(QSettings.IniFormat,
                          QSettings.SystemScope, data_dir)
        print(f"[设置] 配置存储于: {data_dir}")
    except Exception as e:
        print(f"[设置] 配置目录初始化失败: {e}")


# ============================================================
# 偏好读取（P7 接线）
# ============================================================
def _pref(key, default=None):
    """
    读取用户偏好设置（供启动流程使用）。

    说明（P7）:
        main.py 此前完全绕过 Preferences。例如 splash_screen 在首选项
        面板里可以勾选，main.py 第 9 步却无条件创建启动画面，用户改了
        毫无反应。该 helper 统一走 app.preferences.Preferences，
        并保留 QSettings 回退，保证启动流程永远能拿到一个值。

    读取偏好绝不能阻断启动，因此这里吞掉所有异常。
    """
    try:
        from app.preferences import Preferences

        return Preferences().get(key, default)
    except Exception:
        pass
    try:
        from PyQt5.QtCore import QSettings

        return QSettings(ORG_NAME, "Editor").value(key, default)
    except Exception:
        return default


# ============================================================
# 国际化设置（P3-5 修复）
# ============================================================
def _detect_language() -> str:
    """
    探测目标语言。

    优先级:
        1. 用户设置（QSettings 中的 language 键）
        2. 系统 locale（需要 PyQt5.QtCore.QLocale）
        3. 默认 zh_CN

    返回:
        语言代码（如 "zh_CN"）

    说明（P3-5）:
        - 本函数独立处理 PyQt5 缺失的异常：
          若 PyQt5 不可用，仍会安全返回默认语言 zh_CN，
          不会向上层抛出。
        - 抽成独立函数后，setup_locale 主流程和 gettext 回退
          路径共享同一探测逻辑，避免重复代码。
    """
    # ---- 1. 用户设置 ----
    try:
        from PyQt5.QtCore import QSettings
        settings = QSettings(ORG_NAME, "Editor")
        lang = settings.value("language", "", type=str)
        if lang:
            return lang
    except ImportError:
        # PyQt5 不可用：跳过用户设置探测
        pass
    except Exception:
        # QSettings 读取失败：继续尝试系统 locale
        pass

    # ---- 2. 系统 locale ----
    # P7 接线：language_auto_detect 之前零读取。关闭后不再按系统
    # locale 猜测语言，直接使用默认值（用户在首选项里手选的语言
    # 已在第 1 步返回）。
    auto_detect = True
    try:
        from PyQt5.QtCore import QSettings

        auto_detect = QSettings(ORG_NAME, "Editor").value(
            "language_auto_detect", True, type=bool
        )
    except Exception:
        auto_detect = True

    if not auto_detect:
        return "zh_CN"

    try:
        from PyQt5.QtCore import QLocale
        sys_locale = QLocale.system().name()
        if sys_locale.startswith("zh"):
            return "zh_CN"
        if sys_locale.startswith("ja"):
            return "ja_JP"
        if sys_locale.startswith("ko"):
            return "ko_KR"
        if sys_locale.startswith("es"):
            return "es_ES"
        return "zh_CN"
    except ImportError:
        # PyQt5 不可用：直接使用默认
        pass
    except Exception:
        pass

    # ---- 3. 默认 ----
    return "zh_CN"


def setup_locale():
    """
    设置国际化。

    流程:
        1. 探测目标语言（_detect_language，独立处理异常）
        2. 尝试使用 core.i18n 加载
        3. 若 core.i18n 不可用或加载失败，回退到 gettext

    修复说明（P3-5）:
        - 原实现把"PyQt5 缺失"和"core.i18n 导入失败"混在同一个
          try 里处理，一旦 PyQt5 缺失，回退路径中的
          `from PyQt5.QtCore import ...` 会再次失败，导致整个
          函数在 fallback 里也崩溃。
        - 现拆分为 _detect_language 与 setup_locale 两个步骤，
          各步骤独立处理自身异常，互不影响。
        - 语言探测逻辑抽成 _detect_language，避免重复。
    """
    # ---- 第 1 步：探测语言 ----
    lang = _detect_language()

    # ---- 第 2 步：尝试 core.i18n ----
    try:
        from core.i18n import get_i18n
    except ImportError as e:
        print(f"[国际化] core.i18n 不可用，回退 gettext: {e}")
    else:
        try:
            i18n = get_i18n()
            i18n.locale_dir = LOCALE_DIR
            i18n.load(lang)
            print(f"[国际化] 已加载语言（core.i18n）: {lang}")
            return
        except Exception as e:
            print(f"[国际化] core.i18n 加载失败，回退 gettext: {e}")

    # ---- 第 3 步：回退 gettext ----
    try:
        import gettext

        # 尝试加载指定语言的翻译
        try:
            tr = gettext.translation(
                "qingcao", LOCALE_DIR, languages=[lang]
            )
            tr.install()
            print(f"[国际化] 已加载语言（gettext）: {lang}")
            return
        except FileNotFoundError:
            # 翻译文件不存在：安装 gettext 但使用原文
            try:
                gettext.install("qingcao", LOCALE_DIR)
            except Exception:
                try:
                    gettext.install("qingcao")
                except Exception:
                    pass
            print(f"[国际化] 未找到 {lang} 翻译文件，使用内置文本")
            return
        except Exception as e:
            print(f"[国际化] gettext 加载失败: {e}")
            # 最终兜底：尝试安装默认 gettext
            try:
                gettext.install("qingcao")
            except Exception:
                pass
    except Exception as e:
        # gettext 模块本身不可用（极少见）
        print(f"[国际化] gettext 不可用，跳过国际化: {e}")


# ============================================================
# 日志系统（带轮转）
# ============================================================
def _log_settings():
    """
    读取日志相关偏好（P7 接线）。

    返回:
        (level_name, max_bytes)

    说明（P7）:
        log_level / log_max_size 两个键此前只在首选项里存在，
        setup_logging() 永远使用硬编码的 INFO 与 LOG_MAX_SIZE
        （10MB），用户改了没有反应。debug_mode 作为最高优先级
        覆盖（True 时强制 DEBUG）。
    """
    level_name = "INFO"
    max_bytes = LOG_MAX_SIZE
    try:
        from PyQt5.QtCore import QSettings

        settings = QSettings(ORG_NAME, "Editor")
        raw = settings.value("log_level", "INFO", type=str) or "INFO"
        if str(raw).upper() in ("DEBUG", "INFO", "WARNING",
                                "ERROR", "CRITICAL"):
            level_name = str(raw).upper()
        if settings.value("debug_mode", False, type=bool):
            level_name = "DEBUG"
        mb = settings.value("log_max_size", 10, type=int)
        if mb and int(mb) > 0:
            max_bytes = int(mb) * 1024 * 1024
    except Exception:
        pass
    return level_name, max_bytes


def setup_logging():
    """初始化运行日志（含简单轮转）"""
    import logging

    # P7：log_level / log_max_size / debug_mode 现在真正生效
    level_name, max_bytes = _log_settings()
    level = getattr(logging, level_name, logging.INFO)

    os.makedirs(LOGS_DIR, exist_ok=True)

    # 日志轮转：超过 max_bytes 则重命名
    try:
        if os.path.exists(RUNTIME_LOG) and \
                os.path.getsize(RUNTIME_LOG) > max_bytes:
            backup = RUNTIME_LOG + ".1"
            if os.path.exists(backup):
                try:
                    os.remove(backup)
                except Exception:
                    pass
            shutil.move(RUNTIME_LOG, backup)
    except Exception:
        pass

    logger = logging.getLogger("QingCao")
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 文件处理器
    try:
        fh = logging.FileHandler(RUNTIME_LOG, encoding="utf-8")
        fh.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass

    # 控制台处理器
    try:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)
    except Exception:
        pass

    return logger


# ============================================================
# 全局异常处理（含崩溃上报）
# ============================================================
def exception_hook(exc_type, exc_value, exc_tb):
    """
    全局未捕获异常处理：
    - 将完整堆栈写入 crash.log
    - 调用崩溃上报器（弹对话框、收集上下文、生成 GitHub Issue URL）
    """
    tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1) 写入崩溃日志
    try:
        with open(CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 70}\n")
            f.write(f"崩溃时间: {timestamp}\n")
            f.write(f"版本: {__version__}\n")
            f.write(f"平台: {sys.platform}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"{'=' * 70}\n")
            f.write(tb_str)
            f.write(f"{'=' * 70}\n")
    except Exception as log_err:
        try:
            print(f"无法写入崩溃日志: {log_err}", file=sys.stderr)
        except Exception:
            pass

    # 2) 控制台输出
    try:
        print(tb_str, file=sys.stderr)
    except Exception:
        pass

    # 3) 崩溃上报器（首选）
    try:
        from core.crash_reporter import get_crash_reporter
        reporter = get_crash_reporter(__version__)
        reporter.show_crash_dialog(
            None, (exc_type, exc_value, exc_tb)
        )
        return
    except Exception as report_err:
        try:
            print(f"[Crash] 上报器不可用: {report_err}", file=sys.stderr)
        except Exception:
            pass

    # 4) 回退：简单 QMessageBox
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("青草编辑器 - 错误")
            msg_box.setText("程序遇到未预期的错误")
            msg_box.setInformativeText(
                f"错误信息：{exc_value}\n\n"
                f"详细堆栈已记录到：\n{CRASH_LOG}\n\n"
                # F821 修复：此处原为 {__email}，但 __email 是模块级
                # 变量、在函数内不可见（会 NameError 掩盖真实异常）
                f"请将日志文件发送至 {globals().get('__email', '')} "
                f"以帮助我们改进。"
            )
            msg_box.setDetailedText(tb_str)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec_()
    except Exception:
        pass


sys.excepthook = exception_hook


# ============================================================
# 退出钩子
# ============================================================
@atexit.register
def _on_exit():
    """进程退出时输出日志标记"""
    try:
        import logging
        logging.getLogger("QingCao").info("进程退出 (atexit)")
    except Exception:
        pass


# ============================================================
# 崩溃恢复检测（旧版 backup/autosave_*）
# ============================================================
def check_crash_recovery():
    """
    检查上次是否有未正常退出的备份目录（backup/autosave_*）。
    返回备份目录路径或 None。
    """
    if not os.path.exists(BACKUP_DIR):
        return None

    backup_dirs = []
    try:
        for name in os.listdir(BACKUP_DIR):
            path = os.path.join(BACKUP_DIR, name)
            if os.path.isdir(path) and name.startswith("autosave_"):
                files = [f for f in os.listdir(path) if f.endswith(".tmp")]
                if files:
                    backup_dirs.append(
                        (path, len(files), os.path.getmtime(path))
                    )
    except Exception:
        return None

    if not backup_dirs:
        return None

    # 取最新的一个
    backup_dirs.sort(key=lambda x: x[2], reverse=True)
    latest_path, file_count, _ = backup_dirs[0]

    msg = (f"检测到上次未正常退出，共有 {file_count} 个文件可恢复。\n"
           f"是否尝试恢复这些文件？\n\n"
           f"备份位置：{latest_path}")

    try:
        from PyQt5.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            None, "崩溃恢复", msg,
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Discard
        )

        if reply == QMessageBox.Yes:
            return latest_path
        elif reply == QMessageBox.Discard:
            shutil.rmtree(latest_path, ignore_errors=True)
            return None
    except Exception:
        pass

    return None


# ============================================================
# 草稿恢复（P0-2：补齐"只写不读"的读取端）
# ============================================================
def _render_recovered_drafts(window) -> int:
    """把"草稿恢复"新建标签里的正文真正显示出来（P0-2）

    跨模块缺口（已核实，这是本函数存在的唯一理由）:
        `SessionManager.check_and_recover_drafts()` 用
        `EditorWidget(provider=MemoryProvider(草稿正文))` 建标签，但
        `EditorWidget.__init__` **不会**把 provider 的正文灌进 QScintilla
        —— 只有 `proxy.open_file()` / `proxy.set_text()` 才会。
        结果是：恢复出来的标签页是**空白**的，用户以为"没恢复成功"，
        而草稿还留在磁盘上（下次启动再弹一次）。
        `app/session.py` 不在本次修复的写入范围内，因此在**调用侧**补一步。

    安全约束：只处理标题带 "[未保存]"（check_and_recover_drafts 的固定
    后缀）且"编辑器缓冲区为空、provider 有正文"的标签，不碰其它标签。
    """
    tabs = getattr(window, 'tabs', None)
    if tabs is None:
        return 0

    fixed = 0
    try:
        count = tabs.count()
    except Exception:
        return 0

    for i in range(count):
        try:
            widget = tabs.widget(i)
            if widget is None:
                continue
            try:
                title = tabs.tabText(i) or ""
            except Exception:
                title = ""
            if "[未保存]" not in title:
                continue

            proxy = getattr(widget, 'proxy', None)
            if proxy is None:
                continue
            sc = getattr(proxy, 'sc', None)
            if sc is None or sc.text():
                continue

            provider = getattr(
                getattr(proxy, 'document', None), 'provider', None
            )
            if provider is None or not getattr(provider, 'is_open', False):
                continue
            text = provider.read_text()
            if not text:
                continue

            # set_text 同时把 proxy 标记为已修改（modified_changed 发射），
            # 使恢复出来的内容重新纳入自动备份，不会二次丢失。
            proxy.set_text(text)
            fixed += 1
        except Exception as e:
            print(f"[草稿恢复] 渲染标签失败: {e}")

    return fixed


def _notify_draft_recovery(window, drafts, restored: int):
    """草稿恢复后的可见提示（P0-2）

    缺陷背景（已核实）:
        `check_and_recover_drafts()` 原先**零调用点**——读取端存在但从不
        执行，用户只能自己去 backup/drafts 里翻文件。
        补上调用后，还必须把两种"看起来像没恢复"的情况说清楚：
          * 原文件已删除 / 本来未命名（草稿里的 Original 为空或不存在）：
            这类内容没有可回写的磁盘路径，恢复出来是"[未保存]"缓冲区，
            必须提示用户用「文件 → 另存为」保存；
          * 恢复的标签**不带 '*' 脏标记**（`app/session.py` 里
            `proxy.is_modified = True` 是对只读 property 赋值，会抛异常并
            被它自己的 try/except 吞掉）——所以要明确告诉用户"内容在这里、
            需要手动保存"。
    """
    try:
        from PyQt5.QtWidgets import QMessageBox
    except Exception:
        return

    try:
        orphans = []
        for d in drafts or []:
            original = (d or {}).get('original') or ""
            if not original:
                orphans.append("(未命名)")
            elif not os.path.exists(original):
                orphans.append(original)

        lines = [
            f"已恢复 {restored} 项未保存内容，均以「[未保存]」标签打开。",
            "确认内容后请使用「文件 → 另存为」写入磁盘。",
        ]
        if orphans:
            preview = "\n".join("  · %s" % p for p in orphans[:8])
            more = "" if len(orphans) <= 8 else \
                "\n  … 另有 %d 项" % (len(orphans) - 8)
            lines.append("")
            lines.append("以下内容没有可回写的原文件"
                         "（未命名或原文件已不存在）：")
            lines.append(preview + more)

        QMessageBox.information(window, "草稿恢复", "\n".join(lines))
    except Exception as e:
        print(f"[草稿恢复] 提示失败: {e}")


# ============================================================
# 启动画面
# ============================================================
def create_splash():
    """创建启动画面"""
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPixmap
    from PyQt5.QtWidgets import QSplashScreen

    splash_path = os.path.join(RESOURCES_DIR, "splash.png")

    if os.path.exists(splash_path):
        pixmap = QPixmap(splash_path)
    else:
        # 生成默认启动画面
        pixmap = QPixmap(480, 260)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)

        # 渐变背景
        gradient = QLinearGradient(0, 0, 0, 260)
        gradient.setColorAt(0, QColor("#1e3a5f"))
        gradient.setColorAt(1, QColor("#0d1f33"))
        painter.fillRect(0, 0, 480, 260, QBrush(gradient))

        # 标题
        painter.setPen(QColor("#7ec850"))
        font = QFont("Microsoft YaHei", 32, QFont.Bold)
        painter.setFont(font)
        painter.drawText(0, 0, 480, 260, Qt.AlignCenter, "青草编辑器")

        # 副标题
        painter.setPen(QColor("#a0a0a0"))
        font2 = QFont("Microsoft YaHei", 11)
        painter.setFont(font2)
        painter.drawText(0, 160, 480, 40, Qt.AlignCenter,
                          "青草枯荣 · 野火重生")

        painter.end()

    splash = QSplashScreen(pixmap)
    splash.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    splash.setAttribute(Qt.WA_TranslucentBackground)
    return splash


# ============================================================
# 主题加载
# ============================================================
def load_theme(app):
    """加载全局样式表"""
    # 修复: 优先从 QSettings 的 theme_name 恢复主题
    # 原实现只读 theme_path，但 theme_path 默认指向
    # resources/qingcao_theme.qss（空注释），导致每次启动 QSS 为空。
    try:
        from PyQt5.QtCore import QSettings

        from infrastructure.theme_loader import ThemeLoader

        settings = QSettings(ORG_NAME, "Editor")
        theme_name = settings.value("theme_name", "", type=str)

        if theme_name:
            loader = ThemeLoader()
            theme = loader.load_by_name(theme_name)
            if theme is not None:
                loader.apply_qss(app, theme)
                print(f"[主题] 已应用: {theme.name} "
                      f"({theme.display_name or theme.name})")
                return
            else:
                print(f"[主题] 未找到主题: {theme_name}，"
                      f"回退到 qss 文件")
    except Exception as e:
        print(f"[主题] 从 theme_name 恢复失败: {e}")

    # 回退：原逻辑（读 theme_path 或默认 QSS）
    theme_path = DEFAULT_THEME
    try:
        from PyQt5.QtCore import QSettings
        settings = QSettings(ORG_NAME, "Editor")
        custom_theme = settings.value("theme_path", "", type=str)
        if custom_theme and os.path.exists(custom_theme):
            theme_path = custom_theme
    except Exception:
        pass

    if os.path.exists(theme_path):
        try:
            content = open(theme_path, encoding='utf-8').read()
            if content.strip() and not content.strip().startswith('/*'):
                app.setStyleSheet(content)
                print(f"[主题] 已加载文件: {theme_path}")
            else:
                # 文件为空或仅注释 → 回退到内置暗夜
                _apply_fallback_dark(app)
        except Exception as e:
            print(f"[主题] 加载失败: {e}")
            _apply_fallback_dark(app)
    else:
        _apply_fallback_dark(app)


def _apply_fallback_dark(app):
    """应用内置默认暗色主题（无主题文件时）"""
    app.setStyleSheet("""
        QMainWindow { background-color: #1e1e1e; color: #d4d4d4; }
        QMenuBar { background-color: #252526; color: #d4d4d4; }
        QMenuBar::item:selected { background-color: #094771; }
        QMenu { background-color: #2d2d2d; color: #d4d4d4;
                border: 1px solid #3c3c3c; }
        QMenu::item:selected { background-color: #094771; }
        QToolBar { background-color: #252526; border: none; }
        QStatusBar { background-color: #007acc; color: white; }
        QTabWidget::pane { border: 0; }
        QTabBar::tab { background-color: #2d2d2d; color: #cccccc;
                        padding: 6px 12px; }
        QTabBar::tab:selected { background-color: #1e1e1e;
                                 color: white; }
    """)


# ============================================================
# 应用图标
# ============================================================
def set_app_icon(app):
    """设置应用图标"""
    from PyQt5.QtGui import QIcon

    icon_paths = [
        os.path.join(RESOURCES_DIR, "icons", "qingcao.png"),
        os.path.join(RESOURCES_DIR, "icons", "qingcao.ico"),
        os.path.join(RESOURCES_DIR, "qingcao.png"),
        os.path.join(RESOURCES_DIR, "qingcao.ico"),
    ]

    for path in icon_paths:
        if os.path.exists(path):
            app.setWindowIcon(QIcon(path))
            return


# ============================================================
# 命令行参数处理
# ============================================================
def parse_arguments(argv):
    """
    解析命令行参数：
    - 文件路径：打开指定文件
    - --no-splash：不显示启动画面
    - --version：显示版本
    - --help：帮助信息
    - --project FILE：打开项目
    - --new-window：新窗口启动（预留）
    """
    args = {
        'files': [],
        'no_splash': False,
        'version': False,
        'help': False,
        'project': None,
        'new_window': False,
    }

    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == '--new-window':
            args['new_window'] = True
        elif arg == '--no-splash':
            args['no_splash'] = True
        elif arg in ('--version', '-v'):
            args['version'] = True
        elif arg in ('--help', '-h'):
            args['help'] = True
        elif arg == '--project' and i + 1 < len(argv):
            args['project'] = argv[i + 1]
            i += 1
        elif not arg.startswith('-'):
            args['files'].append(arg)
        i += 1

    return args


def print_help():
    """打印帮助信息"""
    help_text = f"""
{APP_NAME} v{__version__}
{APP_NAME_EN}

用法: python main.py [选项] [文件...]

选项:
  --no-splash       不显示启动画面
  --new-window      新开独立实例（独立会话与配置）
  --project FILE    打开指定的 .qingcao-project 项目文件
  --version, -v     显示版本信息
  --help, -h        显示此帮助信息

示例:
  python main.py                       # 启动编辑器
  python main.py file.txt              # 打开 file.txt
  python main.py a.py b.py             # 同时打开多个文件
  python main.py --project my.qingcao-project  # 打开项目

开发者: {__author__}
邮箱: {__email__}

青草枯荣，野火重生。
"""
    print(help_text)


def print_version():
    """打印版本信息"""
    print(f"{APP_NAME} v{__version__}")
    print(f"{APP_NAME_EN}")
    print(f"开发者: {__author__}")
    print(f"邮箱: {__email__}")
    print(f"Python: {sys.version.split()[0]}")

    try:
        from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        print(f"Qt: {QT_VERSION_STR}")
        print(f"PyQt5: {PYQT_VERSION_STR}")
    except Exception:
        pass

    try:
        from PyQt5.Qsci import QSCINTILLA_VERSION_STR
        print(f"QScintilla: {QSCINTILLA_VERSION_STR}")
    except Exception:
        pass

    # 可选依赖
    for mod in ['chardet', 'requests', 'psutil']:
        try:
            m = __import__(mod)
            v = getattr(m, '__version__', '?')
            print(f"{mod}: {v}")
        except ImportError:
            print(f"{mod}: 未安装")

    print("青草枯荣，野火重生。")


# ============================================================
# 主函数
# ============================================================
def main():
    """应用入口"""
    # --------------------------------------------------------
    # 1. 解析命令行参数
    # --------------------------------------------------------
    args = parse_arguments(sys.argv)
    if args.get('new_window'):
        # 多实例：新窗口使用独立会话文件与设置目录
        os.environ['QINGCAO_NEW_WINDOW'] = '1'

    if args['help']:
        print_help()
        return 0

    if args['version']:
        print_version()
        return 0

    # --------------------------------------------------------
    # 2. 确保目录存在
    # --------------------------------------------------------
    ensure_directories()

    # --------------------------------------------------------
    # 3. 便携模式
    # --------------------------------------------------------
    setup_portable_mode()

    # --------------------------------------------------------
    # 4. 日志系统
    # --------------------------------------------------------
    logger = setup_logging()
    logger.info(f"{APP_NAME} v{__version__} 启动")
    logger.info(f"Python: {sys.version}")
    logger.info(f"平台: {sys.platform}")
    logger.info(f"工作目录: {os.getcwd()}")

    # --------------------------------------------------------
    # 5. 国际化
    # --------------------------------------------------------
    setup_locale()

    # --------------------------------------------------------
    # 6. 创建 QApplication
    # --------------------------------------------------------
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QApplication, QMessageBox, QWizard

    # 高 DPI 支持（必须在 QApplication 创建前）
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(ORG_NAME)
    app.setOrganizationDomain(ORG_DOMAIN)

    # --------------------------------------------------------
    # P0 修复：主窗口关闭时退出事件循环
    # --------------------------------------------------------
    # 说明：
    #   - 原实现为 setQuitOnLastWindowClosed(False)，依赖
    #     MainWindow.closeEvent 显式调用 QApplication.quit()，
    #     但 closeEvent 中并未调用，导致应用"关不掉"。
    #   - 这里改为 True，使关闭最后一个顶层窗口即退出。
    #   - 同时 MainWindow.closeEvent 中也会显式 quit()（双保险），
    #     以覆盖"关闭主窗口时仍有其他 QDialog 存在"的边缘场景。
    app.setQuitOnLastWindowClosed(True)

    # --------------------------------------------------------
    # 7. 设置图标
    # --------------------------------------------------------
    set_app_icon(app)

    # --------------------------------------------------------
    # 8. 加载主题
    # --------------------------------------------------------
    load_theme(app)

    # --------------------------------------------------------
    # 9. 启动画面
    # --------------------------------------------------------
    splash = None
    splash_started = 0.0
    # P7 接线：splash_screen 之前只在首选项面板里读写，main.py 无条件
    # 创建启动画面（只有命令行 --no-splash 能关掉）。
    if not args['no_splash'] and bool(_pref("splash_screen", True)):
        try:
            splash = create_splash()
            splash_started = time.monotonic()
            splash.show()
            splash.showMessage(
                f"正在启动 {APP_NAME} v{__version__}...",
                Qt.AlignBottom | Qt.AlignHCenter,
                Qt.white
            )
            app.processEvents()
        except Exception as e:
            print(f"[启动画面] 创建失败: {e}")
            splash = None

    # --------------------------------------------------------
    # 10. 崩溃恢复检测（旧版 backup/autosave_*）
    # --------------------------------------------------------
    recovery_dir = None
    if splash:
        splash.showMessage("检查上次退出状态...",
                            Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        app.processEvents()

    try:
        recovery_dir = check_crash_recovery()
    except Exception as e:
        logger.error(f"崩溃恢复检测失败: {e}")
        recovery_dir = None

    # --------------------------------------------------------
    # 11. 导入主窗口
    # --------------------------------------------------------
    if splash:
        splash.showMessage("加载主界面...",
                            Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        app.processEvents()

    try:
        from ui.main_window import MainWindow
    except ImportError as e:
        logger.error(f"无法导入主窗口: {e}")
        traceback.print_exc()
        QMessageBox.critical(
            None, "启动失败",
            f"无法加载主窗口模块：\n{e}\n\n"
            f"请确认项目文件完整，且已安装依赖：\n"
            f"pip install PyQt5 QScintilla chardet requests psutil"
        )
        return 1

    # --------------------------------------------------------
    # 12. 创建主窗口
    # --------------------------------------------------------
    try:
        window = MainWindow()
    except Exception as e:
        logger.error(f"创建主窗口失败: {e}")
        tb = traceback.format_exc()
        traceback.print_exc()
        QMessageBox.critical(
            None, "启动失败",
            f"创建主窗口时发生错误：\n{e}\n\n{tb}"
        )
        return 1

    # --------------------------------------------------------
    # 13. 处理启动参数中的文件
    # --------------------------------------------------------
    # 13a. 把已保存主题应用到**面板**（修复"面板永远深色"）
    #
    # 顺序很重要：必须在打开文件之前 —— 打开文件会创建编辑器标签，
    # 而主题里包含 Scintilla 的字体/配色应用。
    try:
        if hasattr(window, 'apply_startup_theme'):
            _theme = window.apply_startup_theme()
            if _theme is not None:
                logger.info("启动主题已应用到面板: %s", getattr(
                    _theme, 'name', ''))
    except Exception as _e:
        logger.warning("启动主题应用到面板失败: %s", _e)

    if args['files']:
        for filepath in args['files']:
            abs_path = os.path.abspath(filepath)
            if os.path.exists(abs_path):
                try:
                    window.tabs.open_file(abs_path)
                    logger.info(f"已打开文件: {abs_path}")
                except Exception as e:
                    logger.error(f"打开文件失败 {abs_path}: {e}")
            else:
                logger.warning(f"文件不存在: {abs_path}")

    # --------------------------------------------------------
    # 14. 处理项目参数
    # --------------------------------------------------------
    if args['project']:
        try:
            if hasattr(window, 'open_project'):
                window.open_project(args['project'])
                logger.info(f"已打开项目: {args['project']}")
        except Exception as e:
            logger.error(f"打开项目失败: {e}")

    # --------------------------------------------------------
    # 15. 处理旧版崩溃恢复
    # --------------------------------------------------------
    # B2 修复：改用 SessionManager.check_and_recover_crash
    # 原实现调 window.recover_from_backup，但 MainWindow 从未定义
    # 该方法，hasattr 恒为 False，恢复被静默跳过。
    if recovery_dir:
        try:
            sess = getattr(window, 'session', None)
            if sess is not None and hasattr(sess, 'check_and_recover_crash'):
                count = sess.check_and_recover_crash(
                    parent=window, auto_save_dir=recovery_dir
                )
                if count > 0:
                    logger.info(f"已从备份恢复 {count} 个文件")
            else:
                logger.warning("SessionManager 不可用，跳过崩溃恢复")
        except Exception as e:
            logger.error(f"崩溃恢复失败: {e}")

    # --------------------------------------------------------
    # 16. 首次启动向导
    # --------------------------------------------------------
    try:
        from ui.first_run_wizard import (
            FirstRunWizard,
            apply_wizard_settings,
            mark_wizard_completed,
            should_show_wizard,
        )

        if should_show_wizard():
            if splash:
                splash.showMessage("首次启动配置...",
                                    Qt.AlignBottom | Qt.AlignHCenter,
                                    Qt.white)
                app.processEvents()

            wizard = FirstRunWizard(window)
            if wizard.exec_() == QWizard.Accepted:
                try:
                    apply_wizard_settings(wizard)
                except Exception as e:
                    logger.error(f"应用向导配置失败: {e}")
                mark_wizard_completed()
                logger.info("首次启动向导完成")
            else:
                logger.info("首次启动向导被取消")
                # 用户取消也标记为已完成，避免每次启动都弹
                mark_wizard_completed()
    except ImportError:
        logger.warning("首次启动向导模块不可用")
    except Exception as e:
        logger.error(f"首次启动向导失败: {e}")

    # --------------------------------------------------------
    # 17. 显示主窗口
    # --------------------------------------------------------
    window.show()

    # 诊断钩子（仅在 QINGCAO_STARTUP_DIAG=1 时写文件；不影响正常运行）
    #
    # 用途：排查"打包版状态栏/面板样式与源码版不一致"这类**只在打包产物中
    # 出现**的问题时，需要从被冻结的进程里拿到真实 UI 状态。
    # 用环境变量门控，避免日常运行产生多余文件。
    if os.environ.get("QINGCAO_STARTUP_DIAG") == "1":
        try:
            from PyQt5.QtWidgets import QDockWidget as _QDW
            app.processEvents()
            sb = window.statusBar()
            lines = [
                "frozen=%r" % getattr(sys, "frozen", False),
                "window_size=%s" % (window.size(),),
                "statusBar_exists=%r" % (sb is not None),
                "statusBar_visible=%r" % (sb.isVisible() if sb else None),
                "statusBar_height=%r" % (sb.height() if sb else None),
                "statusBar_geometry=%s" % (sb.geometry() if sb else None),
                "theme_name=%r" % (
                    __import__("PyQt5.QtCore", fromlist=["QSettings"])
                    .QSettings(ORG_NAME, "Editor")
                    .value("theme_name", "", type=str)
                ),
                "startup_theme=%r" % getattr(
                    getattr(window, "_startup_theme", None), "name", None),
                "central_size=%s" % (window.centralWidget().size(),),
            ]
            for dock in window.findChildren(_QDW):
                lines.append(
                    "dock=%r visible=%r area=%r"
                    % (dock.objectName(), dock.isVisible(),
                       int(window.dockWidgetArea(dock)))
                )
            diag_path = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "startup_diag.txt")
            with open(diag_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            logger.info("启动诊断已写入: %s", diag_path)
        except Exception as _e:
            logger.warning("启动诊断失败: %s", _e)

    # 再次确保可见（某些 Qt 版本可能隐藏）
    if not window.isVisible():
        try:
            window.show()
            window.raise_()
            window.activateWindow()
        except Exception:
            pass

    # --------------------------------------------------------
    # 18. 关闭启动画面
    # --------------------------------------------------------
    # P7 接线：splash_duration（毫秒）之前零读取。
    # QSplashScreen 本身没有"显示时长"参数（构造函数只接受 QPixmap），
    # 因此这里实现为**最小可见时长**：主窗口已经就绪，但启动画面显示
    # 时间不足 splash_duration 时，用单次定时器延迟关闭，保证用户确实
    # 能看到它；否则立即关闭（不拖慢启动）。
    if splash:
        try:
            duration_ms = int(_pref("splash_duration", 800) or 0)
            elapsed_ms = int((time.monotonic() - splash_started) * 1000)
            remaining_ms = max(0, duration_ms - elapsed_ms)
            if remaining_ms > 0:
                QTimer.singleShot(
                    remaining_ms, lambda: splash.finish(window)
                )
            else:
                splash.finish(window)
        except Exception:
            try:
                splash.finish(window)
            except Exception:
                pass

    # --------------------------------------------------------
    # 19. 延迟初始化（会话恢复、更新检查、遥测等）
    # --------------------------------------------------------
    def deferred_init():
        """延迟初始化非关键组件"""
        logger.info("deferred_init 开始")
        try:
            # ---- 会话恢复 ----
            if hasattr(window, 'restore_session'):
                logger.debug("调用 restore_session...")
                try:
                    window.restore_session()
                    logger.debug("restore_session 完成")
                except Exception as e:
                    logger.error(f"会话恢复失败: {e}")

            # ---- 自动备份恢复（backup/autosave 目录） ----
            # B2 修复：同 B2-1，改用 SessionManager.check_and_recover_crash
            #
            # P1 修复：目录必须与**写入端**（SessionManager.AUTOSAVE_DIR）
            # 同一个来源。原实现用 `os.path.join(BACKUP_DIR, "autosave")`，
            # 与写入端可能不是同一路径，会出现"备份写了、恢复找不到"。
            try:
                from app.session import AUTOSAVE_DIR as _autosave_dir
                auto_backup = _autosave_dir
            except Exception:
                auto_backup = os.path.join(BACKUP_DIR, "autosave")
            try:
                meta_path = os.path.join(auto_backup, "meta.json")
                if os.path.isfile(meta_path):
                    sess = getattr(window, 'session', None)
                    if sess is not None and hasattr(
                        sess, 'check_and_recover_crash'
                    ):
                        count = sess.check_and_recover_crash(
                            parent=window, auto_save_dir=auto_backup
                        )
                        if count > 0:
                            logger.info(
                                f"已从自动备份恢复 {count} 个未保存文件"
                            )
            except Exception as e:
                logger.error(f"自动备份恢复失败: {e}")

            # ---- 草稿恢复（P0-2 修复）----
            #
            # 缺陷背景（真实缺陷，已核实）:
            #   生产者 `core/document.py::_save_draft` 每 60 秒把"未保存
            #   正文"写进 backup/drafts/*.draft（进程被杀也不会丢），
            #   但读取端 `SessionManager.check_and_recover_drafts()`
            #   **全仓零调用点** —— 只写不读，等价于没有备份。
            #   这里补上调用（parent=window 以弹出可见的确认框），
            #   并对"未命名 / 原文件已删除"的情况给出明确提示。
            try:
                sess = getattr(window, 'session', None)
                if sess is not None and hasattr(
                        sess, 'check_and_recover_drafts'):
                    drafts = []
                    try:
                        drafts = sess.find_recoverable_drafts()
                    except Exception as e:
                        logger.error(f"读取草稿失败: {e}")
                        drafts = []

                    if drafts:
                        logger.info(f"检测到 {len(drafts)} 项未保存草稿")
                        restored = sess.check_and_recover_drafts(
                            parent=window, drafts=drafts
                        )
                        if restored > 0:
                            # 补渲染：session 侧只把正文放进 provider，
                            # 不会显示出来（见 _render_recovered_drafts）
                            rendered = _render_recovered_drafts(window)
                            logger.info(
                                f"已恢复 {restored} 项未保存草稿"
                                f"（补渲染 {rendered} 项）"
                            )
                            _notify_draft_recovery(window, drafts, restored)
                            try:
                                window.status_bar.showMessage(
                                    f"已恢复 {restored} 项未保存内容", 6000
                                )
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"草稿恢复失败: {e}")

            # ---- 检查更新 ----
            try:
                prefs = getattr(window, 'prefs', None)
                check_update = True
                if prefs:
                    try:
                        check_update = prefs.get("check_update", True)
                    except Exception:
                        pass

                if check_update:
                    from core.updater import UpdateChecker, show_update_dialog
                    checker = UpdateChecker(__version__)

                    def _on_update(info):
                        try:
                            show_update_dialog(window, info)
                        except Exception as e:
                            logger.error(f"显示更新对话框失败: {e}")

                    checker.check_completed.connect(_on_update)
                    checker.check_async()
                    logger.debug("已启动更新检查")
            except ImportError:
                logger.warning("更新模块不可用")
            except Exception as e:
                logger.error(f"检查更新失败: {e}")

            # ---- 每日技巧 ----
            try:
                if hasattr(window, '_show_daily_tip'):
                    # 用 QTimer 延迟弹出，避免打断用户
                    QTimer.singleShot(3000, window._show_daily_tip)
            except Exception:
                pass

            # ---- 遥测：记录启动 ----
            try:
                from core.telemetry import get_telemetry
                telemetry = get_telemetry()
                telemetry.record_app_start()
                logger.debug("遥测记录完成")
            except ImportError:
                pass
            except Exception as e:
                logger.error(f"遥测失败: {e}")

            logger.info("延迟初始化完成")

        except Exception as e:
            logger.error(f"延迟初始化失败: {e}")
            import traceback
            traceback.print_exc()

    QTimer.singleShot(100, deferred_init)

    # --------------------------------------------------------
    # 插件加载自检报告（便于反馈"插件菜单不出现"这类问题）
    #
    # 为什么需要：打包后的程序是 GUI 模式（无控制台），插件加载信息
    # 全部走 print() —— 实测**无法从外部捕获**（stdout 重定向得到 0 字节）。
    # 所以主动把关键结论写成文件，用户只需把该文件发回即可定位问题。
    #
    # 报告路径：<ROOT_DIR>/plugin_report.txt
    #   冻结后 ROOT_DIR 是 _internal/，同时在 exe 同级再写一份副本。
    # --------------------------------------------------------
    def _write_plugin_report(elapsed: float = 0.0, attempts: int = 0):
        out = []
        try:
            import platform
            out.append("青草编辑器 插件加载自检报告")
            out.append("=" * 56)
            out.append("冻结运行   : %s" % bool(getattr(sys, "frozen", False)))
            out.append("可执行文件 : %s" % sys.executable)
            out.append("ROOT_DIR   : %s" % ROOT_DIR)
            out.append("PLUGINS_DIR: %s" % PLUGINS_DIR)
            out.append("插件目录存在: %s" % os.path.isdir(PLUGINS_DIR))
            out.append("Python     : %s" % platform.python_version())
            out.append("采样耗时   : %.1f 秒（轮询 %d 次后写出）"
                       % (elapsed, attempts))
            out.append("")

            pm = getattr(window, "plugin_manager", None)
            out.append("plugin_manager: %r" % (pm,))
            loader = getattr(pm, "loader", None)
            specs = getattr(loader, "specs", None) or {}
            out.append("发现插件数: %d" % len(specs))
            out.append("")
            out.append("插件状态:")
            for name in sorted(specs):
                sp = specs[name]
                inst = getattr(sp, "instance", None)
                st = getattr(sp, "state", None)
                out.append("  %-20s 状态=%-14s 实例=%s"
                           % (name, getattr(st, "name", st),
                              "有" if inst is not None else "无"))
            active = [n for n, s in specs.items()
                      if getattr(s, "instance", None) is not None]
            out.append("")
            out.append("已激活插件数: %d" % len(active))
            out.append("")

            out.append("工具菜单内容:")
            tools = None
            for a in window.menuBar().actions():
                if "工具" in a.text() and a.menu():
                    tools = a.menu()
                    break
            if tools is None:
                out.append("  （未找到工具菜单）")
            else:
                def walk(menu, depth):
                    for act in menu.actions():
                        nm = act.text().replace("&", "")
                        if act.menu():
                            out.append("  " * (depth + 1) + nm + "/")
                            walk(act.menu(), depth + 1)
                        else:
                            out.append("  " * (depth + 1) + nm)
                walk(tools, 0)
            out.append("")

            out.append("插件依赖模块可导入性:")
            for m in ("core.ai_client", "core.ai_cache", "core.ollama_client",
                      "ui.ai_inline_completer", "core.git_client",
                      "core.secure_storage", "infrastructure.plugin_loader"):
                try:
                    __import__(m)
                    out.append("  %-30s OK" % m)
                except Exception as e:
                    out.append("  %-30s 失败: %s: %s"
                               % (m, type(e).__name__, e))
        except Exception:
            import traceback
            out.append("生成报告时出错:")
            out.append(traceback.format_exc())

        text = "\n".join(out)
        targets = [os.path.join(ROOT_DIR, "plugin_report.txt")]
        try:
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            if os.path.normcase(exe_dir) != os.path.normcase(ROOT_DIR):
                targets.append(os.path.join(exe_dir, "plugin_report.txt"))
        except Exception:
            pass
        for dst in targets:
            try:
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(text)
                logger.info("插件报告已写出: %s" % dst)
            except Exception:
                pass

    # 插件由主窗口的 100ms 定时器加载。
    #
    # 关键（真实缺陷）：**不能用固定延时**。原先写死 6 秒，但冷启动耗时
    # 受磁盘、杀毒软件扫描（首次解压出 400+ 文件时尤其慢）影响可达十几秒。
    # 若报告在 `_load_plugins` 完成前写出，就会记录成
    #   plugin_manager: <PluginManager total=0 active=0>
    # —— 看起来"插件全丢了"，实际只是**采样太早**。
    # 这正是用户反馈"每次打包都丢菜单"的来源之一。
    #
    # 改为**轮询等待插件加载完成**（最多 60 秒），并在报告里写明实际耗时，
    # 便于区分"加载失败"与"采样过早"。
    _report_state = {"attempts": 0, "started": time.time()}
    _report_timer = QTimer()

    def _poll_and_report():
        _report_state["attempts"] += 1
        pm = getattr(window, "plugin_manager", None)
        loader = getattr(pm, "loader", None)
        specs = getattr(loader, "specs", None) or {}
        elapsed = time.time() - _report_state["started"]

        # 已加载出插件 → 立即写报告；否则继续等（最多 60 秒）
        if specs or elapsed >= 60.0:
            _report_timer.stop()
            _write_plugin_report(elapsed, _report_state["attempts"])
        else:
            _report_timer.start(500)

    _report_timer.setSingleShot(True)
    _report_timer.timeout.connect(_poll_and_report)
    _report_timer.start(1000)

    # --------------------------------------------------------
    # 20. 进入事件循环
    # --------------------------------------------------------
    logger.info("即将进入事件循环")
    exit_code = app.exec_()
    logger.info(f"事件循环结束，exit_code={exit_code}")

    # --------------------------------------------------------
    # 21. 退出前清理
    # --------------------------------------------------------
    try:
        # 保存遥测
        try:
            from core.telemetry import get_telemetry
            get_telemetry()._save_stats()
        except Exception:
            pass

        # 清理自动备份（正常退出后不再需要）
        try:
            if hasattr(window, 'session') and window.session:
                window.session.clear_autosave()
        except Exception:
            pass

        # 关闭窗口
        try:
            if window and window.isVisible():
                window.close()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"退出清理失败: {e}")

    logger.info(f"{APP_NAME} 退出，代码: {exit_code}")
    return exit_code


# ============================================================
# 程序入口
# ============================================================
if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断，退出。")
        sys.exit(130)
    except Exception:
        # 最后的防线
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            with open(CRASH_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 70}\n")
                f.write(f"启动失败: {datetime.datetime.now()}\n")
                f.write(tb)
                f.write(f"{'=' * 70}\n")
        except Exception:
            pass
        sys.exit(1)