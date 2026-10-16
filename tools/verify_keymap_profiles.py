# -*- coding: utf-8 -*-
"""青草编辑器 · 快捷键方案（keymap profiles）验证

不依赖 pytest，直接运行::

    python tools\\verify_keymap_profiles.py

覆盖：
  1. 每个方案（default/vscode/sublime/vim）都能通过 validate_scheme；
  2. **方案内部无重复快捷键**（Qt 遇重复会报 ambiguous shortcut，按键失效）；
  3. 重复快捷键的方案会被 apply_scheme **拒绝**（且不留下半坏状态）；
  4. 真实 ActionManager + 真实 MainWindow：动作确实被注册
     （这是本功能能生效的前提 —— 此前 ActionManager 是空的）；
  5. 套用方案后 overrides 真的写到了 QAction 的 shortcut 上；
  6. 套用方案后**全仓无重复快捷键**；
  7. default 方案能恢复默认（不是把快捷键清空）；
  8. QSettings 持久化往返 + apply_saved_scheme。

退出码: 0 = 全部通过；1 = 有失败项。
"""
import os
import sys
import tempfile


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PyQt5.QtGui import QKeySequence  # noqa: E402
from PyQt5.QtWidgets import QAction, QApplication  # noqa: E402


app = QApplication.instance() or QApplication([])

PASS, FAIL = [], []


def norm(sc):
    """把快捷键规范化为 Qt 的排序形式

    为什么必须规范化：**Qt 会对修饰键重新排序**。
    方案文件里写 `Shift+Alt+Down`，`QAction.shortcut().toString()` 会返回
    `Alt+Shift+Down` —— 直接做字符串比较会误判成"没生效"（实测踩过）。
    两边都用 `QKeySequence` 归一化后再比。
    """
    if not sc:
        return ""
    return QKeySequence(str(sc)).toString()


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-56s %s" % ("OK " if cond else "FAIL", name, detail))


def sc_of(action):
    try:
        return action.shortcut().toString()
    except Exception:
        return ""


def duplicate_shortcuts(root):
    """扫描 root 下所有 QAction，返回重复快捷键列表 [(key, text), ...]"""
    seen, dups = {}, []
    for a in root.findChildren(QAction):
        key = sc_of(a)
        if not key:
            continue
        if key in seen and seen[key] is not a:
            dups.append((key, a.text()))
        else:
            seen[key] = a
    return dups


print("=" * 96)
print("青草编辑器 · 快捷键方案验证")
print("=" * 96)

from core.keymap_profiles import (  # noqa: E402
    KEYMAP_SCHEMES,
    apply_scheme,
    get_scheme,
    get_scheme_names,
    validate_scheme,
)


# ============================================================
# 1. 逐方案校验
# ============================================================
print()
print("== 1. 逐方案 validate_scheme（纯逻辑，不看 ActionManager）==")
names = get_scheme_names()
check("方案数量 >= 4", len(names) >= 4,
      str([k for k, _ in names]))
for key, label in names:
    ok, probs = validate_scheme(key)
    check("方案 %s（%s）内部自洽" % (key, label), ok,
          "" if ok else "; ".join(probs[:2]))

# 未知方案必须被拒绝，而不是静默回退
ok_unknown, probs_unknown = validate_scheme("__no_such_scheme__")
check("未知方案被拒绝", not ok_unknown, probs_unknown[:1])

# ============================================================
# 2. 重复快捷键必须被拒绝（核心缺陷回归）
# ============================================================
print()
print("== 2. 重复快捷键的方案必须被拒绝 ==")
from core.keymap_profiles import KEYMAP_SCHEMES as _KS  # noqa: E402


_KS["__dup_probe__"] = {
    "name": "__dup_probe__",
    "description": "人为构造的重复方案",
    "overrides": {
        "file.save": "Ctrl+S",
        "file.new": "Ctrl+S",   # 与上一条重复
    },
}
try:
    ok_dup, probs_dup = validate_scheme("__dup_probe__")
    check("重复方案 validate 返回 False", not ok_dup, "")
    check("重复方案给出可读原因",
          any("重复" in p for p in probs_dup), str(probs_dup[:1]))

    class _FakeMgr:
        def __init__(self):
            self.actions = {}
            self.defaults = {}
            self.calls = []

        def reset_to_defaults(self, path=None):
            self.calls.append("reset")
            return True

        def set_shortcut(self, name, sc):
            self.calls.append(("set", name, sc))
            return True

    fake = _FakeMgr()
    res = apply_scheme(fake, "__dup_probe__")
    check("重复方案 apply_scheme 返回 False", res is False, str(res))
    check("拒绝时**没有**动过任何快捷键（不留半坏状态）",
          fake.calls == [], str(fake.calls))
finally:
    _KS.pop("__dup_probe__", None)

# ============================================================
# 3. 真实 MainWindow：动作是否真的注册了
# ============================================================
print()
print("== 3. 真实 MainWindow / ActionManager 接线 ==")
from ui.main_window import MainWindow  # noqa: E402


win = MainWindow()
acts = getattr(win.act_mgr, 'actions', {}) or {}
check("ActionManager 里注册了核心动作（此前为 0）",
      len(acts) >= 30, "%d 个" % len(acts))
