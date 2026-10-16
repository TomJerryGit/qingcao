# -*- coding: utf-8 -*-
"""P1-7 验证：「⭐ 特色功能」聚合入口是否真的把差异化能力暴露出来

可独立运行（不需要 pytest）：
    python tools/verify_feature_menu.py
"""
import os
import sys


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PyQt5.QtWidgets import QAction, QApplication  # noqa: E402


app = QApplication.instance() or QApplication([])

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-52s %s" % ("OK " if cond else "FAIL", name, detail))


def collect(menu, depth=0, out=None):
    """递归收集菜单文本（保持层级，便于断言）"""
    if out is None:
        out = []
    for act in menu.actions():
        sub = act.menu()
        if sub is not None:
            out.append("  " * depth + act.text() + "/")
            collect(sub, depth + 1, out)
        else:
            out.append("  " * depth + act.text())
    return out


print("=" * 92)
print("P1-7 验证：⭐ 特色功能 聚合入口")
print("=" * 92)

from ui.main_window import MainWindow  # noqa: E402


w = MainWindow()

# ---- 1. 菜单存在且位置显眼（一级菜单）----
print()
print("[1] 菜单存在与位置")
tops = [a.text() for a in w.menuBar().actions()]
check("1a 「⭐ 特色功能」是一级菜单", "⭐ 特色功能" in tops, str(tops))
fm = getattr(w, 'feature_menu', None)
check("1b feature_menu 是 QMenu（不是 QAction）",
      fm is not None and hasattr(fm, 'addSeparator'),
      type(fm).__name__ if fm is not None else None)

# ---- 2. 构造时（插件未加载）：如实占位，不撒谎 ----
print()
print("[2] 插件未加载时如实说明")
before = "\n".join(collect(fm))
check("2a 未加载时显示「未注册命令」占位",
      "未注册命令" in before, "")
# ⚠️ 时序很重要：必须在 `_load_plugins()` **之前**取占位项的禁用状态。
#   插件加载后 `refresh_feature_menu()` 会把占位项换成真实命令，
#   那时再查就查不到了（原断言写错位置，导致恒失败）。
placeholder_disabled = []
for act in fm.actions():
    sub = act.menu()
    if sub is None:
        continue
    for item in sub.actions():
        if "未注册" in item.text():
            placeholder_disabled.append(not item.isEnabled())
check("2b 占位项被禁用（不可点）",
      bool(placeholder_disabled) and all(placeholder_disabled),
      "占位项 %d 个，禁用 %d 个"
      % (len(placeholder_disabled), sum(placeholder_disabled)))

# ---- 3. 插件加载后自动刷新 ----
print()
print("[3] 插件加载后自动刷新（P1-7 的核心）")
w._load_plugins()
after = collect(fm)
joined = "\n".join(after)

cmds = w._plugin_commands("ai_assistant")
check("3a act_mgr 里确实有 ai_assistant 命令", len(cmds) >= 1,
      "%d 个" % len(cmds))
check("3b AI 子菜单列出了真实插件命令",
      any("AI:" in x or "AI：" in x for x in after),
      "AI 条目 %d" % sum(1 for x in after if "AI:" in x))
check("3c Git 子菜单列出了真实插件命令",
      any("Git" in x and "状态" in x for x in after),
      "Git 条目 %d" % sum(1 for x in after if "Git" in x))
check("3d 不再有「未注册命令」占位",
      "未注册命令" not in joined, "")

# ---- 4. 命令与命令面板**同源**（不会出现菜单有、面板没有）----
print()
print("[4] 与命令面板同源")
acts = getattr(w.act_mgr, 'actions', {}) or {}
panel_cmds = {k for k in acts if isinstance(k, str)
              and k.startswith("plugin.")}
mine = set()
for act in fm.actions():
    sub = act.menu()
    if sub is None:
        continue
    for item in sub.actions():
        for k, qa in acts.items():
            if qa is item:
                mine.add(k)
check("4a 特色功能列出的命令都在 act_mgr 里", mine and mine <= panel_cmds,
      "%d 个" % len(mine))
check("4b 命令面板能取到同一批命令（plugin.* 前缀）",
      len(panel_cmds) >= len(mine), "面板 %d / 菜单 %d"
      % (len(panel_cmds), len(mine)))

# ---- 5. 点击链路真的会执行（不是哑菜单）----
print()
print("[5] 点击链路可执行")
hit = []
try:
    target = None
    for act in fm.actions():
        if act.menu() and "AI 助手" in act.text():
            sub = act.menu()
            for item in sub.actions():
                if item.isEnabled():
                    target = item
                    break
    if target is None:
        check("5a 找到可点击的 AI 命令", False, "没有可用条目")
    else:
        # 只验证"signal 已连接到可调用对象"，不真的调 AI（会联网）
        rcv = target.receivers(target.triggered)
        check("5a AI 命令已连接接收者（点击会执行）", rcv > 0,
              "%s receivers=%d" % (target.text(), rcv))
        hit.append(target)
except Exception as e:
    check("5a AI 命令已连接接收者（点击会执行）", False, "%s" % e)

# F5 必须**全仓唯一**，且特色功能里那一项就是同一个 QAction 对象
f5_actions = [a for a in w.findChildren(QAction)
              if a.shortcut().toString() == "F5"]
check("5b F5 全仓只绑定 1 个动作", len(f5_actions) == 1,
      "%d 个: %s" % (len(f5_actions), [a.text() for a in f5_actions]))
feat_run = [a for a in fm.actions() if a.text().startswith("▶ 运行当前文件")]
check("5c 特色功能里的运行项复用了同一个 F5 动作对象",
      len(feat_run) == 1 and bool(f5_actions)
      and feat_run[0] is f5_actions[0],
      "同一个对象=%s" % (bool(feat_run and f5_actions)
                        and feat_run[0] is f5_actions[0]))

print()
print("=" * 92)
print("结果：%d 通过 / %d 失败" % (len(PASS), len(FAIL)))
print("=" * 92)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)
print()
print("菜单结构（插件加载后）：")
for line in collect(fm):
    print("  " + line)
sys.exit(1 if FAIL else 0)
