# 插件功能增强建议（逐插件，2026-11-13）

> 基于插件审计（`docs/plugin_audit_2026-11-13.md`）与现有 PluginAPI 能力（selection/diagnostics/decorations/background/panel/provider/i18n）。

## P0：优先增强

### ai_assistant（AI 助手）
1. **流式输出 + 取消**：`run_background` 增量 `insert_text`，提供停止按钮与超时；
2. **选区操作**：解释/重构/生成测试，先 diff 预览再 `replace_selected_text`；
3. **上下文控制**：当前文件/选中代码/项目索引三档，显示 token 估算；
4. **Provider 抽象**：OpenAI/Ollama/自定义 base_url、失败回退、隐私模式（禁网）；
5. **代码审查模式**：对 diff 输出问题并 `publish_diagnostics`；
6. **测试生成闭环**：生成 pytest 用例 → 后台运行 → 结果面板；
7. **工程**：拆分至 ≤1,300 行/模块，补超时/取消/异常测试。
> 工作量：3–4 周；收益最高。

### git_deep（Git 深度集成）
1. **命令参数化（去 shell）**：白名单 git 子命令 + 参数数组，超时/输出上限；
2. **状态栏**：分支、ahead/behind、脏文件数；
3. **Diff/暂存**：文件 diff 查看器、hunk 级 stage/unstage；
4. **常用操作**：分支切换/新建、stash、amend、提交模板；
5. **Blame**：行内 `add_decoration` 显示作者/提交；
6. **冲突**：冲突标记导航与“采用当前/传入”；
7. **性能**：异步状态缓存，大仓库不阻塞 UI。
> 工作量：2–3 周。

## P1：体验增强

### json_formatter
- JSONC/JSON5/JSONL 支持；JSON Schema 校验；
- 选区格式化、format-on-save 开关、按项目缩进/排序策略；
- 错误 `goto_line` + 高亮；大文件保护（>10MB 提示）；
- 路径查询/提取（jq-lite）。

### wordcount
- 选区统计、阅读时间、CJK 词数策略；
- 目标字数进度（状态栏进度条/颜色）；
- 排除注释/字符串模式；大文件保护；
- 点击状态栏打开面板；历史趋势/CSV 导出。

### logtail
- 多文件标签、tail/follow 开关、暂停/继续；
- 正则过滤与高亮、错误行跳转；
- 日志轮转检测、编码检测、环形缓冲内存上限；
- 从“运行任务”自动打开对应日志。

### markdown_preview
- 同步滚动、代码高亮、TOC、任务列表；
- Mermaid/数学公式、图片粘贴/拖拽；
- 导出 HTML/PDF、主题跟随、分屏方向切换；
- 大文档增量渲染 + 防抖。

### python_debugger
- 条件/日志断点、监视表达式、变量编辑；
- 异常暂停、调用栈帧切换、表达式求值控制台；
- pytest 集成、断点持久化；
- 拆分 1,965 行；高风险权限逐次确认 + 签名要求（后续多进程/attach）。

### spell_check
- 用户/项目词典、忽略一次/文件；
- camelCase/snake_case 拆分；字符串/注释可配置检查；
- 多语言词典；右键建议菜单；诊断严重级别；
- 大文件增量检查；迁移标准沙箱运行时并保留诊断 UI。

### todo_panel
- 点击跳转、按文件/标签/优先级分组、搜索过滤；
- 自定义模式（`.qctodo`）、截止日期/负责人；
- 编辑器高亮（`add_decoration`）、工作区统计、自动刷新。

### whitespace_sandbox
- 一键修复：trim trailing whitespace / tab→space；
- 可配置最大行宽、忽略 glob、严重级别；
- format-on-save 集成；补测试覆盖。

## P2：样例与一致性

### sandbox_demo
- 扩展示例：hover/completion/code-action 走沙箱 RPC；
- 文档化 manifest 能力声明与限制。

### demo
- 作为“插件开发模板”：展示 provider/status/settings/panel/i18n/测试；
- 增加交互式开发向导入口（可选）。

### my_plugin
- 改为脚手架生成示例（命令+状态+设置+i18n+测试）；
- 或从默认插件目录移除，避免市场噪音。

### wordcount_sandbox
- 对齐 wordcount 功能（选区/阅读时间/CJK/目标）；
- 迁移远程面板协议，作为沙箱能力回归样例。

## 共性工程建议

1. **统一 i18n**：新增文案全部 `_tr()`，保持 ja/ko 100%；
2. **设置页**：每个插件注册 `settings_schema`，纳入“工具 → 插件设置”；
3. **命令面板**：为常用动作 `register_command`，提升发现性；
4. **后台任务**：网络/大文件操作走 `run_background`，UI 不阻塞；
5. **测试**：核心插件 ≥8 用例，覆盖权限拒绝/大文件/异常路径；
6. **安全**：高风险插件（git_deep/python_debugger/ai_assistant）优先迁移沙箱/签名信任。

## 建议排期

| 周 | 内容 |
|---|---|
| W1–2 | git_deep 去 shell + 状态栏/分支；ai 流式+取消+选区 |
| W3–4 | ai provider/隐私模式/审查；git diff/stage |
| W5–6 | python_debugger 拆分 + 条件断点；spell_check 词典 |
| W7–8 | wordcount/logtail/markdown/todo 体验项；样例清理 |