core_names = [k for k in acts if not str(k).startswith(("plugin.", "misc."))]
check("存在具名核心动作（非 misc./plugin.）",
      len(core_names) >= 10,
      ", ".join(sorted(core_names)[:6]))

# 方案里引用的每个 action 名都必须真实存在
referenced = set()
for _k, v in KEYMAP_SCHEMES.items():
    referenced.update((v.get("overrides") or {}).keys())
missing = sorted(n for n in referenced if n not in acts)
check("方案引用的动作名全部真实存在", not missing, str(missing))

# 带 ActionManager 的完整校验
for key, label in names:
    ok, probs = validate_scheme(key, action_manager=win.act_mgr)
    check("方案 %s 在真实 ActionManager 上可应用" % key, ok,
          "" if ok else "; ".join(probs[:2]))

# ============================================================
# 4. 套用方案：快捷键真的变了，且全仓无重复
# ============================================================
print()
print("== 4. 套用各方案（真实 ActionManager）==")
for key, label in names:
    if key == "default":
        continue
    res = apply_scheme(win.act_mgr, key)
    check("apply_scheme(%s) 成功" % key, res is True, str(res))

    overrides = get_scheme(key).get("overrides", {}) or {}
    bad = []
    for action_name, want in overrides.items():
        a = win.act_mgr.actions.get(action_name)
        got = sc_of(a) if a else "<动作不存在>"
        if norm(got) != norm(want):
            bad.append("%s: 期望 %s 实际 %s" % (action_name, want, got))
    check("方案 %s 的 overrides 全部落到 QAction 上" % key, not bad,
          "; ".join(bad[:2]) if bad else "%d 条" % len(overrides))

    dups = duplicate_shortcuts(win)
    check("套用 %s 后全仓无重复快捷键" % key, not dups,
          str(dups[:2]) if dups else "0 处")

# ============================================================
# 5. default 方案：恢复默认而不是清空
# ============================================================
print()
print("== 5. default 方案恢复默认（而非清空）==")
apply_scheme(win.act_mgr, "vscode")
save_action = win.act_mgr.actions.get("file.save")
check("套用 vscode 后 file.save == Ctrl+S",
      sc_of(save_action) == "Ctrl+S" if save_action else False,
      sc_of(save_action) if save_action else "<无>")

res = apply_scheme(win.act_mgr, "default")
check("apply_scheme(default) 成功", res is True, str(res))
after = sc_of(save_action) if save_action else ""
check("恢复默认后 file.save 仍为 Ctrl+S（未被清空）",
      after == "Ctrl+S", repr(after))

# 找一个**没有**被任何方案覆盖的动作，确认它也没被清空
untouched = None
for name, a in acts.items():
    if str(name).startswith("misc.") and sc_of(a):
        untouched = (name, a)
        break
check("存在自动注册的 misc.* 动作（快捷键编辑器不再是空表）",
      untouched is not None,
      untouched[0] if untouched else "无")

# ============================================================
# 6. 持久化
# ============================================================
print()
print("== 6. QSettings 持久化 ==")
from ui.keymap_editor import (  # noqa: E402
    apply_saved_scheme,
    load_saved_scheme,
    save_scheme,
)


old = load_saved_scheme()
try:
    save_scheme("vim")
    check("save_scheme('vim') → load_saved_scheme() == 'vim'",
          load_saved_scheme() == "vim", load_saved_scheme())
    check("apply_saved_scheme(act_mgr) 返回 True",
          apply_saved_scheme(win.act_mgr) is True, "")
    check("应用后 file.save 仍存在",
          sc_of(win.act_mgr.actions.get("file.save")) == "Ctrl+S" if
          win.act_mgr.actions.get("file.save") else False, "")

    save_scheme("default")
    check("保存 default 后 apply_saved_scheme 返回 False（无需应用）",
          apply_saved_scheme(win.act_mgr) is False, "")

    # 非法 key 必须回退到 default，而不是抛异常/返回垃圾
    save_scheme("__bogus__")
    check("非法方案 key 回退为 'default'",
          load_saved_scheme() == "default", load_saved_scheme())
finally:
    save_scheme(old)

# ============================================================
# 7. 真实 KeymapEditor：方案下拉存在且可用
# ============================================================
print()
print("== 7. 真实 KeymapEditor 方案下拉 ==")
from ui.keymap_editor import KeymapEditor  # noqa: E402


ed = KeymapEditor(win.act_mgr, win)
check("编辑器有 scheme_combo", hasattr(ed, "scheme_combo"), "")
check("下拉项数 == 方案数",
      ed.scheme_combo.count() == len(names),
      "%d vs %d" % (ed.scheme_combo.count(), len(names)))
check("下拉项的 userData 是方案 key",
      [ed.scheme_combo.itemData(i) for i in range(ed.scheme_combo.count())]
      == [k for k, _ in names], "")
check("编辑器有「套用」按钮", hasattr(ed, "apply_scheme_btn"), "")
ed.close()

print()
print("=" * 96)
print("结果：通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
print("=" * 96)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)
sys.exit(1 if FAIL else 0)
