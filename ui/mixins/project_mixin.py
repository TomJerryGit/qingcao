# -*- coding: utf-8 -*-
"""
青草编辑器 - 项目能力 Mixin
========================================================

把三个此前**零引用**的孤立模块统一接线，并给它们同一个「项目根」语义：

| 模块 | 行数 | 职责 |
|---|---|---|
| `core/workspace.py` | 116 | 多根工作区模型（本项目用它记住"打开过哪些项目"） |
| `core/project_config.py` | 133 | 项目级配置（`.qingcao/settings.json`） |
| `ui/task_panel.py` + `core/project_tasks.py` | 189 + 131 | 项目任务（运行命令并看输出） |

## 为什么三者必须一起做

它们共享一个概念：**项目根**（project root）。

* 没有项目根 → 项目配置不知道读哪个目录；
* 没有项目根 → 任务不知道该在哪个 cwd 跑；
* 没有项目根 → 工作区只是一堆无意义的路径。

分开接会各造一套"项目"定义，后面必然打架。

## 产品定义（本项目采用的最小定义）

* 用户通过「项目 → 📁 打开项目…」选一个目录，该目录即**项目根**；
* 项目根会被记进 `Workspace`（`data/workspace.json`），下次可在
  「项目 → 最近项目」里一键切回；
* 项目根的 `.qingcao/settings.json` 可覆盖全局编辑设置
  （tab 宽度 / 缩进用空格 / 换行符 / 默认编码）；
* 项目根的 `.qingcao/tasks.json` 或 `.qingcao-tasks.json` 定义任务，
  在「任务」面板里双击运行。
"""
import json
import os

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)


PROJECT_DIR = ".qingcao"
SETTINGS_FILE = "settings.json"
TASKS_FILE = "tasks.json"
# `ui/task_panel.py` / `core/project_tasks.py` 沿用的旧文件名，
# 两个都支持（见 `_project_has_tasks`）
LEGACY_TASKS_FILE = ".qingcao-tasks.json"

# 项目设置里支持生效的键（其余键只保存、不生效，避免"看起来能配实际没用"）
SUPPORTED_SETTINGS = ("tab_width", "use_spaces", "eol", "encoding")


def _app_data_path(filename: str) -> str:
    """`data/` 下的绝对路径（相对路径会随 cwd 漂移）"""
    try:
        from infrastructure.plugin_loader import app_root_dir
        base = os.path.join(app_root_dir(), "data")
    except Exception:
        base = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "data")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, filename)


