# 快捷键

本文档由代码自动核对生成，与 `ui/main_window.py` 的注册保持一致。

## 文件

| 快捷键 | 功能 |
|---|---|
| `Ctrl+N` | 新建文件 |
| `Ctrl+O` | 打开文件 |
| `Ctrl+S` | 保存 |
| `Ctrl+Shift+S` | 另存为 |
| `Ctrl+Alt+S` | 全部保存 |
| `Ctrl+W` | 关闭标签 |
| `Ctrl+Shift+W` | 关闭所有标签 |
| `Ctrl+Shift+T` | 恢复关闭的标签 |
| `Ctrl+Q` | 退出 |

## 编辑

| 快捷键 | 功能 |
|---|---|
| `Ctrl+Z` / `Ctrl+Y` | 撤销 / 重做 |
| `Ctrl+X` / `Ctrl+C` / `Ctrl+V` | 剪切 / 复制 / 粘贴 |
| `Ctrl+A` | 全选 |
| `Ctrl+/` | 注释切换 |
| `Ctrl+D` | 选中下一个相同项（多光标） |
| `Ctrl+Shift+D` | 复制整行 |
| `Ctrl+Shift+↑` / `Ctrl+Shift+↓` | 上移 / 下移行 |
| `Ctrl+Shift+E` | 计算表达式 |
| `F5` | 插入日期时间 |
| `Ctrl+Space` | 触发自动补全 |
| `Ctrl+点击` | 添加多光标 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 下一个 / 上一个标签 |

## 查找与导航

| 快捷键 | 功能 |
|---|---|
| `Ctrl+F` | 查找 |
| `Ctrl+Shift+F` | 全局搜索 |
| `Ctrl+G` | 跳转到行 |
| `Ctrl+P` | 文件切换（VSCode 风格） |
| `Ctrl+Shift+P` | 命令面板 |
| `Ctrl+Alt+R` | 符号跳转 |

> ⚠️ **`Ctrl+H`（替换）目前未绑定任何快捷键。** 替换功能可用，但需通过
> 查找栏的替换按钮或全局搜索面板操作。这是已知缺口。

## 视图

| 快捷键 | 功能 |
|---|---|
| `F11` | 无干扰模式 |
| `Shift+F11` | 全屏 |
| `Alt+C` | 列模式 |
| `Ctrl+=` / `Ctrl+-` / `Ctrl+0` | 放大 / 缩小 / 重置字体 |

## 工具

| 快捷键 | 功能 |
|---|---|
| `Ctrl+`` | Python 控制台 |
| `Ctrl+Shift+R` | 录制 / 停止宏 |
| `Ctrl+Shift+M` | 回放宏 |
| `Ctrl+,` | 首选项 |
| `Ctrl+Shift+V` | Vim 模式（增强） |

> 说明：Vim 模式最初尝试用 `Ctrl+Alt+V`，但 Windows 上会被解释为
> AltGr+V，因此改为 `Ctrl+Shift+V`。

## 插件

| 快捷键 | 插件 |
|---|---|
| `Ctrl+Alt+G` | Git 深度集成 |
| `Ctrl+Alt+J` | JSON 格式化 |
| `Ctrl+Alt+L` | 日志实时监视 |
| `Ctrl+Alt+M` | Markdown 预览 |
| `Ctrl+Alt+T` | TODO 面板 |
| `Ctrl+Alt+W` | 字数统计 |
| `F6` / `F7` | Python 调试器（启动 / 步进） |
| `Ctrl+Alt+Shift+M` | 示例插件 `my_plugin` |

> ⚠️ **已知冲突：`Ctrl+Alt+M` 同时被 `my_plugin` 与 `markdown_preview`
> 声明。** `my_plugin` 是脚手架示例插件，建议在正式使用前禁用或改键
> （插件管理 → 禁用，或编辑 `plugins/my_plugin/plugin.json`）。

### AI 助手

| 快捷键 | 功能 |
|---|---|
| `Ctrl+Shift+A` | AI 快捷菜单 |
| `Ctrl+Alt+E` | 解释选中代码 |
| `Ctrl+Alt+Shift+R` | 重构选中代码 |
| `Ctrl+Alt+Space` | 请求 AI 行内补全（需先在菜单里开启） |
| `Ctrl+Alt+Return` | 接受 AI 行内补全 |

> 注意：README 正文中曾写"按 `Ctrl+Shift+E` 让 AI 解释"，那是错的 ——
> `Ctrl+Shift+E` 已被"计算表达式"占用，AI 解释是 `Ctrl+Alt+E`。
> 本文档以代码为准。

## 自定义快捷键

工具 → 快捷键编辑器，或直接编辑 `keybindings.json`。

## 排查快捷键无效

1. **被系统/输入法占用** —— 例如 `Ctrl+Alt+*` 系列在部分 Windows 环境
   会被 AltGr 或输入法截获。
2. **与 QScintilla 内置绑定冲突** —— 编辑器已用 `SCI_CLEARCMDKEY`
   清理了 `Ctrl+Z`/`Ctrl+Y` 等冲突项；若自定义键无效，可在
   `ui/editor_view.py` 的 `_init_...` 中追加清理。
3. **重名快捷键** —— 同名会触发 Qt 的 "Ambiguous shortcut overload"
   告警，第二个绑定不生效（见上文 `Ctrl+Alt+M`）。
