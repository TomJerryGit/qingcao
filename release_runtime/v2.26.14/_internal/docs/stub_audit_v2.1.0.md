# 空壳功能审计（v2.1.0）

> 生成方式：`tools/audit_stubs.py` + `tools/audit_orphan_modules.py`
> 判据均为**可自动检测**的（占位实现 / 显式未实现 / 伪成功 / 零引用），
> 每一条都附文件行号，可自行复核。

## 结论摘要

| 类别 | 数量 | 说明 |
|---|---|---|
| **A. 完整实现但零接线**（最可惜） | 11 个模块 | 代码是真的，只是没人调用 |
| **B. 半接线**（有入口但做不到位） | 4 项 | 用户会察觉"点了效果不对" |
| **C. 假开关/假能力**（误导用户） | 2 项 | 界面有、实际无效 |
| **D. 能力在但无界面**（用户看不见） | 3 项 | 后端完整、没有入口 |

---

## A. 完整实现但零接线（代码是真的，没人调用）

这些不是"空壳代码"，而是**被遗弃的完整实现** —— 删了可惜、留着无用。

| 模块 | 行数 | 提供的能力 | 现状 |
|---|---|---|---|
| `core/file_merge.py` | 197 | 三方合并（`ThreeWayMerger`）、合并冲突检测 | 零引用；配套 UI `ui/file_merge_dialog.py` 也已孤立 |
| `core/code_smell.py` | 180 | 代码坏味道检测（`SmellDetector`） | 零引用；无任何 UI 入口 |
| `core/code_metrics.py` | — | 圈复杂度等代码指标 | 仅 `tools/` 引用 |
| `core/formatter.py` | 147 | **Black / Autopep8 / Clang-Format** 三种格式化器 | 零引用（`main.py` 里的 `Formatter` 是 `logging.Formatter`，无关） |
| `core/exporter.py` | 157 | 导出（PDF/HTML 等；依赖 `reportlab`） | 零引用 |
| `core/refactor_session.py` | 158 | AI 重构会话（`RefactorSession`/`Message`/`RefactorIteration`） | 零引用；`ui/refactor_dialog.py` 已删除 |
| `core/crash_stats.py` | 240 | 崩溃统计分析（`get_top_exceptions`/`should_notify`/`cleanup_old`） | **零引用**；`crash_reporter.py` 不用它 |
| `core/project_config.py` | 132 | 项目配置模型（`ProjectConfig`） | 零引用 |
| `core/workspace.py` | 115 | 多根工作区（`Workspace`/`WorkspaceFolder`） | 零引用 |
| `core/key_sequence_manager.py` | 189 | 多键序列（如 VS Code 的 `Ctrl+K Ctrl+S`） | 零引用 |
| `ui/lsp_panel.py` | 548 | LSP 状态面板 + **语言服务器安装向导**（`LspInstallerDialog`） | 零引用（仅 `tools/verify_patches.py` 检查其存在） |
| `ui/undo_history_panel.py` | 229 | 撤销历史面板 | 零引用（撤销栈本身已实现） |
| `ui/collab_dialog.py` | 230 | 协同编辑 | 零引用（`core/collab.py` 仅它引用） |
| `ui/snapshot_manager_dialog.py` | 153 | 快照管理 | 零引用 |
| `ui/task_panel.py` | 188 | 项目任务面板 | 零引用 |
| `ui/snippet_market_dialog.py` | 221 | 代码片段市场 | 零引用 |
| `ui/profiler_panel.py` | 165 | 性能剖析面板 | 零引用 |
| `ui/help_browser.py` | 280 | 离线帮助浏览器（`show_help(parent, topic)`） | 零引用；帮助菜单用的是内联对话框 |

**最可惜的三个**：

1. **`core/formatter.py`** —— 三种格式化器都是真实实现（会真的调 `black` 子进程），
   只差一个菜单项。
2. **`ui/lsp_panel.py` 的 `LspInstallerDialog`** —— 548 行，含语言服务器
   **安装向导**。用户现在启用 LSP 失败时只能在状态栏看到"请 pip install"，
   而这个对话框就是为此准备的。
