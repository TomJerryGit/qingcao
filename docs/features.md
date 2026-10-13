# 功能说明

本文档描述**实际实现**的能力，并明确标注已知限制。凡是"已实测"的数据
都来自本仓库的验证记录（见 `docs/REVIEW_GUIDE.md`）。

---

## 编辑

| 功能 | 说明 |
|---|---|
| 多光标 | `Ctrl+点击` 添加光标；`Ctrl+D` 选中下一个相同项 |
| 列模式 | `Alt+C` 进入矩形选择（`SC_SEL_RECTANGLE`） |
| 自动配对 | 括号/引号自动闭合，可在首选项关闭（`auto_close_brackets`） |
| 代码片段 | 支持 `${1:占位符}` 语法，内置 `if` / `for` / `def` / `class` 等 |
| 代码折叠 | `setFolding`，支持 Boxed / Cirrus / Plain |
| 缩进彩虹线 | 可选（`indent_rainbow`） |
| Vim 模式 | `Ctrl+Shift+V`；支持 `dw`/`cw`/`yw`、文本对象 `iw`/`a"`/`i(`、具名寄存器 `"a`、`n`/`N` |
| 撤销/重做 | 自研 `UndoManager`（非 QScintilla 内置栈），支持命令合并 |

## 搜索

| 功能 | 说明 |
|---|---|
| 查找栏 | `Ctrl+F` |
| 全局搜索 | `Ctrl+Shift+F`，支持正则、文件类型过滤、批量替换预览 |
| 大文件搜索 | 复用行索引，1 MB 约 0.4 s、10 MB 约 3.7 s |

> **性能提示**：搜索采用全量解码 + 一次性行索引，内存占用与文件大小
> 同阶。超大文件（>100 MB）建议配合只读模式使用。

## 语言服务（LSP）

- 支持注册 Python / JavaScript / Rust / Go / C++ / Java 六种语言的服务器
- 能力：补全、跳转定义、查找引用、重命名、Code Action、诊断、格式化
- 诊断显示在问题面板与编辑器波浪线

**限制**：

- 不附带语言服务器，需自行安装（见[快速启动](quickstart.md#4-启用语言服务lsp)）
- 自动启用仅针对 `.py` / `.pyw`
- 已用真实 `python-lsp-server` 1.15.0 验证握手、`didChange` 同步与补全；
  但**未验证**其他五种语言服务器的语义兼容性

## 插件

| 功能 | 说明 |
|---|---|
| 动态加载 | 启动扫描 `plugins/`，也可在插件管理里手动重载 |
| 权限声明 | `plugin.json` 的 `permissions` 字段；启动激活前弹确认框 |
| API 边界门控 | 文件读写、网络、进程、剪贴板、对话框等均需对应权限 |
| 热重载 | 监控插件源码变更后自动 unload→load→activate；可用 `"hot_reload": false` 单独退出 |
| 依赖管理 | 支持 Python 包依赖与插件间依赖 |

### 已知限制

1. **没有进程级隔离。** 插件与编辑器同进程运行，`permissions` 只在
   `PluginAPI` 方法边界做门控。插件仍可通过 `import subprocess`
   等方式获得完整系统能力。
   仓库中曾有一套沙箱原型，经实测**无法启动**（`start()` 返回 `False`），
   且无任何生产调用方 —— 为避免误导，**已从代码库移除**。
   要真正隔离需要重构 `PluginAPI`（当前大量操作 QWidget，子进程不可用）。
2. **插件市场后端未部署。** 界面、缓存、回退列表齐全，但主注册表
   URL 不可达、回退条目 `download_url` 为空，因此**在线安装不可用**。

## 国际化

- 简体中文 / English / 日本語 / 한국어
- 翻译文件：`locale/<lang>/LC_MESSAGES/qingcao.po` 与编译后的 `.mo`
- 重新生成：`python tools/build_translations.py`

## 主题

内置 4 套：暗夜 / 晨曦 / 护眼 / 高对比度（`themes/*.json`）。
可在主题编辑器中调整，或直接编辑 JSON。

## 集成

| 功能 | 说明 |
|---|---|
| Git | 状态、差异、提交、推送、拉取（`core/git_client.py`） |
| 终端 | 内置终端面板；Windows 用 PowerShell / CMD / WSL |
| 导出 | HTML / Markdown / PDF（PDF 需 `reportlab`） |
| 配置同步 | GitHub Gist / WebDAV / 本地目录 |
| 文件关联 | 注册系统文件关联 |

## AI 助手

内置插件，支持 7 家 provider：OpenAI / DeepSeek / Ollama（本地）/
通义千问 / Moonshot / 智谱 GLM / Anthropic Claude。

操作包括：解释、重构、修复、加注释、生成 Docstring、生成测试、
性能优化、Code Review、摘要、语言转换。

需自备 API Key（Ollama 可留空）。配置入口：工具 → AI 助手 → ⚙ 配置 AI。

### Ollama 本地模型管理

工具 → AI 助手 → **🦙 Ollama 管理面板**（独立停靠窗口），支持：

| 功能 | 说明 |
|---|---|
| 服务状态 | 运行中 / 未启动 + 版本号，60 秒自动刷新 |
| 模型列表 | 名称、大小、参数量、量化级别、修改时间；内存中已加载的标 ● |
| 拉取模型 | 输入模型名（如 \qwen2.5:7b\）直接拉取，带实时进度条 |
| 删除模型 | 释放磁盘空间（二次确认） |
| 一键应用到 AI 配置 | 把 provider/model/端点写入设置 |

选中 Ollama 时，**AI 配置对话框的模型下拉框会自动从本机
\/api/tags\ 读取真实已安装模型**，不再是硬编码列表。

实现见 \core/ollama_client.py\（纯标准库，无新增依赖）。

## 工具

| 功能 | 说明 |
|---|---|
| 命令面板 | `Ctrl+Shift+P`，支持拼音首字母搜索（需 `pypinyin`） |
| 文件切换 | `Ctrl+P` |
| 符号跳转 | `Ctrl+Alt+R` |
| 宏录制/回放 | `Ctrl+Shift+R` / `Ctrl+Shift+M` |
| Python 控制台 | 内置 REPL，可直接访问编辑器 API |
| 性能监控 | CPU / 内存 / 线程数 |
| 代码度量 | 圈复杂度、可维护性指数、代码行统计 |
| 代码坏味检测 | 长函数、深嵌套、重复代码等 |
| 快照管理 | 工作区状态快照与恢复 |
| 差异对比 / 文件合并 | 并排对比与三方合并 |
| 会话恢复 | 崩溃或退出后恢复上次打开的文件 |
| 音效 | 可选，**默认关闭**，需在首选项开启 |

## 性能实测

| 指标 | 数值 |
|---|---|
| `MainWindow()` 冷启动 | 约 1.36 s（惰性构造面板后） |
| 面板构造 | 启动时 0 个，按需构造 |
| mmap 打开 10 MB | 约 0.011 s |
| 搜索 1 MB / 19 065 匹配 | 约 0.4 s |
| 搜索 10 MB / 190 650 匹配 | 约 3.7 s |
| 打包体积 | 约 137 MB（目录模式，其中 Qt DLL 约 80 MB） |
