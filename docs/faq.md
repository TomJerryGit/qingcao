# 常见问题

## 启动与运行

### Q: 插件不生效 / 插件面板为空？

1. 确认 `plugins/<名字>/` 下同时存在 `plugin.json` 与 `__init__.py`
2. `plugin.json` 的 `name` 必须是合法 Python 标识符（不能含 `-`、空格）
3. 打开 **工具 → 插件管理** 查看状态与错误信息
4. 查看 `logs/runtime.log` 中的详细堆栈
5. 首次加载会弹**权限确认对话框**；若你之前点了拒绝，插件会被记住为
   禁用状态，需在插件管理里重新启用

### Q: 修改插件代码后没生效？

编辑器默认开启热重载（监控插件目录与源码文件），变更后约 1 秒自动
unload → load → activate。

若无效，检查：

- 首选项里的 `plugin_hot_reload` 是否被关掉
- 该插件的 `plugin.json` 是否设了 `"hot_reload": false`
- 插件是否持有长连接/后台线程（这类插件建议手动重载）

### Q: AI 助手连接失败？

- **Ollama（本地）**：确认 `curl http://localhost:11434` 返回
  `Ollama is running`，且 `ollama list` 中有你填写的模型名
- **云端模型**：检查 API Key、网络；用配置对话框里的 🔌 测试连接
- 配置入口：**工具 → AI 助手 → ⚙ 配置 AI**

### Q: 打开大文件卡顿？

编辑器用 mmap 分块加载，打开本身很快（10 MB 约 11 ms）。但要注意：

- **搜索**是全文解码 + 行索引，内存占用与文件大小同阶；超大文件
  （>100 MB）建议开启只读模式
- 语法高亮、折叠、Minimap 在大文件上开销明显，可在首选项调大
  "大文件阈值"以关闭这些特性
- 编辑器内嵌 `Ctrl+=` 放大字体也会影响长文件滚动性能

### Q: 窗口关不掉 / 退出后进程残留？

已在 2.1.x 修复（`setQuitOnLastWindowClosed(True)` + `closeEvent` 显式
`quit()` 双保险）。若仍遇到，请附上 `logs/runtime.log` 末尾内容。

## 快捷键

### Q: 某个快捷键没反应？

1. 先看[快捷键](shortcuts.md)确认是否真的绑定了（例如 **`Ctrl+H`
   替换目前未绑定**）
2. 是否被系统/输入法截获（`Ctrl+Alt+*` 系列在 Windows 上易被 AltGr 占用）
3. 是否与其他绑定重名（重名会触发 Qt "Ambiguous shortcut overload"，
   第二个不生效；已知 `Ctrl+Alt+M` 被 `my_plugin` 与 `markdown_preview`
   同时声明）

### Q: 如何自定义快捷键？

**工具 → 快捷键编辑器**，或直接编辑 `keybindings.json`。

## 功能相关

### Q: 支持哪些语言？

- 语法高亮（内置词法器）：Python、C/C++、JavaScript、Markdown、日志
- 语言服务（LSP）：Python、JavaScript/TypeScript、Rust、Go、C++、Java
  —— 但**需自行安装对应的语言服务器**

目前自动启用 LSP 的只有 `.py` / `.pyw`。

### Q: 插件市场无法安装插件？

**已知限制**：插件市场的**后端尚未部署**。界面与缓存是完整的，但主
注册表 URL 不可达、内置回退条目的 `download_url` 为空，因此在线安装
不可用。

替代方式：手动把插件目录放到 `plugins/` 下。如果插件声明了
`dependencies`（PyPI 包），需自行 `pip install`。

### Q: "插件沙箱"是安全的吗？

**不是。** 编辑器目前**没有进程级隔离**：

- 插件与编辑器在同一进程、同一解释器中运行
- `plugin.json` 的 `permissions` 只在 `PluginAPI` 方法边界做门控
- 插件可以直接 `import subprocess` / `socket` / `open(...)` 绕过声明
- `infrastructure/plugin_sandbox.py` 与 `sandbox_runtime.py` 是
  **未接线的原型**，没有任何生产调用方

请**只安装可信来源的插件**。

### Q: PDF 导出失败？

PDF 导出依赖 `reportlab`：

```bash
pip install reportlab
```

缺失时导出功能会明确提示，不会静默失败。

### Q: 配置存在哪里？

默认使用系统原生格式：

- **Windows**：注册表 `HKCU\Software\QingCao\Editor`
- **Linux**：`~/.config/QingCao/Editor.conf`
- **macOS**：`~/Library/Preferences/com.QingCao.Editor.plist`

**便携模式**：在程序目录创建 `portable.txt`，配置改为写入程序目录下的
`data/Editor.ini`。

> 注意：README 曾把 ini 路径写成默认行为，那是便携模式下的路径。

### Q: 界面语言是英文/日文，怎么切回中文？

**工具 → 首选项 → 语言**，或删除配置后重启（会重新走首次启动向导）。
简体中文 / English / 日本語 / 한국어 四种均有编译好的 `.mo`。

### Q: 音效没声音？

音效**默认关闭**（避免突然出声）。开启：**工具 → 首选项** →
打开 `sound_effects`。

`resources/sounds/` 下已有 26 个生成的 WAV；直接替换同名文件即可自定义。
若 `QtMultimedia` 不可用，会自动回退到系统提示音。

## 开发

### Q: 测试怎么跑？为什么有 7 项被跳过？

```bash
python -m pytest tests            # 默认套件
python -m pytest -m realserver    # 需要真实语言服务器
```

默认套件用 `-m "not realserver"` 排除了 7 项真实 `python-lsp-server`
联调测试（每个用例会 spawn 一个 pylsp 进程，约 25 s）。

### Q: `git status` 显示大量"已修改"，但我没改过？

可能是 `.gitattributes` 的 `eol=lf` 归一化导致的 **stat 假象**。
用仓库自带工具确认内容是否真的一致：

```bash
python tools/verify_worktree.py
```

它用内容哈希比对（绕过 git 过滤器）。若输出"内容一致 N / 不同 0"，
则这些"已修改"不是真实差异。要消除状态噪声：

```bash
git add --renormalize .
git commit -m "chore: 统一行尾为 LF"
```

### Q: 如何反馈 bug？

**帮助 → 报告问题**，或提交 GitHub Issue。请附上：

- 操作系统与版本、青草版本、Python 版本
- 复现步骤、期望行为 / 实际行为
- `logs/runtime.log` 与 `crash.log` 的相关片段