3. **`core/file_merge.py`** —— 完整的**三方合并**算法，无 UI。

---

## B. 半接线（有入口，但做不到位）

这些是用户**点得到、但效果不对**的地方 —— 也是我在本轮明确标注过的。

| 功能 | 现状 | 位置 |
|---|---|---|
| **LSP 重命名** | 只**报告**会影响多少处，**不实际改动**。状态栏文案已如实写"跨文件应用尚未实现" | `ui/main_window.py::_on_lsp_rename_applied` |
| **LSP 代码操作** | 弹出选单让用户选，但选中后只提示"应用尚未实现"，**不执行** | `ui/main_window.py::_on_lsp_code_actions` |
| **LSP 查找引用** | 列出位置，但**点击不能跳转** | `ui/main_window.py::_on_lsp_references` |
| **调试器断点** | 断点能设、能停；但**变量查看只读局部变量**，无表达式求值 UI、无监视窗口 | `plugins/python_debugger/panel.py` |

> 说明：这些不是"假"，而是**能力未完成**。我已让状态栏文案如实说明，
> 不假装完成。

---

## C. 假开关 / 假能力（最需要警惕）

| 项 | 现状 | 处置 |
|---|---|---|
| **国际化** | 曾提供 4 种语言选择，但切换后界面**依然全中文** —— 无一条 `tr()`、`.qm` 路径拼错、翻译仅 49 条 | **本轮已移除**，改为如实标注"仅中文" |
| **`ui/tips.py` / `help_browser` 的快捷键说明** | 曾教用户"按 Alt+C 进列模式"等，而该键当时因双绑定失效 | 本轮已随快捷键修复同步更新 |

---

## D. 能力在但无界面（用户看不见）

| 能力 | 实现位置 | 用户可见性 |
|---|---|---|
| **崩溃统计分析** | `core/crash_stats.py`（240 行） | ❌ 无任何入口；崩溃时会弹报告对话框，但**历史统计**看不到 |
| **代码指标/坏味道** | `core/code_metrics.py`、`core/code_smell.py` | ❌ 只能在 `tools/` 里跑 |
| **导出（PDF/HTML）** | `core/exporter.py` | ❌ 无入口（依赖 `reportlab`，且是可选依赖） |

---

## 已核实**不是**空壳的部分（避免误判）

- **插件 API**：`PluginAPI` 共 49 个公开方法，逐个检查后只有
  `on_activate` / `on_deactivate` 是基类覆写点（`pass` 是设计如此），
  **没有空壳方法**。
- **`core/local_completer.py`**、**`core/lsp_client.py`**、
  **`SessionManager.start_autosave`** 等此前的"零调用"项
  **本轮已全部接线**。
- 各类 `pass` 大多是：抽象基类方法（`ContentProvider`）、
  Qt 事件重写、测试替身、异常兜底分支 —— 属正常实现。

---

## 建议的处置优先级

| 优先级 | 动作 | 成本 |
|---|---|---|
| **P1** | 接 `core/formatter.py`（三种格式化器）→ 工具菜单"格式化文档" | 低（~20 行） |
| **P1** | 接 `LspInstallerDialog`（安装向导）→ LSP 失败时引导安装 | 低 |
| **P2** | 接 `ui/undo_history_panel.py`（撤销栈已实现） | 中 |
| **P2** | 补 LSP 重命名/代码操作的实际应用（跨文件 `WorkspaceEdit`） | 高 |
| **P3** | 接 `core/file_merge.py` + 重建合并 UI | 高 |
| **P3** | 接 `crash_stats` 到崩溃报告界面（让用户看到历史统计） | 低 |
| **P4** | 其余孤立模块：删除或按需接线 | — |

> 注意：D1 之外还有 **42 个被 `addopts` 排除的"审计预期失败"测试**，
> 其中仍有约 28 个真实失败（内容源过期、撤销栈失效、主题色覆盖、
> 三方合并丢内容、Git 路径解析等）。那是**已写好的缺陷规格书**，
> 建议优先于本表的 P3/P4。
