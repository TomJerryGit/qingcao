# -*- coding: utf-8 -*-
"""快捷键方案预设

## 用途
提供 Notepad++ / VSCode / Sublime / Vim 风格的快捷键预设，让用户**一键切换**
操作习惯，而不是在快捷键编辑器里逐个手改。

## ★ 重要约束（改这些 overrides 前必读）

1. **action 名必须与 `ActionManager` 里注册的名字完全一致**
   （例如 `file.new` / `edit.duplicate_line` / `view.column_mode`）。
   `ActionManager.set_shortcut()` 对**不存在的名字返回 False 而不抛异常** ——
   也就是说**拼错会被静默忽略**，用户以为切了方案、实际没生效。
   改完请用 `validate_scheme()` 检查，并跑
   `python tools/verify_keymap_profiles.py`。

2. **同一个方案内不得出现重复快捷键**。
   Qt 遇到重复快捷键会报 `ambiguous shortcut overload`，**按键彻底失效**
   （不是"后一个覆盖前一个"）。历史缺陷：vscode 方案里
   `edit.duplicate_line` 与 `view.column_mode` 都写成了 `Shift+Alt+Down`，
   一应用就产生重复绑定。`apply_scheme()` 现在会**拒绝**这类方案。

3. 方案之间**允许**同一快捷键对应不同 action（那是用户主动切换方案的预期行为）；
   禁止的是方案**内部**重复。
"""
from typing import Dict, List, Tuple


KEYMAP_SCHEMES = {
    "default": {
        "name": "青草默认",
        "description": "默认的快捷键布局",
        "overrides": {},  # 使用 ActionManager 里的默认值
    },

    "vscode": {
        "name": "VSCode 兼容",
        "description": "使用 VSCode 风格的快捷键",
        "overrides": {
            "file.new": "Ctrl+N",
            "file.open": "Ctrl+O",
            "file.save": "Ctrl+S",
            "file.save_as": "Ctrl+Shift+S",
            "edit.find": "Ctrl+F",
            # 说明：本项目**没有**独立的"替换"对话框（替换是全局搜索面板
            # 内部的输入框，不是 QAction，无法注册进 ActionManager）。
            # 原先这里写了 "edit.replace": "Ctrl+H"，实测 `set_shortcut()`
            # 因动作不存在而静默返回 False —— 用户以为生效了其实没有。
            # 故按事实移除；替换入口是「查找」（Ctrl+F）与「全局搜索」
            # （Ctrl+Shift+F）。
            "edit.goto_line": "Ctrl+G",
            "tools.command_palette": "Ctrl+Shift+P",
            "tools.quick_open": "Ctrl+P",
            "edit.toggle_comment": "Ctrl+/",
            "edit.duplicate_line": "Shift+Alt+Down",
            "edit.move_line_up": "Alt+Up",
            "edit.move_line_down": "Alt+Down",
            "edit.select_next": "Ctrl+D",
            # VSCode 的列选是 Shift+Alt+Down/Up（列选择模式），
            # 但"复制行"已经占用了 Shift+Alt+Down —— 同一方案内重复绑定会让
            # Qt 报 ambiguous shortcut，两个动作**都失效**。
            # 因此列模式改用 VSCode 的另一组列选快捷键
            # Ctrl+Shift+Alt+Down（VSCode 中为 Column Selection 的备用绑定），
            # 语义一致且不与本方案其它条目冲突。
            "view.column_mode": "Ctrl+Shift+Alt+Down",
        },
    },

    "sublime": {
        "name": "Sublime Text 兼容",
        "description": "使用 Sublime 风格的快捷键",
        "overrides": {
            "file.new": "Ctrl+N",
            "file.open": "Ctrl+O",
            "file.save": "Ctrl+S",
            "edit.find": "Ctrl+F",
            # 同上：本项目无独立替换对话框
            "edit.goto_line": "Ctrl+G",
            "tools.command_palette": "Ctrl+Shift+P",
            "tools.quick_open": "Ctrl+P",
            "edit.toggle_comment": "Ctrl+/",
            "edit.select_next": "Ctrl+D",
            "edit.move_line_up": "Ctrl+Shift+Up",
            "edit.move_line_down": "Ctrl+Shift+Down",
        },
    },

    "vim": {
        "name": "Vim 模式",
        "description": "使用 Vim 风格的操作",
        "overrides": {
            "file.save": "Ctrl+S",
            "edit.find": "Ctrl+F",
            "edit.undo": "Ctrl+Z",
            "edit.redo": "Ctrl+Shift+Z",
            "edit.goto_line": "Ctrl+G",
            "tools.command_palette": "Ctrl+Shift+P",
        },
    },
}


