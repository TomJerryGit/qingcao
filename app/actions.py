#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为动作管理模块，包含：
- ActionManager：全局动作注册与快捷键管理
- create_action：动作创建工厂
- 快捷键自定义加载与保存
- 配置文件损坏自修复
- 快捷键冲突检测
- 动作分组与分类
"""

import datetime
import json
import os
import shutil
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import QAction, QApplication, QMessageBox, QStyle


# ============================================================
# 常量定义
# ============================================================
KEYBINDINGS_FILE = "keybindings.json"
KEYBINDINGS_BACKUP_DIR = "data/backups"

# 动作分类
CATEGORY_FILE = "文件"
CATEGORY_EDIT = "编辑"
CATEGORY_VIEW = "视图"
CATEGORY_TOOLS = "工具"
CATEGORY_SEARCH = "搜索"
CATEGORY_MACRO = "宏"
CATEGORY_HELP = "帮助"
CATEGORY_PLUGIN = "插件"
CATEGORY_OTHER = "其他"

# 默认分类映射（基于动作名前缀）
CATEGORY_MAP = {
    'f.': CATEGORY_FILE,
    'file.': CATEGORY_FILE,
    'e.': CATEGORY_EDIT,
    'edit.': CATEGORY_EDIT,
    'v.': CATEGORY_VIEW,
    'view.': CATEGORY_VIEW,
    't.': CATEGORY_TOOLS,
    'tools.': CATEGORY_TOOLS,
    's.': CATEGORY_SEARCH,
    'search.': CATEGORY_SEARCH,
    'm.': CATEGORY_MACRO,
    'macro.': CATEGORY_MACRO,
    'h.': CATEGORY_HELP,
    'help.': CATEGORY_HELP,
    'p.': CATEGORY_PLUGIN,
    'plugin.': CATEGORY_PLUGIN,
}


# ============================================================
# 动作创建工厂
# ============================================================
def create_action(
    parent,
    name: str,
    text: str,
    shortcut: Optional[str],
    slot: Callable,
    mgr: 'ActionManager',
    icon: Optional[str] = None,
    tooltip: Optional[str] = None,
    checkable: bool = False,
    category: Optional[str] = None,
) -> QAction:
    """
    创建一个 QAction 并注册到 ActionManager。

    参数:
        parent: 父对象（通常是主窗口）
        name: 动作唯一名称（如 "file.new"）
        text: 显示文本（如 "新建"）
        shortcut: 快捷键字符串（如 "Ctrl+N"），可为 None
        slot: 触发时调用的函数
        mgr: ActionManager 实例
        icon: 图标名称（可选，从 IconManager 获取）
        tooltip: 工具提示（可选）
        checkable: 是否为可勾选动作
        category: 动作分类（可选，不指定则根据 name 自动推断）

    返回:
        创建好的 QAction 实例
    """
    act = QAction(text, parent)

    # 设置图标
    if icon:
        try:
            from infrastructure.icon_manager import IconManager
            act.setIcon(IconManager.get(icon))
        except Exception:
            # 回退到系统标准图标
            pass

    # 设置快捷键
    if shortcut:
        act.setShortcut(QKeySequence(shortcut))

    # 设置工具提示
    if tooltip:
        act.setToolTip(tooltip)
    elif shortcut:
        # 如果未提供工具提示，自动生成包含快捷键的提示
        act.setToolTip(f"{text} ({shortcut})")
    else:
        act.setToolTip(text)

    # 可勾选
    if checkable:
        act.setCheckable(True)

    # 连接信号
    if checkable:
        act.toggled.connect(slot)
    else:
        act.triggered.connect(slot)

    # 注册到管理器
    mgr.register(name, act, shortcut, category=category)

    return act


# ============================================================
# 动作管理器
# ============================================================
class ActionManager(QObject):
    """
    全局动作管理器。

    职责:
    - 注册所有 QAction
    - 管理默认快捷键
    - 加载/保存用户自定义快捷键
    - 检测快捷键冲突
    - 提供动作查询接口
    - 支持动作分类

    信号:
        action_registered(str): 新动作注册时发射（动作名称）
        shortcut_changed(str, str): 快捷键变更时发射（动作名称, 新快捷键）
        conflict_detected(str, str, str): 检测到快捷键冲突（快捷键, 动作1, 动作2）
    """

    action_registered = pyqtSignal(str)
    shortcut_changed = pyqtSignal(str, str)
    conflict_detected = pyqtSignal(str, str, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 动作字典: name -> QAction
        self.actions: Dict[str, QAction] = {}

        # 默认快捷键: name -> shortcut string
        self.defaults: Dict[str, str] = {}

        # 动作分类: name -> category
        self.categories: Dict[str, str] = {}

        # 动作描述: name -> description
        self.descriptions: Dict[str, str] = {}

        # 加载状态
        self._loaded_custom = False

    # --------------------------------------------------------
    # 注册与注销
    # --------------------------------------------------------
    def register(
        self,
        name: str,
        action: QAction,
        default_shortcut: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
    ):
        """
        注册一个动作。

        参数:
            name: 动作唯一名称
            action: QAction 实例
            default_shortcut: 默认快捷键
            category: 动作分类（不指定则自动推断）
            description: 动作描述（用于命令面板）
        """
        if not name:
            raise ValueError("动作名称不能为空")

        if name in self.actions:
            # 已存在，先注销旧的
            self.unregister(name)

        self.actions[name] = action

        if default_shortcut:
            self.defaults[name] = default_shortcut
            # 如果 action 尚未设置快捷键，则应用默认值
            if action.shortcut().isEmpty():
                action.setShortcut(QKeySequence(default_shortcut))

        # 推断分类
        if category:
            self.categories[name] = category
        else:
            self.categories[name] = self._infer_category(name)

        # 描述
        self.descriptions[name] = description or action.text()

        self.action_registered.emit(name)

    def unregister(self, name: str):
        """注销一个动作"""
        if name in self.actions:
            del self.actions[name]
        if name in self.defaults:
            del self.defaults[name]
        if name in self.categories:
            del self.categories[name]
        if name in self.descriptions:
            del self.descriptions[name]

    def get(self, name: str) -> Optional[QAction]:
        """获取指定名称的动作"""
        return self.actions.get(name)

    def exists(self, name: str) -> bool:
        """判断动作是否存在"""
        return name in self.actions

    # --------------------------------------------------------
    # 分类推断
    # --------------------------------------------------------
    def _infer_category(self, name: str) -> str:
        """根据动作名称前缀推断分类"""
        for prefix, category in CATEGORY_MAP.items():
            if name.startswith(prefix):
                return category
        return CATEGORY_OTHER

    def get_categories(self) -> Dict[str, List[str]]:
        """返回按分类分组的动作名称"""
        result: Dict[str, List[str]] = {}
        for name, category in self.categories.items():
            result.setdefault(category, []).append(name)
        # 排序每个分类内的动作
        for cat in result:
            result[cat].sort()
        return result

    def get_by_category(self, category: str) -> List[QAction]:
        """获取指定分类的所有动作"""
        return [
            self.actions[name]
            for name, cat in self.categories.items()
            if cat == category and name in self.actions
        ]

    # --------------------------------------------------------
    # 快捷键加载/保存
    # --------------------------------------------------------
    def load_custom(self, path: str = KEYBINDINGS_FILE) -> bool:
        """
        加载用户自定义快捷键。

        返回:
            True 表示加载成功（或文件不存在，使用默认）
            False 表示文件损坏但已备份
        """
        if not os.path.exists(path):
            self._loaded_custom = True
            return True

        try:
            with open(path, encoding='utf-8') as f:
                custom = json.load(f)

            if not isinstance(custom, dict):
                raise ValueError("快捷键配置文件格式错误：应为 JSON 对象")

            applied = 0
            for name, shortcut in custom.items():
                if name in self.actions:
                    try:
                        self.actions[name].setShortcut(QKeySequence(shortcut))
                        self.shortcut_changed.emit(name, shortcut)
                        applied += 1
                    except Exception as e:
                        print(f"[快捷键] 设置 {name} -> {shortcut} 失败: {e}")

            self._loaded_custom = True
            print(f"[快捷键] 已加载 {applied} 个自定义快捷键")
            return True

        except json.JSONDecodeError as e:
            self._backup_broken_file(path, f"JSON 解析错误: {e}")
            return False
        except Exception as e:
            self._backup_broken_file(path, f"未知错误: {e}")
            return False

    def save_custom(self, path: str = KEYBINDINGS_FILE) -> bool:
        """
        保存用户自定义快捷键（仅保存与默认值不同的）。

        返回:
            是否保存成功
        """
        try:
            custom = {}
            for name, action in self.actions.items():
                shortcut = action.shortcut().toString()
                default = self.defaults.get(name, '')
                if shortcut and shortcut != default:
                    custom[name] = shortcut

            # 确保目录存在
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(custom, f, indent=2, ensure_ascii=False, sort_keys=True)

            print(f"[快捷键] 已保存 {len(custom)} 个自定义快捷键")
            return True

        except Exception as e:
            print(f"[快捷键] 保存失败: {e}")
            return False

    def reset_to_defaults(self, path: str = KEYBINDINGS_FILE) -> bool:
        """将所有动作恢复为默认快捷键"""
        try:
            for name, action in self.actions.items():
                default = self.defaults.get(name, '')
                if default:
                    action.setShortcut(QKeySequence(default))
                else:
                    action.setShortcut(QKeySequence())

            # 删除自定义配置文件
            if os.path.exists(path):
                os.remove(path)

            print("[快捷键] 已恢复默认")
            return True
        except Exception as e:
            print(f"[快捷键] 恢复默认失败: {e}")
            return False

    def _backup_broken_file(self, path: str, reason: str):
        """备份损坏的配置文件"""
        try:
            os.makedirs(KEYBINDINGS_BACKUP_DIR, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            basename = os.path.basename(path)
            backup_path = os.path.join(
                KEYBINDINGS_BACKUP_DIR,
                f"{basename}.broken.{timestamp}"
            )
            shutil.copy(path, backup_path)
            os.remove(path)

            print(f"[快捷键] 配置文件损坏（{reason}），已备份至：{backup_path}")

            # 弹窗提示（如果 QApplication 存在）
            app = QApplication.instance()
            if app:
                QMessageBox.warning(
                    None, "快捷键配置损坏",
                    f"快捷键配置文件已损坏，已自动备份并恢复默认。\n\n"
                    f"原因：{reason}\n"
                    f"备份位置：{backup_path}"
                )
        except Exception as e:
            print(f"[快捷键] 备份失败: {e}")

    # --------------------------------------------------------
    # 快捷键查询与冲突检测
    # --------------------------------------------------------
    def get_shortcut(self, name: str) -> str:
        """获取指定动作的快捷键字符串"""
        action = self.actions.get(name)
        if action:
            return action.shortcut().toString()
        return ""

    def set_shortcut(self, name: str, shortcut: str) -> bool:
        """设置指定动作的快捷键"""
        action = self.actions.get(name)
        if not action:
            return False
        try:
            action.setShortcut(QKeySequence(shortcut))
            self.shortcut_changed.emit(name, shortcut)
            return True
        except Exception as e:
            print(f"[快捷键] 设置 {name} 失败: {e}")
            return False

    def find_conflicts(self) -> Dict[str, List[str]]:
        """
        检测快捷键冲突。

        返回:
            {快捷键: [动作名1, 动作名2, ...]}
            仅包含有冲突的快捷键
        """
        shortcut_map: Dict[str, List[str]] = {}
        for name, action in self.actions.items():
            shortcut = action.shortcut().toString()
            if shortcut:
                shortcut_map.setdefault(shortcut, []).append(name)

        conflicts = {
            shortcut: names
            for shortcut, names in shortcut_map.items()
            if len(names) > 1
        }
        return conflicts

    def check_conflict(self, shortcut: str, exclude_name: Optional[str] = None) -> List[str]:
        """
        检查某个快捷键是否与已有动作冲突。

        参数:
            shortcut: 要检查的快捷键
            exclude_name: 排除的动作名（用于编辑时排除自身）

        返回:
            冲突的动作名称列表
        """
        conflicts = []
        target = QKeySequence(shortcut).toString()
        for name, action in self.actions.items():
            if name == exclude_name:
                continue
            if action.shortcut().toString() == target:
                conflicts.append(name)
        return conflicts

    # --------------------------------------------------------
    # 查询与遍历
    # --------------------------------------------------------
    def all_actions(self) -> List[Tuple[str, QAction]]:
        """返回所有动作的 (name, action) 列表"""
        return list(self.actions.items())

    def names(self) -> List[str]:
        """返回所有动作名称"""
        return list(self.actions.keys())

    def count(self) -> int:
        """返回动作总数"""
        return len(self.actions)

    def search(self, keyword: str) -> List[Tuple[str, QAction]]:
        """
        根据关键词模糊搜索动作（用于命令面板）。

        匹配范围：动作名称、显示文本、描述、快捷键

        返回:
            匹配的 (name, action) 列表，按相关性排序
        """
        keyword = keyword.lower().strip()
        if not keyword:
            return self.all_actions()

        results: List[Tuple[int, str, QAction]] = []

        for name, action in self.actions.items():
            text = action.text().lower()
            desc = self.descriptions.get(name, '').lower()
            shortcut = action.shortcut().toString().lower()

            score = 0
            if keyword in text:
                score += 100 - text.index(keyword)
            if keyword in name.lower():
                score += 50
            if keyword in desc:
                score += 30
            if keyword in shortcut:
                score += 20

            if score > 0:
                results.append((score, name, action))

        # 按分数降序排序
        results.sort(key=lambda x: x[0], reverse=True)
        return [(name, action) for _, name, action in results]

    # --------------------------------------------------------
    # 启用/禁用
    # --------------------------------------------------------
    def set_enabled(self, name: str, enabled: bool):
        """启用或禁用指定动作"""
        action = self.actions.get(name)
        if action:
            action.setEnabled(enabled)

    def set_all_enabled(self, enabled: bool):
        """启用或禁用所有动作"""
        for action in self.actions.values():
            action.setEnabled(enabled)

    def enable_group(self, prefix: str, enabled: bool):
        """按名称前缀启用/禁用一组动作"""
        for name, action in self.actions.items():
            if name.startswith(prefix):
                action.setEnabled(enabled)

    # --------------------------------------------------------
    # 导出/导入
    # --------------------------------------------------------
    def export_config(self, path: str) -> bool:
        """导出当前所有动作配置（含默认值和当前值）"""
        try:
            data = {
                'version': 1,
                'exported_at': datetime.datetime.now().isoformat(),
                'actions': {}
            }
            for name, action in self.actions.items():
                data['actions'][name] = {
                    'text': action.text(),
                    'current_shortcut': action.shortcut().toString(),
                    'default_shortcut': self.defaults.get(name, ''),
                    'category': self.categories.get(name, CATEGORY_OTHER),
                    'description': self.descriptions.get(name, ''),
                }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[快捷键] 导出失败: {e}")
            return False

    def import_config(self, path: str) -> bool:
        """从导出的配置文件导入快捷键"""
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)

            actions_data = data.get('actions', {})
            for name, info in actions_data.items():
                if name in self.actions:
                    shortcut = info.get('current_shortcut', '')
                    if shortcut:
                        self.actions[name].setShortcut(QKeySequence(shortcut))
            return True
        except Exception as e:
            print(f"[快捷键] 导入失败: {e}")
            return False

    # --------------------------------------------------------
    # 调试与信息
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出所有动作信息为字符串（用于调试）"""
        lines = [f"ActionManager: {self.count()} 个动作", "=" * 60]
        for category, names in self.get_categories().items():
            lines.append(f"\n[{category}]")
            for name in names:
                action = self.actions[name]
                shortcut = action.shortcut().toString()
                lines.append(f"  {name:30s} {action.text():20s} {shortcut}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.actions)

    def __contains__(self, name: str) -> bool:
        return name in self.actions

    def __iter__(self):
        return iter(self.actions.items())

    def __repr__(self) -> str:
        return f"<ActionManager: {self.count()} actions>"


# ============================================================
# 辅助函数
# ============================================================
def create_standard_icon(action: QAction, style_icon):
    """
    为 QAction 设置 Qt 标准图标。

    用法:
        create_standard_icon(action, QStyle.SP_FileIcon)
    """
    app = QApplication.instance()
    if app:
        style = app.style()
        action.setIcon(style.standardIcon(style_icon))


def get_standard_icon(style_icon) -> QIcon:
    """获取 Qt 标准图标"""
    app = QApplication.instance()
    if app:
        style = app.style()
        return style.standardIcon(style_icon)
    return QIcon()


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    # 简单的自测
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)
    win = QMainWindow()
    mgr = ActionManager()

    def dummy_slot():
        print("动作被触发")

    # 创建几个测试动作
    create_action(win, "file.new", "新建", "Ctrl+N", dummy_slot, mgr)
    create_action(win, "file.open", "打开", "Ctrl+O", dummy_slot, mgr)
    create_action(win, "file.save", "保存", "Ctrl+S", dummy_slot, mgr)
    create_action(win, "edit.undo", "撤销", "Ctrl+Z", dummy_slot, mgr)
    create_action(win, "edit.redo", "重做", "Ctrl+Y", dummy_slot, mgr)
    create_action(win, "edit.copy", "复制", "Ctrl+C", dummy_slot, mgr)
    create_action(win, "edit.paste", "粘贴", "Ctrl+V", dummy_slot, mgr)

    # 制造一个冲突
    create_action(win, "edit.duplicate", "复制行", "Ctrl+C", dummy_slot, mgr)

    print(mgr.dump())
    print("\n冲突检测:")
    conflicts = mgr.find_conflicts()
    for shortcut, names in conflicts.items():
        print(f"  {shortcut}: {names}")

    print("\n搜索 '保存':")
    for name, action in mgr.search("保存"):
        print(f"  {name}: {action.text()}")