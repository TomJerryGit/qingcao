# 快速开始

## 1. 安装

### 从源码运行（推荐开发者）

```bash
git clone https://github.com/qingcao-editor/qingcao.git
cd qingcao

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
python main.py
```

> **注意**：项目**尚未发布到 PyPI**，也没有注册 `qingcao` 命令行入口
> （仓库中没有 `pyproject.toml` 的 `[project.scripts]`）。请不要尝试
> `pip install qingcao-editor`。

### 依赖说明

`requirements.txt` 里分两类：

| 类型 | 包 | 缺失时的表现 |
|---|---|---|
| 必需 | `PyQt5`、`PyQt5-sip`、`QScintilla` | 无法启动 |
| 推荐 | `chardet`、`requests`、`psutil` | 自动降级（编码检测回退启发式、网络功能不可用、内存显示"未安装"） |
| 可选 | `keyring`、`reportlab`、`pypinyin` | 对应功能不可用（明文存 Token、PDF 导出、拼音搜索） |

## 2. 启动

```bash
python main.py                     # 启动编辑器
python main.py file.py             # 打开文件
python main.py a.py b.py c.py      # 打开多个文件
python main.py --project my.qingcao-project   # 打开项目
python main.py --no-splash         # 不显示启动画面
python main.py --version           # 查看版本
```

> `--new-window` 参数目前会被解析但**不生效**（多实例支持未实现）。

## 3. 开发环境

```bash
pip install -r requirements-dev.txt   # pytest / ruff 等
python -m pytest tests                # 281 项测试
python -m pytest -m realserver        # 真实语言服务器联调（需 pylsp）
python -m ruff check .                # 0 告警
python tools/check_version.py         # 版本一致性
```

## 4. 启用语言服务（LSP）

编辑器自带 LSP 客户端，但**不附带语言服务器**，需自行安装：

```bash
pip install python-lsp-server         # Python
npm i -g typescript-language-server   # JavaScript / TypeScript
# rust-analyzer / gopls / clangd / jdtls 按需安装
```

注意：目前只有 `.py` / `.pyw` 文件会自动启用 LSP，其他语言需在代码中
调用 `proxy.toggle_lsp(True)`（`core/editor.py` 中有扩展名判断）。

## 5. 启用音效

音效**默认关闭**（避免突然出声）。开启方式：

工具 → 首选项 → 搜索"音效" → 打开 `sound_effects`。

`resources/sounds/` 下已有 26 个生成的 `.wav`；直接替换同名文件即可
自定义音效。

## 6. 插件

内置插件放在 `plugins/` 下，启动时自动加载。首次启动会弹出**权限确认
对话框**（危险权限需手动允许，可勾选"记住"）。

自己写插件见 [插件开发](plugin_dev.md)。

## 下一步

- [功能说明](features.md) — 了解各模块与已知限制
- [快捷键](shortcuts.md) — 提高操作效率
- [常见问题](faq.md) — 遇到问题先看这里
