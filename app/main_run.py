# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""主启动流程（v2.24 从 main.py 拆出）。"""

from app.main_common import *  # noqa: F401,F403
from app.main_helpers import *  # noqa: F401,F403


def main():
    """应用入口"""
    # --------------------------------------------------------
    # 1. 解析命令行参数
    # --------------------------------------------------------
    args = parse_arguments(sys.argv)
    if args.get("new_window"):
        # 多实例：新窗口使用独立会话文件与设置目录
        os.environ["QINGCAO_NEW_WINDOW"] = "1"

    if args["help"]:
        print_help()
        return 0

    if args["version"]:
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
    try:
        from ui.i18n_widgets import install_ui_translators

        install_ui_translators(app)
    except Exception:
        pass

    if not args.get("new_window"):
        try:
            from infrastructure.instance_broadcast import try_focus_existing

            if try_focus_existing():
                return 0
        except Exception:
            pass
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
    if not args["no_splash"] and bool(_pref("splash_screen", True)):
        try:
            splash = create_splash()
            splash_started = time.monotonic()
            splash.show()
            splash.showMessage(
                f"正在启动 {APP_NAME} v{__version__}...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white
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
        splash.showMessage("检查上次退出状态...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
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
        splash.showMessage("加载主界面...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        app.processEvents()

    try:
        from ui.main_window import MainWindow
    except ImportError as e:
        logger.error(f"无法导入主窗口: {e}")
        traceback.print_exc()
        QMessageBox.critical(
            None,
            "启动失败",
            f"无法加载主窗口模块：\n{e}\n\n"
            f"请确认项目文件完整，且已安装依赖：\n"
            f"pip install PyQt5 QScintilla chardet requests psutil",
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
        QMessageBox.critical(None, "启动失败", f"创建主窗口时发生错误：\n{e}\n\n{tb}")
        return 1

    # --------------------------------------------------------
    # 13. 处理启动参数中的文件
    # --------------------------------------------------------
    # 13a. 把已保存主题应用到**面板**（修复"面板永远深色"）
    #
    # 顺序很重要：必须在打开文件之前 —— 打开文件会创建编辑器标签，
    # 而主题里包含 Scintilla 的字体/配色应用。
    # v2.19: 启动时恢复未完成的 mmap 增量保存（journal）
    try:
        from core.mmap_save import recover_pending_journals

        _n = recover_pending_journals()
        if _n:
            print(f"[mmap-save] 已恢复 {_n} 个未完成保存")
    except Exception:
        pass

    try:
        if hasattr(window, "apply_startup_theme"):
            _theme = window.apply_startup_theme()
            if _theme is not None:
                logger.info("启动主题已应用到面板: %s", getattr(_theme, "name", ""))
    except Exception as _e:
        logger.warning("启动主题应用到面板失败: %s", _e)

    # 高对比度自动适配（v2.13.0 P0）
    try:
        window.apply_high_contrast_if_needed()
    except Exception:
        pass

    # 无障碍：字体缩放 + 可访问名称（v2.17）
    try:
        window.apply_accessibility_settings()
        from ui.accessibility import apply_accessible_descriptions

        apply_accessible_descriptions(window)
        from PyQt5.QtWidgets import QApplication as _QApp

        from ui.accessibility import focus_ring_qss as _focus

        _app = _QApp.instance()
        if _app is not None:
            _app.setStyleSheet((_app.styleSheet() or "") + _focus())
    except Exception:
        pass

    if args["files"]:
        for filepath in args["files"]:
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
    if args["project"]:
        try:
            if hasattr(window, "open_project"):
                window.open_project(args["project"])
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
            sess = getattr(window, "session", None)
            if sess is not None and hasattr(sess, "check_and_recover_crash"):
                count = sess.check_and_recover_crash(parent=window, auto_save_dir=recovery_dir)
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
                splash.showMessage("首次启动配置...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
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
                "theme_name=%r"
                % (
                    __import__("PyQt5.QtCore", fromlist=["QSettings"])
                    .QSettings(ORG_NAME, "Editor")
                    .value("theme_name", "", type=str)
                ),
                "startup_theme=%r" % getattr(getattr(window, "_startup_theme", None), "name", None),
                "central_size=%s" % (window.centralWidget().size(),),
            ]
            for dock in window.findChildren(_QDW):
                lines.append(
                    "dock=%r visible=%r area=%r"
                    % (dock.objectName(), dock.isVisible(), int(window.dockWidgetArea(dock)))
                )
            diag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "startup_diag.txt")
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
                QTimer.singleShot(remaining_ms, lambda: splash.finish(window))
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
            if hasattr(window, "restore_session"):
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
                    sess = getattr(window, "session", None)
                    if sess is not None and hasattr(sess, "check_and_recover_crash"):
                        count = sess.check_and_recover_crash(
                            parent=window, auto_save_dir=auto_backup
                        )
                        if count > 0:
                            logger.info(f"已从自动备份恢复 {count} 个未保存文件")
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
                sess = getattr(window, "session", None)
                if sess is not None and hasattr(sess, "check_and_recover_drafts"):
                    drafts = []
                    try:
                        drafts = sess.find_recoverable_drafts()
                    except Exception as e:
                        logger.error(f"读取草稿失败: {e}")
                        drafts = []

                    if drafts:
                        logger.info(f"检测到 {len(drafts)} 项未保存草稿")
                        restored = sess.check_and_recover_drafts(parent=window, drafts=drafts)
                        if restored > 0:
                            # 补渲染：session 侧只把正文放进 provider，
                            # 不会显示出来（见 _render_recovered_drafts）
                            rendered = _render_recovered_drafts(window)
                            logger.info(f"已恢复 {restored} 项未保存草稿（补渲染 {rendered} 项）")
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
                prefs = getattr(window, "prefs", None)
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
                    window._update_checker = checker  # 防 GC；退出时可 cancel
                    checker.check_when_idle()
                    logger.debug("已安排更新检查（界面空闲后执行）")
            except ImportError:
                logger.warning("更新模块不可用")
            except Exception as e:
                logger.error(f"检查更新失败: {e}")

            # ---- 每日技巧 ----
            try:
                if hasattr(window, "_show_daily_tip"):
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
            out.append("采样耗时   : %.1f 秒（轮询 %d 次后写出）" % (elapsed, attempts))
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
                out.append(
                    "  %-20s 状态=%-14s 实例=%s"
                    % (name, getattr(st, "name", st), "有" if inst is not None else "无")
                )
            active = [n for n, s in specs.items() if getattr(s, "instance", None) is not None]
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
            for m in (
                "core.ai_client",
                "core.ai_cache",
                "core.ollama_client",
                "ui.ai_inline_completer",
                "core.git_client",
                "core.secure_storage",
                "infrastructure.plugin_loader",
            ):
                try:
                    __import__(m)
                    out.append("  %-30s OK" % m)
                except Exception as e:
                    out.append("  %-30s 失败: %s: %s" % (m, type(e).__name__, e))
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
    if os.environ.get("QINGCAO_HEADLESS_SMOKE") == "1":
        # CI/AppImage 冒烟：启动流程跑通后自动退出
        from PyQt5.QtCore import QTimer

        QTimer.singleShot(2500, app.quit)

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
            if hasattr(window, "session") and window.session:
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
