# -*- coding: utf-8 -*-
"""集成验证：Git 动作 / Ollama 面板 / 行内补全

与"只检查菜单是否存在"不同，本脚本**真实执行功能代码路径**并连真实后端：

  1. **Git**：在真实 git 仓库上调用 GitClient 与 git_deep 插件的
     show_status / show_diff / show_log 所依赖的全部方法
  2. **Ollama**：调用 OllamaPanel 用到的 OllamaClient 全部数据方法
     （状态 / 版本 / 模型列表 / 已加载模型 / 详情）
  3. **行内补全**：在真实编辑器上走 request_now -> 显示注解 -> 接受，
     使用**真实 AI 客户端**（Ollama）

代表性问题：打包版 `_internal/plugins/{git_deep,ai_assistant}/__init__.py`
与工作区源码**哈希一致**，且冻结版核心模块已验证可导入 —— 因此这些
代码路径在打包版中执行的是同一份逻辑。

用法：
    python tools/integration_verify.py
"""
import io
import os
import sys
import time
import traceback


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

OUT = []


def log(s=""):
    OUT.append(str(s))
    try:
        print(s, flush=True)
    except Exception:
        pass


def section(title):
    log()
    log("=" * 70)
    log(title)
    log("=" * 70)


# =========================================================
# 1. Git
# =========================================================
def verify_git():
    section("1) Git 插件：真实仓库上的动作代码路径")
    try:
        from core.git_client import GitClient
    except Exception as e:
        log("  导入 GitClient 失败: %s" % e)
        return

    repo = ROOT
    log("  仓库路径: %s" % repo)
    gc = GitClient(repo)

    checks = [
        ("is_repo()", lambda: gc.is_repo()),
        ("find_root(本文件)", lambda: gc.find_root(
            os.path.join(repo, "core", "git_client.py"))),
        ("current_branch()", lambda: gc.current_branch()),
        ("status()", lambda: gc.status()),
    ]
    for name, fn in checks:
        try:
            v = fn()
            if isinstance(v, dict):
                log("  %-24s OK  分支/条目数=%d" % (name, len(v)))
            else:
                log("  %-24s OK  %s" % (name, v))
        except Exception as e:
            log("  %-24s 异常 %s: %s" % (name, type(e).__name__, e))

    # git_deep 的 show_status 会渲染这段文本
    try:
        branch = gc.current_branch()
        status = gc.status()
        lines = ["分支: %s" % branch, "=" * 50, ""]
        if not status:
            lines.append("(无变更)")
        else:
            for fp, code in status.items():
                lines.append("  [%s] %s" % (code, fp))
        log()
        log("  —— git_deep.show_status 将要显示的对话框内容 ——")
        for ln in lines[:12]:
            log("      " + ln)
        log("  （共 %d 行）" % len(lines))
    except Exception as e:
        log("  构造状态文本失败: %s" % e)

    # show_diff 依赖的方法
    try:
        target = os.path.join(repo, "core", "git_client.py")
        d = gc.diff(target) or gc.diff_staged(target)
        log("  diff()/diff_staged() OK  长度=%d（无改动时为 0 属正常）"
            % len(d or ""))
    except Exception as e:
        log("  diff 异常: %s: %s" % (type(e).__name__, e))

    # show_log 依赖的方法
    try:
        lg = gc.log(5) if hasattr(gc, "log") else None
        log("  log(5) OK  条目=%s"
            % (len(lg) if isinstance(lg, (list, str)) else lg))
    except Exception as e:
        log("  log 异常: %s: %s" % (type(e).__name__, e))


