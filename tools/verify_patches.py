# tools/verify_patches.py （精简版，放在 tools/ 下）
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
results = []


def check(rel, pattern, should_exist=True, desc=""):
    p = ROOT / rel
    if not p.exists():
        print(f"[FAIL] {rel} 不存在")
        results.append(False)
        return
    content = p.read_text(encoding='utf-8')
    has = bool(__import__('re').search(pattern, content))
    ok = has == should_exist
    results.append(ok)
    flag = "[OK]  " if ok else "[FAIL]"
    print(f"{flag} {rel}: {desc}")


def check_py(rel):
    p = ROOT / rel
    if not p.exists():
        return
    try:
        ast.parse(p.read_text(encoding='utf-8'))
        results.append(True)
        print(f"[OK]   {rel} 语法")
    except SyntaxError as e:
        results.append(False)
        print(f"[FAIL] {rel}: line {e.lineno}: {e.msg}")


check("ui/command_palette.py", r"qss = getattr\(theme, 'qss', ''\)",
      True, "补丁 1")
check("ui/command_palette.py", r"if 'qss' in theme:", False, "补丁 1 旧代码")
check("build.py", r"'core\.search_worker'", False, "补丁 3")
check("ui/directory_tree.py", r"_git_status_cache", True, "补丁 4")
check("ui/editor_view.py", r"get_snippet_manager", True, "补丁 5")
check("app/menus.py", r"\[DEPRECATED\]", True, "补丁 9")
check("ui/main_window.py", r"self\._closing = False", True, "补丁 10")
check("ui/lsp_panel.py", r"_one_shot_finished", True, "补丁 11")
check("ui/welcome_widget.py", r"bus\.file_opened\.connect", True, "补丁 13")
check("build.py", r"clean_spec", True, "补丁 15")

for f in ["build.py", "main.py", "ui/main_window.py",
          "ui/command_palette.py", "ui/directory_tree.py",
          "ui/editor_view.py", "ui/lsp_panel.py",
          "ui/welcome_widget.py"]:
    check_py(f)

print()
print("=" * 60)
print(f"通过: {sum(results)} / {len(results)}")
print("=" * 60)
sys.exit(0 if all(results) else 1)