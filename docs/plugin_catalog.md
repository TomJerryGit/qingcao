# 插件目录

- 插件总数：15
- 沙箱插件：4
- 默认禁用：2

| 插件 | 名称 | 版本 | 分类 | 权限 | 沙箱 | 启用 | 说明 |
|---|---|---|---|---|---|---|---|
| `ai_assistant` | AI 助手 | 2.1.0 | editor | network, editor_read, editor_write, dialog | — | ✅ | AI 助手：自动调试闭环、结果校验、完整 UI 隔离 |
| `markdown_preview` | Markdown 预览 | 1.2.0 | editor | editor_read, dialog, filesystem | — | ✅ | Markdown：目录、HTML 导出、远程面板 |
| `git_deep` | Git 深度集成 | 1.2.0 | integration | editor_read, process, filesystem, dialog | — | ✅ | Git：隔离 hunk 暂存、宿主 API |
| `python_debugger` | Python 调试器 | 2.2.0 | integration | process, editor_read, editor_write, dialog, debugger | — | ✅ | Python 调试器：宿主面板、调试上下文 AI |
| `demo` | Demo | 1.0.0 | other | editor_read, dialog | — | ✅ | 青草编辑器最小示例插件 |
| `my_plugin` | My Plugin | 1.0.0 | other | - | — | — | 脚手架示例（默认禁用） |
| `json_formatter` | JSON 格式化 | 1.2.0 | tool | editor_read, editor_write, dialog | — | ✅ | JSON：JSONL、JSONC、Schema、选区 |
| `line_sort` | 行排序 | 1.1.0 | tool | editor_read, editor_write, dialog | — | ✅ | 行排序：升序/降序/去重（选区或整文件） |
| `logtail` | 日志实时监视 | 1.2.0 | tool | filesystem, dialog | — | ✅ | 日志：过滤高亮、暂停、多文件 |
| `sandbox_demo` | 沙箱示例（实验） | 1.0.0 | tool | editor_read | ✅ | — | 演示 manifest sandbox:true 的只读子进程插件（大纲符号） |
| `spell_check` | 拼写检查 | 1.1.0 | tool | editor_read, filesystem | ✅ | ✅ | 拼写检查：标准沙箱/忽略词/诊断 |
| `todo_panel` | TODO 面板 | 1.1.0 | tool | filesystem, editor_read, dialog | — | ✅ | TODO 面板：扫描/远程面板/跳转 |
| `wordcount` | 字数统计 | 1.1.0 | tool | editor_read, dialog | — | ✅ | 字数统计：选区/CJK/目标进度 |
| `whitespace_sandbox` | 空白符检查（沙箱） | 1.0.2 | tools | editor_read | ✅ | ✅ | 空白检查：可配置行宽 |
| `wordcount_sandbox` | 字数统计（沙箱） | 1.0.3 | tools | editor_read | ✅ | ✅ | 字数统计沙箱样例 |
