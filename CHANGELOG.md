# Changelog

所有重要的项目变更都记录在此文件中。

本项目遵循 [语义化版本](https://semver.org/)。

## [Unreleased]

### 计划中
- 更多 LSP 语言支持
- 协作编辑完善
- 插件市场后端

## [2.1.0] - 2026-09-24

本次更新聚焦于**跨模块代码审查修复**、**Vim 模式补全**、
**主题切换修复**、**搜索偏移修正**。

### 新增
- **Vim 模式完整实现**
  - 操作符 + 动作: `dw` / `de` / `db` / `d$` / `d0` / `dG` / `dgg`
  - 修改操作符: `cw` / `ce` / `cb` / `c$` / `cc`
  - 复制操作符: `yw` / `ye` / `yb` / `yy`
  - 文本对象: `iw` / `aw` / `i"` / `a"` / `i(` / `a(` / `i[` / `a[` / `i{` / `a{`
  - 具名寄存器: `"a` 前缀（a-z / 0-9 / " / + / * / - / _）
  - 查找重复: `n` / `N`
  - 入口: 工具菜单 → Vim 模式（`Ctrl+Shift+V`）
- **UI 测试套件** (tests/test_vim_mode.py, 11 个测试)
- 测试总数: 187 → 198

### 修复
- **主题切换核心 bug**: `themes/*.json` 无 `qss` 字段，
  `_apply_theme_by_name` 只做 `if theme.qss: setStyleSheet(...)`，
  导致全局 QSS 从未应用。改用 `loader.apply_qss()` 自动生成。
- **主题跟随不全**: 扩展 `adapt_qss_colors` 替换表，
  补充终端色 (`#0d0d0d`)、次要文字、聚焦色 (`#007acc`) 等
- **主题菜单显示**: 从文件名 (`light_clean`) 改为 `display_name` (`晨曦`)
- **字符/字节偏移**: `SearchMatch` 双写 `start/end`（字节）
  和 `char_start/char_end`（字符），修复含中文文件搜索高亮/替换错位
- **`EditorProxy.highlight_all`**: 调用不存在的 `search_all()` →
  改用 `search()`
- **`EditorProxy.search_next`**: 调用签名错误 →
  Python 层遍历 `result.matches`
- **`_search_next` 不前进**: 从 `pos` 开始 → 从 `pos+1` 开始
- **`"a` 寄存器覆盖**: 两次 alnum 输入互相覆盖 →
  加独立 `_waiting_for_register` 状态
- **`yy` 后 `p` 不粘贴**: paste 从旧 `self.register` 读 →
  改从 `registers['"']` 读
- **`SCI_WORDRIGHTPOSITION` 不存在**: `PyQt5` 未导出该常量 →
  改用 `SCI_WORDRIGHT`
- **Ctrl+Z/Ctrl+Y 被吞**: QScintilla 内置绑定占用 →
  `SCI_CLEARCMDKEY` 清除，让主窗口菜单收到
- **`Ctrl+Alt+V` 被 AltGr 解释**: Windows 上无效 →
  改 `Ctrl+Shift+V`
- **`ProjectFileEvent` 子类分派**: `Removed`/`Renamed` 被误当
  `Added` → 先检查子类
- **事件类双重定义**: `app/event_bus.py` 与 `core/events.py`
  各有 44 个同名类 → 统一从 `core.events` 重导出
- **`PluginAPI` 死信号**: `plugin_loaded` / `plugin_unloaded`
  从未 emit → 删除
- **快捷键冲突 5 处**:
  - AI 助手: `Ctrl+Shift+E` → `Ctrl+Alt+E`
  - AI 助手: `Ctrl+Shift+R` → `Ctrl+Alt+Shift+R`
  - Markdown 预览: `Ctrl+Shift+M` → `Ctrl+Alt+M`
  - Python 调试器: `F5` → `F6`
  - TODO 面板: `Ctrl+Shift+T` → `Ctrl+Alt+T`
- **每日技巧日期边界**: 手动点击也更新 `last_tip_date` →
  仅自动触发时更新
- **`outline_panel` 硬编码 50000 行**: 改用
  `large_file_threshold` 偏好推导
- **`DirectoryTree` Git 缓存 5 秒过短**: 改为 30 秒 + 可配置
- **`PythonHighlighter` 性能**: 80 条关键字正则合并为 2 条
- **`command_palette` 使用历史 key 冲突**: `title` 改为
  `action_name`
- **`sandbox_policy.DANGEROUS_MODULES` 冗余**: 移除由权限门控的
  `socket` / `shutil` / `subprocess` 等
- **LSP 位置转换**: 用 `SCI_FINDCOLUMN` → 改用字节偏移
- **pytest-qt 绑定**: PySide6 → PyQt5（避免混用崩溃）

### 变更
- **`adapt_qss_colors` 扩表**:
  - `#0d0d0d` → `background`（终端/控制台）
  - `#2a2d2e` / `#333333` / `#4c4c4c` → 面板变体
  - `#858585` / `#808080` / `#c0c0c0` → 次要文字
  - `#007acc` → `input_focus`（聚焦色）
  - `#404040` → `indent_guide`
  - `#5a5a5a` / `#8f1e1e` → 危险按钮
- `tests/conftest.py`: 设置 `PYTEST_QT_API=pyqt5`
- `EditorWidget.keyPressEvent`: 优先让 VimMode 处理

### 删除
- `PluginAPI.plugin_loaded` / `plugin_unloaded`（死信号）
- `sandbox_policy.DANGEROUS_MODULES` 中由权限门控的冗余模块
- 归档 `fix_*.py` 到 `_archive/fixes/`

### 测试
- 198 passed（187 → 198，新增 11 个 Vim 测试）

## [2.0.0] - 2026-09-19

### 新增
- 全新的 PyQt5 架构
- 完整的 LSP 客户端
- 插件系统与沙箱
- 宏录制与回放
- 多光标与列模式
- 命令面板与文件切换
- AI 助手集成
- 代码片段系统
- 主题编辑器
- 性能监控面板
- 会话快照
- 集成终端
- Git 集成
- 自动更新

### 修复
- 编辑器渲染性能
- 大文件加载
- 快捷键冲突检测

### 变更
- 从 PySide6 迁移到 PyQt5
