# 青草编辑器 (QingCao Editor)

> 青草枯荣，野火重生。

轻量 · 极速 · 可扩展的跨平台代码编辑器。基于 **PyQt5** + **QScintilla** 构建，内置 LSP、插件系统、AI 助手、宏录制等现代化功能。

[![Version](https://img.shields.io/badge/version-2.14.1-brightgreen.svg)](#)
[![Python](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11-blue.svg)](#)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](#)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## ✨ 特性

### 编辑体验
- 🚀 **轻量启动** — 面板惰性构造，实测 `MainWindow()` 约 1.4 s（原 2.46 s）
- 🎨 **语法高亮** — 内置 Python / C++ / JavaScript / Markdown / 日志等多种词法器
- 📐 **代码折叠** — 支持 Boxed / Cirrus / Plain 多种折叠样式
- 🌈 **缩进彩虹线** — 一眼看清嵌套层级
- 🔷 **多光标编辑** — `Ctrl+点击` 添加光标，`Ctrl+D` 选中下一个相同项
- ▦ **列模式** — `Alt+C` 进入，多行批量编辑
- 🎯 **智能补全** — 括号/引号自动配对，`Ctrl+Space` 触发补全
- ✏️ **代码片段** — 支持 `${1:占位符}` 语法

### 大文件与搜索
- 📦 **mmap 分块** — 支持 GB 级大文件流畅打开
- 🔍 **多线程搜索** — 全项目正则搜索，支持文件类型过滤
- 🔁 **批量替换** — 预览后再执行，安全可控
- 🧠 **Hyperscan 加速** — 如安装 hyperscan，超大文件搜索提速数十倍

### 智能语言服务
- 🧩 **LSP 集成** — Python / JavaScript / Rust / Go / C++ / Java
- 💡 **智能提示、跳转定义、查找引用、重命名、Code Action**
- 📊 **问题面板** — 集中展示错误与警告
- 🎯 **符号大纲** — 层级展示类、函数、变量

### 插件系统
- 🔌 **动态加载** — 启动时扫描 `plugins/` 目录自动加载
- 🛡 **权限声明与确认** — 插件在 `plugin.json` 声明权限；启动激活前会弹出
  **权限确认对话框**（危险权限需用户确认），并在 `PluginAPI` 方法边界做门控
- ⚠️ **无进程隔离** — 插件与编辑器**同进程**运行。`permissions` 是 API 级
  门控而非安全沙箱，请只安装可信来源的插件。
  仓库中曾有一套沙箱原型，实测**无法启动**且无生产调用方，已移除
- 📦 **插件市场** — 界面与缓存就绪；**在线注册表后端尚未部署**，
  当前只能使用内置回退列表
- 🔥 **热重载** — 监控插件源码变更后自动重载（可在首选项关闭；
  单个插件可用 `"hot_reload": false` 退出）
- 🧬 **依赖管理** — 支持 Python 依赖与插件间依赖

### AI 助手（内置插件）
- 🤖 **多模型支持** — OpenAI / DeepSeek / Ollama（本地）/ 通义千问 / Moonshot / 智谱 GLM / Claude
- 💬 **流式响应** — 逐字输出，所见即所得
- 🛠 **代码操作** — 解释、重构、修复、加注释、生成 Docstring、生成测试、性能优化、Code Review、摘要、语言转换
- 🔒 **本地优先** — 支持 Ollama 本地模型，敏感代码不上云

### 生产力
- ⌨️ **命令面板** — `Ctrl+Shift+P` 模糊搜索所有功能
- 📂 **文件切换** — `Ctrl+P` 快速跳转（VSCode 风格）
- 🔣 **符号跳转** — `Ctrl+Alt+R` 跳转到函数/类
- ⏺ **宏录制回放** — `Ctrl+Shift+R` 录制，`Ctrl+Shift+M` 回放
- 🎨 **多主题** — 暗夜 / 晨曦 / 护眼 / 高对比度
- 🐍 **Python 控制台** — `Ctrl+`` 内置 REPL，可直接访问编辑器 API
- 📁 **项目目录树** — 文件图标、Git 状态着色、右键菜单
- 🔖 **书签与折叠记忆** — 关闭后重开保留工作状态
- 💾 **会话恢复** — 崩溃/退出后自动恢复上次打开的文件

### 集成与扩展
- 🐙 **Git 集成** — 状态、差异、提交、推送、拉取
- 🖥 **集成终端** — Windows: PowerShell / CMD / WSL；POSIX: `$SHELL`
- 📤 **导出** — HTML / Markdown / PDF（PDF 需 `reportlab`）
- 🎵 **音效反馈** — 可选的操作音效（默认关闭，需在首选项中开启）
- ☁️ **配置同步** — 支持 GitHub Gist / WebDAV / 本地目录
- 🌍 **国际化** — 简体中文 / English / 日本語 / 한국어
  （`.mo` 位于 `locale/*/LC_MESSAGES/`，可用
  `python tools/build_translations.py` 重新生成）

---

## 📋 系统要求

| 项目 | 要求 |
|------|------|
| Python | 3.8 / 3.9 / 3.10 / 3.11（推荐 3.11） |
| 操作系统 | Windows 10+ / Ubuntu 20.04+ / macOS 10.14+ |
| 内存 | 至少 4 GB（推荐 8 GB） |
| 磁盘 | 至少 500 MB 可用空间 |

> ⚠️ **Python 3.13+** 可能缺少 PyQt5 wheel，建议使用 Python 3.8 ~ 3.11。

---

## 🚀 安装

### 方式一：下载发行版（推荐新手）

前往 [Releases](https://github.com/qingcao-editor/qingcao/releases) 下载对应平台的安装包：

- **Windows**：`QingCaoEditor_Setup_v2.14.1.exe`
- **macOS**：`QingCaoEditor_v2.14.1.dmg`
- **Linux**：`QingCaoEditor_v2.14.1_linux_x64.tar.gz` 或 `.deb`

### 方式二：从源码运行（推荐开发者）

```bash
# 1. 克隆仓库
git clone https://github.com/qingcao-editor/qingcao.git
cd qingcao

# 2. 创建虚拟环境（推荐）
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动编辑器
python main.py
```

### 方式三：从 pip 安装（实验性）

> ⚠️ 目前**尚未**发布到 PyPI，也没有注册 `qingcao` 命令行入口
> （仓库中不存在 `pyproject.toml` / `entry_points`）。
> 请使用方法一或方法二。
```bash
pip install qingcao-editor
qingcao
```

## 🏃 快速开始

### 基本操作

```bash

# 启动编辑器
python main.py

# 打开指定文件
python main.py /path/to/file.py

# 打开多个文件
python main.py a.py b.py c.py

# 打开项目
python main.py --project myproject.qingcao-project

# 不显示启动画面（调试用）
python main.py --no-splash

# 查看版本
python main.py --version
```

### 快捷键速查

分类	快捷键	功能
文件	Ctrl+N	新建文件
Ctrl+O	打开文件
Ctrl+S	保存文件
Ctrl+Shift+S	另存为
Ctrl+W	关闭标签
Ctrl+Shift+T	恢复最近关闭的标签
Ctrl+Q	退出
编辑	Ctrl+Z / Ctrl+Y	撤销 / 重做
Ctrl+X / C / V	剪切 / 复制 / 粘贴
Ctrl+D	选中下一个相同项
Ctrl+/	注释切换
Ctrl+Shift+D	复制整行
Ctrl+Shift+↑/↓	上移 / 下移行
查找	Ctrl+F	查找
Ctrl+H	替换
Ctrl+Shift+F	全局搜索
Ctrl+G	跳转到行
Ctrl+Alt+R	符号跳转
视图	F11	无干扰模式
Shift+F11	全屏
Alt+C	列模式
Ctrl+= / Ctrl+- / Ctrl+0	放大 / 缩小 / 重置字体
工具	Ctrl+Shift+P	命令面板
Ctrl+P	文件切换
Ctrl+Shift+R	录制宏
Ctrl+Shift+M	回放宏
`Ctrl+`` | Python 控制台 |	
AI 助手	Ctrl+Shift+A	AI 快捷菜单
Ctrl+Shift+E	解释选中代码
Ctrl+Shift+R	重构选中代码
完整快捷键列表：帮助 → 快捷键参考

🤖 配置 AI 助手（以 Ollama 为例）
青草编辑器内置 AI 助手插件，支持本地与云端模型。以 Ollama（本地模型，隐私优先）为例：

1. 安装 Ollama
从 ollama.com/download 下载安装，或：


# Linux
curl -fsSL https://ollama.com/install.sh | sh
2. 拉取模型

# 通用对话（推荐，约 2GB）
ollama pull llama3.2

# 代码专用
ollama pull deepseek-coder

# 中文友好
ollama pull qwen2.5

# 轻量（约 500MB）
ollama pull qwen2.5:0.5b
3. 验证

# 应显示已下载的模型
ollama list

# 应显示 "Ollama is running"
curl http://localhost:11434
4. 在编辑器中配置
工具 → AI 助手 → ⚙ 配置 AI...

字段	填写
提供商	Ollama (本地)
API Key	（留空）
模型	llama3.2（与 ollama list 中一致）
Base URL	（留空）
点 🔌 测试连接 → 显示 ✓ 连接成功 → 点 Save。

5. 使用
选中一段代码 → 按 Ctrl+Shift+E 让 AI 解释。

切换云端模型
在配置对话框切换"提供商"并填入对应 API Key：

提供商	说明	获取 Key
OpenAI	GPT-4o / GPT-4o-mini	platform.openai.com
DeepSeek	deepseek-chat / deepseek-coder	platform.deepseek.com
通义千问	qwen-plus / qwen-max	dashscope.aliyuncs.com
Moonshot	moonshot-v1-8k	platform.moonshot.cn
智谱 GLM	glm-4 / glm-4-flash	open.bigmodel.cn
Anthropic Claude	claude-3-5-sonnet	console.anthropic.com
## 🧩 插件开发

### 目录结构

```text
plugins/
└── my_plugin/
    ├── plugin.json      # 插件清单（必需）
    ├── __init__.py      # 插件入口（必需）
    └── README.md        # 插件说明（可选）
```

plugin.json 示例
```json
{
  "name": "my_plugin",
  "display_name": "我的插件",
  "version": "1.0.0",
  "description": "插件简介",
  "author": "your-name",
  "author_email": "your@email.com",
  "license": "MIT",
  "type": "plugin",
  "category": "tool",
  "tags": ["demo"],
  "permissions": ["editor_read", "editor_write"],
  "dependencies": [],
  "plugin_dependencies": [],
  "api_version": "2.0.0",
  "enabled": true,
  "auto_load": true,
  "load_order": 100
}
```

__init__.py 示例
```python
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "my_plugin"
    VERSION = "1.0.0"
    DESCRIPTION = "我的插件"
    AUTHOR = "your-name"

    def on_activate(self):
        """插件激活时调用"""
        self.api.log("插件已激活")

```

        # 注册菜单
        self.api.add_menu(
            "工具/我的插件/执行",
            self.run_action,
            shortcut="Ctrl+Alt+M"
        )

    def on_deactivate(self):
        """插件卸载时调用"""
        self.api.log("插件已卸载")

    def run_action(self):
        """示例动作"""
        text = self.api.get_current_text()
        self.api.show_message("当前文件信息", f"字符数: {len(text)}")
```

### 权限列表

| 权限 | 说明 |
| --- | --- |
| `filesystem` | 读写本地文件 |
| `network` | 访问网络 |
| `process` | 执行系统命令 |
| `clipboard` | 读写剪贴板 |
| `dialog` | 显示对话框 / 访问主窗口 |
| `editor_read` | 读取编辑器内容 |
| `editor_write` | 修改编辑器内容 |
| `terminal` | 使用集成终端 |
| `lsp` | 注册 LSP 服务 |
| `debugger` | 调试功能 |

> **重要（P0-3）**：编辑器目前**没有进程级沙箱**，插件与编辑器同进程
> 运行。上面的权限只在 `PluginAPI` 的方法边界上做门控（`app/plugins.py`），
> 插件仍可用 `import subprocess` 等方式获得全部系统能力。
> 仓库中曾有一套沙箱原型（`plugin_sandbox.py` / `sandbox_runtime.py`），
> 实测**无法启动**（`start()` 返回 `False`）且无任何生产调用方，
> 为避免误导已从代码库移除。
### 一键生成插件骨架

```bash
python tools/create_plugin.py my_plugin
```

## ⚙️ 配置文件位置

> 说明：默认使用系统原生格式存储（Windows 为注册表
> `HKCU\Software\QingCao\Editor`），并非下面的 ini 路径；
> 只有便携模式下才改为程序目录内的 ini 文件。

| 平台 | 路径（便携模式） |
| --- | --- |
| Windows | `data/Editor.ini`（程序目录） |
| Linux / macOS | `data/Editor.ini`（程序目录） |

### 便携模式

在程序目录创建 `portable.txt` 文件，所有配置将存储于程序目录：

```bash
# 程序目录下
touch portable.txt
```

## 命令行选项

```text
python main.py [选项] [文件...]

选项:
  --no-splash       不显示启动画面
  --new-window      在新窗口打开
  --project FILE    打开指定的项目文件
  --version, -v     显示版本信息
  --help, -h        显示帮助信息
```

## 🛠 开发

### 环境准备

```bash
git clone https://github.com/qingcao-editor/qingcao.git
cd qingcao

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装开发依赖
pip install -r requirements.txt
pip install pytest pytest-qt coverage ruff black isort pyinstaller
```

### 项目结构

```text
qingcao/

├── main.py                 # 启动入口
├── app/                    # 应用层（动作、事件总线、菜单、插件 API 等）
├── core/                   # 核心层（编辑器、文档、命令、搜索、LSP 等）
├── ui/                     # UI 层（主窗口、面板、对话框等）
├── infrastructure/         # 基础设施（插件加载、主题、图标、音效等）
├── plugins/                # 插件目录
├── themes/                 # 主题目录
├── resources/              # 资源文件（图标、音效、启动画面）
├── tests/                  # 测试
├── docs/                   # 文档
├── build.py                # PyInstaller 打包脚本
├── build_installer.py      # Inno Setup 打包脚本
└── requirements.txt        # 依赖清单
代码检查

# Ruff
ruff check .

# Black 格式检查
black --check --diff .

# isort 检查
isort --check-only --diff .
运行测试

# 全部测试
python tests/run_all.py

# 或使用 pytest
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=. --cov-report=html
打包

# 目录模式（推荐，启动快）
python build.py

# 单文件模式（方便分发）
python build.py --onefile

# 调试模式（保留控制台）
python build.py --debug

# Windows 安装包（需要 Inno Setup 6+）
python build_installer.py

# Linux 打包（.tar.gz + .deb）
python build_linux.py

# macOS 打包（.app + .dmg）
python build_macos.py
## 📸 截图

截图待补充。欢迎提交 PR 添加。

❓ 常见问题
Q: 打开大文件很卡？
青草使用 mmap 分块加载，但建议：

打开 >100MB 的文件启用只读模式

在 工具 → 首选项 中调大"大文件阈值"

Q: 插件不生效？
检查 plugins/ 目录下是否有 plugin.json 和 __init__.py

查看 工具 → 插件管理 中的错误提示

检查 logs/runtime.log 中的详细堆栈

Q: AI 助手连接失败？
Ollama：确保 curl http://localhost:11434 返回 "Ollama is running"

云端模型：检查 API Key 是否正确、网络是否通畅

查看 工具 → AI 助手 → ⚙ 配置 AI 中的测试连接结果

Q: 如何自定义快捷键？
工具 → 快捷键编辑，或直接编辑 keybindings.json。

Q: 如何反馈 bug？
帮助 → 报告问题，或提交 GitHub Issue。

崩溃时程序会自动保存 crash.log，请一并附上。

Q: 支持哪些语言？
编辑器原生支持 Python / C++ / JavaScript / Markdown / 日志等。
通过 LSP 可扩展：Python、TypeScript、Rust、Go、C++、Java 等。

## 🤝 贡献

欢迎提交 Issue 和 PR！

提交 PR 前
□ 已在本地运行 python tests/run_all.py
□ 已通过 ruff check .
□ 已通过 black --check .
□ 已添加对应的测试用例（如适用）
□ 提交信息清晰（推荐 Conventional Commits）
报告 Bug
请使用 Bug 报告模板，并附上：

操作系统与版本

青草版本

Python 版本

复现步骤

期望行为 / 实际行为

crash.log 内容（如有）

## 📄 许可证

本项目采用 MIT License 开源协议。

```text
Copyright (c) 2024-2025 TomJerry
```

## 📬 联系方式

- 开发者：TomJerry

邮箱：1265338136@qq.com

GitHub：https://github.com/qingcao-editor/qingcao

文档：https://qingcao-editor.github.io/docs

问题反馈：https://github.com/qingcao-editor/qingcao/issues

## 🌱 致谢

感谢以下开源项目：

- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) — GUI 框架
- [QScintilla](https://riverbankcomputing.com/software/qscintilla/) — 代码编辑控件
- [pytest](https://pytest.org/) — 测试框架
- [PyInstaller](https://pyinstaller.org/) — 打包工具

以及所有贡献者与用户。

<p align="center"> <b>青草枯荣，野火重生。</b><br> <sub>QingCao Editor — Lightweight · Fast · Extensible</sub> </p> ```
```

```