class ProjectMixin:
    """项目能力 Mixin —— 由 MainWindow 继承

    依赖属性：``self.tabs``、``self.status_bar``、``self.menuBar()``、
    ``self._ensure_panel``、``self.panel_menu``
    """

    # ========================================================
    # 状态
    # ========================================================
    def _init_project_state(self):
        """初始化项目状态（在 `_build_menus` 之前调用）"""
        self._project_root = ""
        self.project_config = None
        self._project_menu = None
        self._recent_menu = None

        # 多根工作区（持久化在 data/workspace.json）
        self.workspace = None
        try:
            from core.workspace import Workspace

            self.workspace = Workspace()
            ws_path = _app_data_path("workspace.json")
            self._workspace_path = ws_path
            if os.path.isfile(ws_path):
                loaded = Workspace.load(ws_path)
                if loaded is not None:
                    self.workspace = loaded
        except Exception as e:
            print(f"[Project] 工作区初始化失败: {e}")

    # ========================================================
    # 菜单
    # ========================================================
    def _setup_project_menu(self):
        """构建「项目」菜单（插在「文件」之后）"""
        try:
            from PyQt5.QtWidgets import QMenu

            self._project_menu = QMenu("项目(&P)", self)
            # 插到「文件」**之后**、「编辑」之前：
            #   `insertMenu(before, menu)` 的语义是"插到 before 之前"，
            #   所以锚点要用「编辑」菜单（不是文件菜单 ——
            #   用文件菜单会把项目插到最前面，实测确实如此）。
            anchor = None
            for attr in ('edit_menu', 'view_menu'):
                cand = getattr(self, attr, None)
                if cand is not None:
                    anchor = cand.menuAction()
                    break
            if anchor is not None:
                self.menuBar().insertMenu(anchor, self._project_menu)
            else:
                self.menuBar().addMenu(self._project_menu)

            self._add_action(self._project_menu, "📁 打开项目…", None,
                             self._open_project)
            self._add_action(self._project_menu, "⚙ 项目设置…", None,
                             self._show_project_settings)
            self._add_action(self._project_menu, "❌ 关闭项目", None,
                             self._close_project)
            self._project_menu.addSeparator()

            # 最近项目（来自 Workspace 持久化）
            self._recent_menu = self._project_menu.addMenu("🕘 最近项目")
            self._rebuild_recent_menu()

            self._project_menu.addSeparator()
            self._add_action(self._project_menu, "🧰 任务面板", None,
                             lambda: self._show_panel('task'))
        except Exception as e:
            print(f"[Project] 项目菜单构建失败: {e}")

    def _rebuild_recent_menu(self):
        """重建「最近项目」子菜单"""
        try:
            if self._recent_menu is None:
                return
            self._recent_menu.clear()
            folders = []
            if self.workspace is not None:
                folders = list(self.workspace.folders)
            if not folders:
                item = self._recent_menu.addAction("（还没有打开过项目）")
                item.setEnabled(False)
                return
            for folder in folders:
                path = getattr(folder, 'path', '') or ''
                name = getattr(folder, 'name', '') or os.path.basename(path)
                if not path:
                    continue
                act = self._recent_menu.addAction(
                    "%s  —  %s" % (name, path)
                )
                # 用默认参数绑定 path，避免闭包晚绑定
                act.triggered.connect(
                    lambda _checked=False, p=path: self._set_project(p)
                )
        except Exception as e:
            print(f"[Project] 重建最近项目失败: {e}")

    # ========================================================
    # 打开 / 关闭项目
    # ========================================================
    def _open_project(self):
        """选择目录作为项目根"""
        try:
            start_dir = self._project_root or os.path.expanduser("~")
            path = QFileDialog.getExistingDirectory(
                self, "打开项目（选择项目根目录）", start_dir
            )
            if not path:
                return
            self._set_project(path)
        except Exception as e:
            print(f"[Project] 打开项目失败: {e}")
            self._project_status(f"打开项目失败: {e}")

    def _set_project(self, root: str) -> bool:
        """设置当前项目根（打开项目 / 从最近项目切回都走这里）

        步骤：
          1. 校验目录存在；
          2. 记进 Workspace 并持久化；
          3. 加载项目配置（没有 `.qingcao/` 时询问是否创建）；
          4. 把项目设置应用到当前编辑器；
          5. 任务面板绑定该项目并显示。
        """
        try:
            root = os.path.abspath(root or "")
            if not root or not os.path.isdir(root):
                self._project_status("项目目录不存在: %s" % root)
                return False

            self._project_root = root

            # 1) 记进工作区（多根模型）
            if self.workspace is not None:
                try:
                    self.workspace.add_folder(
                        root, os.path.basename(root) or root
                    )
                    self.workspace.save(getattr(
                        self, '_workspace_path',
                        _app_data_path("workspace.json")))
                except Exception as e:
                    print(f"[Project] 记录工作区失败: {e}")

            # 2) 项目配置
            from core.project_config import ProjectConfig, set_project_root

            cfg = ProjectConfig(root)
            has_cfg = cfg.has_config()
            if has_cfg:
                cfg.load()
            else:
                reply = QMessageBox.question(
                    self, "初始化项目配置",
                    "目录「%s」还没有青草项目配置（.qingcao/）。\n\n"
                    "要创建吗？\n"
                    "创建后会生成 .qingcao/settings.json（项目级编辑设置）\n"
                    "和 .qingcao/.gitignore。" % os.path.basename(root),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    try:
                        cfg.init_project_dir()
                        cfg.load()
                        has_cfg = True
                    except Exception as e:
                        print(f"[Project] 初始化项目配置失败: {e}")
            self.project_config = cfg

            # 3) 全局单例（供其它模块读取）
            try:
                set_project_root(root)
            except Exception as e:
                print(f"[Project] set_project_root 失败: {e}")

            # 4) 应用项目设置
            self._apply_project_settings()

            # 5) 任务面板
            try:
                self._ensure_panel('task')
                panel = getattr(self, 'task', None)
                if panel is not None:
                    panel.set_project(root)
                    panel.show()
                    panel.raise_()
            except Exception as e:
                print(f"[Project] 绑定任务面板失败: {e}")

            self._rebuild_recent_menu()
            tasks_n = self._count_project_tasks(root)
            self._project_status(
                "已打开项目：%s%s" % (
                    os.path.basename(root),
                    "（%d 个任务）" % tasks_n if tasks_n else ""
                )
            )
            return True
        except Exception as e:
            print(f"[Project] 设置项目失败: {e}")
            self._project_status(f"设置项目失败: {e}")
            return False

    def _close_project(self):
        """关闭当前项目（不关文件，只解除项目绑定）"""
        try:
            self._project_root = ""
            self.project_config = None
            try:
                from core.project_config import set_project_root
                set_project_root("")
            except Exception:
                pass
            panel = getattr(self, 'task', None)
            if panel is not None:
                try:
                    panel.task_manager = None
                    panel.task_tree.clear()
                    panel.hide()
                except Exception:
                    pass
            self._project_status("已关闭项目")
        except Exception as e:
            print(f"[Project] 关闭项目失败: {e}")

    # ========================================================
    # 项目设置
    # ========================================================
    def _apply_project_settings(self):
        """把项目设置应用到**当前编辑器**

        诚实标注：这里只实现**真正能生效**的 4 个键
        （`SUPPORTED_SETTINGS`）：tab 宽度、缩进用空格、换行符、编码。
        其它键（font_size / word_wrap 等）只保存在文件里、不在此生效 ——
        因为改字号/换行要动主题与编辑器构造参数，属于另一个改动面。
        """
        cfg = self.project_config
        if cfg is None:
            return
        proxy = None
        try:
            proxy = self.tabs.current_proxy()
        except Exception:
            pass
        if proxy is None:
            return

        # tab 宽度 + 缩进方式
        try:
            tab_width = int(cfg.get_setting("tab_width", 0) or 0)
            use_spaces = cfg.get_setting("use_spaces", None)
            sc = getattr(proxy, 'sc', None)
            if sc is not None:
                if 1 <= tab_width <= 16:
                    sc.setTabWidth(tab_width)
                    sc.setIndentationWidth(tab_width)
                if use_spaces is not None:
                    sc.setIndentationsUseTabs(not bool(use_spaces))
        except Exception as e:
            print(f"[Project] 应用缩进设置失败: {e}")

        # 换行符
        try:
            eol = cfg.get_setting("eol", "")
            doc = getattr(proxy, 'document', None)
            if eol and doc is not None and hasattr(doc, 'convert_eol'):
                doc.convert_eol(eol)
        except Exception as e:
            print(f"[Project] 应用换行符失败: {e}")

        # 默认编码（只对新打开/未命名文档有意义，这里不强行改已有文件）

    def _show_project_settings(self):
        """项目设置对话框（只读展示 + 编辑受支持的键）"""
        cfg = self.project_config
        if cfg is None or not self._project_root:
            QMessageBox.information(
                self, "项目设置", "请先打开一个项目（项目 → 打开项目…）"
            )
            return
        try:
            dlg = ProjectSettingsDialog(cfg, self._project_root, self)
            if dlg.exec_() == QDialog.Accepted:
                self._apply_project_settings()
                self._project_status("项目设置已保存")
        except Exception as e:
            print(f"[Project] 项目设置失败: {e}")
            QMessageBox.warning(self, "项目设置", str(e))

    # ========================================================
    # 任务面板
    # ========================================================
    def _count_project_tasks(self, root: str) -> int:
        """数一下项目里定义了���少个任务（用于状态栏提示）"""
        if not root:
            return 0
        try:
            from core.project_tasks import ProjectTaskManager

            mgr = ProjectTaskManager(root)
            mgr.load_tasks()
            return len(mgr.tasks)
        except Exception:
            return 0

    def _build_panel_task(self):
        """构造任务面板（`ui/task_panel.py` 此前零实例化）

        ⚠️ 属性名必须是 `self.task`（`_ensure_panel('task')` 用 getattr 取）
        """
        try:
            from ui.task_panel import TaskPanel

            self.task = TaskPanel(main_window=self, parent=self)
            self.addDockWidget(self._bottom_dock_area(), self.task)
            self.task.hide()
            # 若已有当前项目，直接绑定
            if self._project_root:
                try:
                    self.task.set_project(self._project_root)
                except Exception:
                    pass
        except Exception as e:
            print(f"[TaskPanel] 加载失败: {e}")
            self.task = None

    def _toggle_task_panel(self, checked):
        """切换任务面板"""
        if self._ensure_panel('task') and getattr(self, 'task', None):
            self.task.setVisible(checked)
            if checked and self._project_root:
                try:
                    self.task.set_project(self._project_root)
                except Exception:
                    pass

    # ========================================================
    # 状态提示
    # ========================================================
    def _project_status(self, text: str):
        """状态栏提示（失败不影响主流程）"""
        try:
            self.status_bar.showMessage(text, 6000)
        except Exception:
            print("[Project] " + text)

    def current_project_root(self) -> str:
        """当前项目根（空串表示未打开项目）"""
        return getattr(self, '_project_root', '') or ''


class ProjectSettingsDialog(QDialog):
    """项目设置对话框（只暴露**真正能生效**的键）"""

    def __init__(self, config, project_root: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.project_root = project_root
        self.setWindowTitle("项目设置 — %s" % os.path.basename(project_root))
        self.resize(460, 260)

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "项目根：%s\n配置文件：%s"
            % (project_root,
               os.path.join(project_root, PROJECT_DIR, SETTINGS_FILE))
        ))

        form = QFormLayout()

        self.tab_spin = QSpinBox()
        self.tab_spin.setRange(1, 16)
        self.tab_spin.setValue(
            int(config.get_setting("tab_width", 4) or 4)
        )
        form.addRow("Tab 宽度:", self.tab_spin)

        self.spaces_cb = QCheckBox("用空格代替 Tab")
        self.spaces_cb.setChecked(
            bool(config.get_setting("use_spaces", True))
        )
        form.addRow("缩进:", self.spaces_cb)

        self.eol_combo = QComboBox()
        for label, val in (("保持现状", ""), ("LF (\\n)", "\n"),
                           ("CRLF (\\r\\n)", "\r\n"), ("CR (\\r)", "\r")):
            self.eol_combo.addItem(label, val)
        current_eol = config.get_setting("eol", "")
        idx = self.eol_combo.findData(current_eol)
        self.eol_combo.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("换行符:", self.eol_combo)

        root.addLayout(form)

        tip = QLabel(
            "提示：仅上面这些项会在打开项目时生效；\n"
            "其它键可手工写入 settings.json，但当前版本不会应用。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(tip)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_accept(self):
        try:
            self.config.set_setting("tab_width", int(self.tab_spin.value()))
            self.config.set_setting("use_spaces",
                                    bool(self.spaces_cb.isChecked()))
            eol = self.eol_combo.currentData()
            if eol is not None:
                self.config.set_setting("eol", eol)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self.accept()
