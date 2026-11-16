# 插件目录

- 插件总数：15
- 沙箱插件：4
- 默认禁用：2

| 插件 | 名称 | 版本 | 分类 | 权限 | 沙箱 | 启用 | 说明 |
|---|---|---|---|---|---|---|---|
| `ai_assistant` | AI 助手 | 1.0.0 | editor | network, editor_read, editor_write, dialog | — | ✅ | 在编辑器内使用 AI 进行代码解释、重构、生成测试 |
| `markdown_preview` | Markdown 预览 | 1.0.0 | editor | editor_read, dialog | — | ✅ | Markdown 实时预览（分屏） |
| `git_deep` | Git 深度集成 | 1.0.0 | integration | editor_read, process, filesystem, dialog | — | ✅ | Git 状态、差异、提交、推送、拉取 |
| `python_debugger` | Python 调试器 | 2.0.0 | integration | process, editor_read, editor_write, dialog | — | ✅ | 编辑器内 Python 调试器：断点、单步（跳过/进入/跳出）、继续、局部变量与调用栈、终止。基于  |
| `demo` | Demo | 1.0.0 | other | editor_read, dialog | — | ✅ | 青草编辑器最小示例插件 |
| `my_plugin` | My Plugin | 1.0.0 | other | - | — | — | 脚手架示例（默认禁用） |
| `json_formatter` | JSON 格式化 | 1.0.0 | tool | editor_read, editor_write, dialog | — | ✅ | 格式化、压缩、验证 JSON |
| `line_sort` | 行排序 | 1.0.0 | tool | editor_read, editor_write, dialog | — | ✅ | 行排序：升序/降序/去重（选区或整文件） |
| `logtail` | 日志实时监视 | 1.0.0 | tool | filesystem, dialog | — | ✅ | 监视日志文件的变化并自动滚动 |
| `sandbox_demo` | 沙箱示例（实验） | 1.0.0 | tool | editor_read | ✅ | — | 演示 manifest sandbox:true 的只读子进程插件（大纲符号） |
| `spell_check` | 拼写检查 | 1.0.0 | tool | editor_read, filesystem | ✅ | ✅ | 英文拼写检查（可选 pyspellchecker；缺失时用内置常用词表） |
| `todo_panel` | TODO 面板 | 1.0.0 | tool | filesystem, editor_read, dialog | — | ✅ | 收集并显示所有 TODO/FIXME 注释 |
| `wordcount` | 字数统计 | 1.0.0 | tool | editor_read, dialog | — | ✅ | 实时统计字符数、词数、行数 |
| `whitespace_sandbox` | 空白符检查（沙箱） | 1.0.0 | tools | editor_read | ✅ | ✅ | 沙箱子进程只读诊断：行尾空白、Tab 缩进、超长行 |
| `wordcount_sandbox` | 字数统计（沙箱） | 1.0.1 | tools | editor_read | ✅ | ✅ | 沙箱子进程字数统计试点：状态栏展示当前文档字数/字符数 |
