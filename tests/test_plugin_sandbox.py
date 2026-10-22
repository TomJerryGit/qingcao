# -*- coding: utf-8 -*-
"""插件安全沙箱审计测试（P2 第一阶段）"""
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS = os.path.join(ROOT, "plugins")


def _write_plugin(tmp_path, name, manifest_perms, code):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.json").write_text(json.dumps({
        "name": name, "display_name": name, "version": "1.0.0",
        "description": "test", "author": "t", "license": "MIT",
        "type": "plugin", "category": "tool", "tags": [],
        "permissions": manifest_perms, "api_version": "2.0.0",
        "enabled": True, "auto_load": True,
    }, ensure_ascii=False), encoding="utf-8")
    (d / "__init__.py").write_text(code, encoding="utf-8")
    return str(d)


def test_clean_plugin_passes(tmp_path):
    from infrastructure.plugin_sandbox import audit_plugin

    d = _write_plugin(tmp_path, "clean", ["editor_read"],
                      "def helper(x):\n    return x + 1\n")
    r = audit_plugin(d)
    assert r.verdict == "pass"
    assert r.findings == []


def test_network_import_without_permission_is_review(tmp_path):
    from infrastructure.plugin_sandbox import audit_plugin

    d = _write_plugin(tmp_path, "net", ["editor_read"],
                      "import socket\nsocket.socket()\n")
    r = audit_plugin(d)
    assert r.verdict == "review"
    assert "network" in r.missing_permissions
    assert any(f.code == "SBX101" for f in r.findings)


def test_network_declared_passes(tmp_path):
    from infrastructure.plugin_sandbox import audit_plugin

    d = _write_plugin(tmp_path, "net2", ["editor_read", "network"],
                      "import socket\nsocket.socket()\n")
    r = audit_plugin(d)
    assert r.verdict == "warn"
    assert r.missing_permissions == []


def test_process_and_filesystem_calls(tmp_path):
    from infrastructure.plugin_sandbox import audit_plugin

    d = _write_plugin(
        tmp_path, "proc", ["editor_read"],
        "import os\nimport shutil\n"
        "os.system('dir')\n"
        "shutil.rmtree('/tmp/x')\n"
        "open('a.txt', 'w').write('x')\n")
    r = audit_plugin(d)
    perms = {f.permission for f in r.findings}
    assert "process" in perms and "filesystem" in perms
    assert r.verdict == "review"
    assert {"process", "filesystem"} <= set(r.missing_permissions)


def test_dangerous_dynamic_code_rejects(tmp_path):
    from infrastructure.plugin_sandbox import audit_plugin

    d = _write_plugin(tmp_path, "evil", ["editor_read"],
                      "eval('1+1')\nexec('x=1')\n")
    r = audit_plugin(d)
    assert r.verdict == "review", "danger 需人工评审而非自动拒绝"
    assert any(f.permission == "danger" for f in r.findings)
    assert any(f.code == "SBX103" for f in r.findings)


def test_root_audit_covers_all_builtin_plugins():
    from infrastructure.plugin_sandbox import audit_plugins_root

    results = audit_plugins_root(PLUGINS)
    assert len(results) >= 10, "内置插件应 >= 10 个: %d" % len(results)
    names = {os.path.basename(r.plugin_dir) for r in results}
    assert "spell_check" in names
    # 内置插件不允许 reject；danger 项（如调试器 eval）只进人工评审
    rejects = [r for r in results if r.verdict == "reject"]
    assert not rejects, [(r.plugin_dir,
                          [f.message for f in r.findings])
                         for r in rejects]
    names = {os.path.basename(r.plugin_dir): r.verdict for r in results}
    assert names.get("python_debugger") in ("review", "warn", "pass")
    assert names.get("spell_check") != "review", names.get("spell_check")


def test_check_against_baseline(tmp_path):
    from infrastructure.plugin_sandbox import AuditResult, check_against_baseline

    def _res(name, verdict):
        r = AuditResult()
        r.plugin_dir = os.path.join(str(tmp_path), name)
        r.verdict = verdict
        return r

    results = [_res("clean", "pass"), _res("known", "review"),
               _res("newbie", "warn")]
    violations = check_against_baseline(results, {"known": "review"})
    assert len(violations) == 1 and "newbie" in violations[0]
    assert check_against_baseline(
        results, {"known": "review", "newbie": "warn"}) == []


def test_baseline_file_covers_current_plugins():
    import subprocess
    import sys as _sys
    baseline = os.path.join(ROOT, "tools", "plugin_audit_baseline.json")
    assert os.path.exists(baseline)
    r = subprocess.run(
        [_sys.executable, "-m", "tools.audit_plugins",
         "--baseline", baseline],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout + r.stderr