def get_scheme_names():
    """获取所有方案名"""
    return [(k, v["name"]) for k, v in KEYMAP_SCHEMES.items()]


def get_scheme(key):
    """获取方案详情"""
    return KEYMAP_SCHEMES.get(key, KEYMAP_SCHEMES["default"])


def validate_scheme(key: str,
                    action_manager=None) -> Tuple[bool, List[str]]:
    """校验方案是否能安全应用

    参数:
        key: 方案 key
        action_manager: 可选。传入时会**额外**校验每个 action 名是否真实存在
            （`set_shortcut` 对不存在的名字返回 False 而不抛异常，
            所以拼错的条目会被静默忽略 —— 必须显式查出来）

    返回:
        ``(ok, problems)``；problems 为人类可读的问题列表（空列表表示没问题）
    """
    problems: List[str] = []

    if key not in KEYMAP_SCHEMES:
        return False, ["未知的快捷键方案: %r（可选: %s）"
                       % (key, [k for k, _ in get_scheme_names()])]

    overrides: Dict[str, str] = get_scheme(key).get("overrides", {}) or {}

    # 1) 方案内部不得有重复快捷键（会导致 Qt ambiguous shortcut，按键失效）
    seen: Dict[str, str] = {}
    for action_name, shortcut in overrides.items():
        sc = (shortcut or "").strip()
        if not sc:
            problems.append("动作 %s 的快捷键为空" % action_name)
            continue
        if sc in seen:
            problems.append(
                "快捷键 %r 在同一方案内重复绑定：%s 与 %s"
                "（Qt 会报 ambiguous shortcut，两个动作都会失效）"
                % (sc, seen[sc], action_name)
            )
        else:
            seen[sc] = action_name

    # 2) 可选：action 名是否真实存在
    if action_manager is not None:
        actions = getattr(action_manager, "actions", None)
        if actions is not None:
            for action_name in overrides:
                if action_name not in actions:
                    problems.append(
                        "动作名 %r 未在 ActionManager 中注册"
                        "（会被静默忽略，请核对拼写）" % action_name
                    )

    return (not problems), problems


def apply_scheme(action_manager, scheme_key) -> bool:
    """应用快捷键方案

    参数:
        action_manager: ActionManager 实例
        scheme_key: 方案 key

    返回:
        True 表示已成功应用；False 表示**拒绝应用**（参数见 problems）

    ★ 防御性设计（真实缺陷修复）：
        原实现直接 `reset_to_defaults()` 然后逐条 `set_shortcut()`。
        如果方案本身含重复快捷键（历史上 vscode 方案就是），
        应用后全仓出现重复绑定 → Qt ambiguous shortcut → 按键失效。
        更糟的是它**先重置再失败**，用户原来的快捷键已经被清掉，
        处于"半坏"状态且没有任何提示。

        现在：**先校验，通过才动任何东西**；失败时保持原状并打印原因。
    """
    ok, problems = validate_scheme(scheme_key, action_manager=action_manager)
    if not ok:
        print("[KeymapScheme] 拒绝应用方案 %r：" % scheme_key)
        for p in problems:
            print("    - %s" % p)
        return False

    if scheme_key == "default":
        # 恢复默认
        action_manager.reset_to_defaults()
        return True

    # 先恢复默认
    action_manager.reset_to_defaults()

    # 再应用覆盖
    failed: List[str] = []
    for action_name, shortcut in get_scheme(scheme_key).get(
            "overrides", {}).items():
        try:
            if action_manager.set_shortcut(action_name, shortcut) is False:
                failed.append(action_name)
        except Exception as e:
            failed.append("%s(%s)" % (action_name, e))

    if failed:
        # 不静默：明确告诉调用方哪些条目没生效（多为 action 名拼错）
        print("[KeymapScheme] 以下条目未生效（动作名可能不存在）：%s"
              % ", ".join(failed))
    return True
