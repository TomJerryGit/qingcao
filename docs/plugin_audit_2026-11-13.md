# 青草编辑器插件全面审计与评价（2026-11-13）

> 范围：`plugins/` 下全部 **14 个插件**；方法：清单/源码静态分析、激活耗时剖析（`tools/profile_plugin_load.py`）、隔离兼容性探测、测试覆盖统计。原始数据：`data/plugin_audit.json`。

## 总评：**8.0 / 10**

- 功能广度好（AI/Git/JSON/日志/Markdown/拼写/TODO/字数/调试/沙箱示例）；
- 主要短板：**沙箱覆盖率低**（仅 3/14 个 manifest 沙箱）、高风险权限插件仍在进程内、部分插件体量大/测试少；性能整体可接受（除 AI 插件 0.28s）。

## 一、插件清单与画像

| 插件 | 功能 | 行数 | 权限 | 激活耗时* | 测试文件 | 隔离兼容 |
|---|---|---|---|---|---|---|
| ai_assistant | AI 解释/重构/测试生成/面板 | 3,299 | network, editor_read/write, dialog | **0.284s**（延后） | 10 | ❌（UI/网络/高风险） |
| demo | 最小示例 | 36 | editor_read, dialog | 0.001s | 35（通用） | ✅ |
| git_deep | Git 状态/提交/推送 | 187 | **process**, filesystem, dialog | 0.017s | 4 | ❌（需 editor/host） |
| json_formatter | JSON 格式化/压缩/验证 | 279 | editor_read/write, dialog | 0.023s | 4 | ✅ |
| logtail | 日志实时监视 | 259 | filesystem, dialog | 0.018s | 3 | ⚠️ 激活但无 UI 桥 |
| markdown_preview | Markdown 分屏预览 | 228 | editor_read, dialog | 0.018s | 5 | ❌ |
| my_plugin | 脚手架占位 | 43 | — | 0.019s | 1 | ❌ |
| python_debugger | 断点/单步/变量/调用栈 | 1,965 | **process**, editor_read/write, dialog | 0.031s | 7 | ❌（高风险/UI） |
| sandbox_demo | 沙箱只读符号示例（禁用） | 31 | editor_read | — | 5 | ✅（既有沙箱） |
| spell_check | 英文拼写检查 | 340 | editor_read, filesystem | ≤0.003s | 9 | ❌ |
| todo_panel | TODO/FIXME 面板 | 323 | filesystem, editor_read, dialog | 0.002s | 4 | ⚠️ 激活但无 UI 桥 |
| whitespace_sandbox | 行尾空白/Tab/超长行诊断 | 43 | editor_read | ≤0.003s | 2 | ✅（既有沙箱） |
| wordcount | 字数统计面板/状态栏 | 264 | editor_read, dialog | 0.001s | 11 | ✅（远程面板） |
| wordcount_sandbox | 沙箱字数统计试点 | 26 | editor_read | ≤0.003s | 4 | ✅（既有沙箱） |

\* cProfile 下的相对值；真实启动中 ai_assistant 已声明延后激活（约 0.1–0.3s 后台）。

## 二、逐项评价

### 优秀（≥8.5）
- **wordcount（9.0）**：功能清晰、远程面板/状态栏、测试 11、隔离可用；建议保留为隔离范本。
- **json_formatter（9.0）**：279 行、provider + 菜单、隔离可用；建议补更多 JSON 边界测试。
- **demo（9.0）**：最小示例 + 35 个相关测试；作为模板价值高。
- **whitespace_sandbox（8.5）**：沙箱只读诊断，安全示范。

### 良好（7.5–8.4）
- **ai_assistant（8.0）**：功能最丰富，但 3,299 行、network 权限、延迟加载；建议拆分 `ai_panel/ai_client/ai_inline` 并做网络超时/取消测试。
- **python_debugger（8.0）**：功能强（bdb 后端），1,965 行、process 权限；建议拆分调试会话/UI，并纳入签名信任要求。
- **git_deep（7.5）**：刚需，但 process 权限 + 隔离不兼容；建议改为调用参数化 git 命令白名单（禁止 shell）。
- **logtail（7.5）**：实用；需远程面板适配后才能隔离。
- **markdown_preview（7.5）**：预览体验；依赖主窗口/Qt，隔离暂不可行。
- **todo_panel（7.5）**：面板型；需远程面板协议。
- **spell_check（7.5）**：已有 manifest 沙箱，但只有诊断类 API；建议迁移到标准 sandbox 运行时并补 UI 入口。
- **wordcount_sandbox（7.5）**：试点样例，功能少但验证沙箱路径。

### 待改进（<7.5）
- **my_plugin（5.0）**：脚手架占位、1 个测试；建议移除或标注“示例”。
- **sandbox_demo（6.5）**：默认禁用；保留为文档示例即可。

## 三、横切问题

1. **沙箱覆盖率**：14 个中仅 3 个 `sandbox:true`（21%）；B2.1 额外隔离 3 个（demo/wordcount/json_formatter，仅 demo 模式）。高风险 `git_deep`/`python_debugger`/`ai_assistant` 仍在主进程。
2. **安全**：`process`（git_deep、python_debugger）、`network`（ai_assistant）为高风险权限；第一方插件未做 Ed25519 校验（市场流程才有）；建议对高风险插件强制签名/逐次确认。
3. **性能**：插件激活总计约 0.4s（含 AI 0.28s，但已延后）；其余插件 ≤0.03s，可接受；启动耗时主要不在插件。
4. **可维护性**：ai_assistant 3,299 行、python_debugger 1,965 行为长尾；建议纳入架构门禁（≤1,300）。
5. **重复/样例**：wordcount 与 wordcount_sandbox、whitespace_sandbox；demo/my_plugin/sandbox_demo 为样例，建议明确“示例”分类。
6. **测试覆盖不均**：my_plugin 1、logtail 3、git_deep 4、json_formatter 4；核心插件建议 ≥8 个用例。
7. **隔离不兼容根因**：`_host_window()`/Qt Widget 直建（logtail/todo/markdown/wordcount）、provider API（spell_check）、高风险/UI（ai/debugger）。

## 四、建议路线（优先级）

| 优先级 | 动作 | 目标 |
|---|---|---|
| P0 | git_deep 命令参数化（去 shell）+ 高风险权限确认 | 消除命令注入面 |
| P0 | ai_assistant 拆分至 ≤1,300 行/模块，网络请求超时/取消测试 | 可维护+可靠 |
| P1 | python_debugger 拆分；高风险插件签名要求 | 架构+安全 |
| P1 | logtail/todo_panel 接入远程面板协议（B2.2） | 扩大隔离覆盖 |
| P1 | spell_check 迁移标准 sandbox 运行时 | 沙箱覆盖 4/14 |
| P2 | 样例插件分类/清理（my_plugin、sandbox_demo） | 市场清晰度 |
| P2 | 插件测试补齐（核心 ≥8 用例） | 质量门禁 |

## 五、结论

插件生态“可用且实用”，头部质量（wordcount/json_formatter/demo）达标；**安全隔离与高风险权限治理**是下一阶段重点，其次是 AI/调试器的体量与测试。建议结合沙箱 B2.2（远程面板/扩展点）与签名信任策略推进。
