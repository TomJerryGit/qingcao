# 插件目录

- 插件总数：15
- 沙箱插件：4
- 默认禁用：2

| 插件 | 名称 | 版本 | 分类 | 权限 | 沙箱 | 启用 | 说明 |
|---|---|---|---|---|---|---|---|
| `ai_assistant` | AI 助手 | 2.0.0 | editor | network, editor_read, editor_write, dialog | — | ✅ | AI 助手：隔离 headless/流式、多会话、加密持久化、diff/插入 |
| `markdown_preview` | Markdown 预览 | 1.1.0 | editor | editor_read, dialog | — | ✅ | Markdown 预览：远程面板/诊断 |
| `git_deep` | Git 深度集成 | 1.1.0 | integration | editor_read, process, filesystem, dialog | — | ✅ | Git 深度集成：状态栏/分支/diff/hunk、隔离宿主 Git API |
| `python_debugger` | Python 调试器 | 2.1.0 | integration | process, editor_read, editor_write, dialog, debugger | — | ✅ | Python 调试器：断点/单步/变量/栈、条件断点/监视、宿主服务 |
| `demo` | Demo | 1.0.0 | other | editor_read, dialog | — | ✅ | 青草编辑器最小示例插件 |
| `my_plugin` | My Plugin | 1.0.0 | other | - | — | — | 脚手架示例（默认禁用） |
| `json_formatter` | JSON 格式化 | 1.1.0 | tool | editor_read, editor_write, dialog | — | ✅ | JSON 格式化：JSONC/JSON Schema/选区 |
| `line_sort` | 行排序 | 1.1.0 | tool | editor_read, editor_write, dialog | — | ✅ | 行排序：升序/降序/去重（选区或整文件） |
| `logtail` | 日志实时监视 | 1.1.0 | tool | filesystem, dialog | — | ✅ | 日志监视：过滤/暂停/多文件/轮转 |
| `sandbox_demo` | 沙箱示例（实验） | 1.0.0 | tool | editor_read | ✅ | — | 演示 manifest sandbox:true 的只读子进程插件（大纲符号） |
| `spell_check` | 拼写检查 | 1.1.0 | tool | editor_read, filesystem | ✅ | ✅ | 拼写检查：标准沙箱/忽略词/诊断 |
| `todo_panel` | TODO 面板 | 1.1.0 | tool | filesystem, editor_read, dialog | — | ✅ | TODO 面板：扫描/远程面板/跳转 |
| `wordcount` | 字数统计 | 1.1.0 | tool | editor_read, dialog | — | ✅ | 字数统计：选区/CJK/目标进度 |
| `whitespace_sandbox` | 空白符检查（沙箱） | 1.0.1 | tools | editor_read | ✅ | ✅ | 空白检查：行尾/Tab/超长行 |
| `wordcount_sandbox` | 字数统计（沙箱） | 1.0.2 | tools | editor_read | ✅ | ✅ | 字数统计沙箱样例 |