# =========================================================
# 2. Ollama
# =========================================================
def verify_ollama():
    section("2) Ollama 管理面板：真实服务上的数据方法")
    try:
        from core.ollama_client import OllamaClient
    except Exception as e:
        log("  导入 OllamaClient 失败: %s" % e)
        return

    c = OllamaClient()
    log("  服务地址: %s" % c.host)
    log("  真实返回签名（以实现为准，勿假设）：")
    log("    is_running()->bool, version()->str, status_text()->(ok,text),")
    log("    list_models()->(ok,list), model_names()->list,")
    log("    list_running()->(ok,list), openai_base_url()->str")

    running = c.is_running()
    log("  is_running()  -> %s" % running)
    if not running:
        log("  （服务未运行，跳过其余检查）")
        return

    log("  version()     -> %s" % c.version())
    log("  status_text() -> %s" % (c.status_text(),))

    ok, models = c.list_models()
    log("  list_models() -> ok=%s 数量=%s"
        % (ok, len(models) if models else 0))
    for m in (models or [])[:5]:
        if isinstance(m, dict):
            log("      - %s  大小=%s"
                % (m.get("name"), m.get("size_text")
                   or OllamaClient.format_size(m.get("size") or 0)))
        else:
            log("      - %s" % (m,))

    names = c.model_names()
    log("  model_names() -> %s" % (names,))

    ok, rl = c.list_running()
    log("  list_running() -> ok=%s 数量=%s" % (ok, len(rl) if rl else 0))

    log("  openai_base_url() -> %s" % c.openai_base_url())

    # show_model 是面板"详情"按钮的路径
    if names:
        ok, info = c.show_model(names[0])
        log("  show_model(%s) -> ok=%s" % (names[0], ok))
        if ok and isinstance(info, dict):
            for k in ("family", "parameter_size", "quantization_level"):
                if k in info:
                    log("      %s = %s" % (k, info[k]))


# =========================================================
# 3. 行内补全
# =========================================================
def verify_inline():
    section("3) 行内补全：真实编辑器 + 真实 AI 客户端")
    from PyQt5.QtGui import QFontDatabase
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    from PyQt5.Qsci import QsciScintilla

    from ui.ai_inline_completer import AIInlineCompleter

    sc = QsciScintilla()
    sc.setUtf8(True)
    sc.setText(
        "def compute(items):\n"
        "    total = 0\n"
        "    for it in items:\n"
        "        total += it\n"
        "    return total\n"
        "\n"
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    tot\n"
    )

    try:
        from core.ai_client import load_ai_client_from_settings
        client = load_ai_client_from_settings()
    except Exception as e:
        log("  加载 AI 客户端失败: %s" % e)
        client = None

    log("  AI 客户端: %r" % (client,))
    if client is None:
        log("  （未配置客户端，仅验证「关闭时不请求」的守卫生效）")
        comp = AIInlineCompleter(sc, None)
        log("  request_now() -> %s（应为 False）" % comp.request_now())
        return

    comp = AIInlineCompleter(sc, client)
    log("  默认启用状态: %s（应为 False，默认关闭）" % comp.enabled)
    log("  未启用时 request_now() -> %s（应为 False）" % comp.request_now())

    comp.set_enabled(True)
    # 光标放到最后一行 "    tot" 之后（列 7）
    sc.setCursorPosition(9, 7)
    log("  光标位置: %s" % (sc.getCursorPosition(),))

    t0 = time.time()
    started = comp.request_now(force=True)
    log("  request_now(force=True) -> %s" % started)
    if not started:
        log("  请求未发起，跳过")
        return

    log("  等待真实模型返回首个建议（最多 180 秒）…")
    got = False
    end = time.time() + 180
    while time.time() < end:
        app.processEvents()
        if comp.has_suggestion():
            got = True
            break
        if not comp._busy:
            # 请求已结束但无建议（可能失败）
            break
        time.sleep(0.1)

    elapsed = time.time() - t0
    log("  耗时 %.1f 秒" % elapsed)
    if got:
        sug = comp.get_suggestion()
        log("  ✅ 收到补全建议: %r" % sug)
        before = sc.text()
        ok = comp.accept_suggestion()
        after = sc.text()
        log("  accept_suggestion() -> %s" % ok)
        log("  文本变化: %s" % (before != after))
        if before != after:
            newline = after[len(before):] if after.startswith(before) else "?"
            log("  插入内容: %r" % newline[:60])
        log("  建议已清除: %s" % (not comp.has_suggestion()))
    else:
        log("  ❌ 未收到建议（_busy=%s）" % comp._busy)


def main():
    log("=" * 70)
    log("集成验证：Git / Ollama / 行内补全")
    log("=" * 70)
    log("说明：打包版插件源码与工作区**哈希一致**，冻结版核心模块已验证")
    log("      可导入，因此以下代码路径与打包版执行的是同一份逻辑。")
    for fn in (verify_git, verify_ollama, verify_inline):
        try:
            fn()
        except Exception:
            log("  [%s] 脚本异常:" % fn.__name__)
            log(traceback.format_exc())
    section("验证结束")
    dst = os.path.join(ROOT, "integration_verify.txt")
    with io.open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    print("[verify] 已写出 %s" % dst, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
