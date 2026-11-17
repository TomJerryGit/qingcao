# 青草编辑器 v2.4.0 发布说明

> 发布日期：2026-10-22 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.4.0`）
> 基于 v2.3.0，包含其全部内容。

---

## 一句话概括

v2.4.0 补齐 Notepad++ 最后的交互差异（**窗口级拖放**、**双击标签栏空白处
新建文档**），并新增**内置拼写检查插件**（对标 NPP DSpellCheck，
零依赖可运行、可选 `pyspellchecker` 提升词典质量）。

---

## 新增功能

### 窗口级拖放打开

- 文件拖到**窗口/欢迎页任意位置**即可打开（此前仅编辑器区域有效）；
- 拖入目录 → 作为项目打开；
- 状态栏提示"已打开 N 个拖入文件"。

### 标签栏 NPP 习惯

- **双击标签栏空白处新建文档**（NPP 同名行为）；
- 中键关闭标签（既有行为，本轮补测试覆盖）。

### 内置拼写检查插件（`plugins/spell_check/`）

- 对标 Notepad++ 的 DSpellCheck；
- 仅 `editor_read` 权限，不写文件、不联网；
- 词典来源：可选 `pyspellchecker`（已安装自动使用）→ 内置常用词表 +
  技术词允许列表（零依赖兜底）；
- 误报抑制：跳过全大写（API）、含数字、下划线、驼峰、URL、过短词；
- 结果发布到「问题」面板（`SPELL001` warning），状态栏给数量；
- 设置项：启用 / 最短检查长度 / 最多报告数量；
- 菜单：工具 → 拼写检查 → 检查当前文档 / 清除结果。

---

## 修复与改进

- 修复启动空窗口（欢迎页）拖入文件无反应的问题；
- 补齐标签栏交互测试，防止中键关闭回归。

---

## 测试

新增：
- `tests/test_drag_drop.py`（acceptDrops + 真实 QDropEvent 打开文件）；
- `tests/test_tab_bar_npp.py`（中键关闭 + 双击新建，真实 QMouseEvent）；
- `tests/test_spell_check_plugin.py`（manifest/注册/误报过滤/限额）。

全量 pytest 套件通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.3.0 → v2.4.0 无数据迁移；
2. 拼写检查默认启用（零依赖可用）；如需更高质量词典：
   `pip install pyspellchecker`；
3. 拖放/双击均为新增行为，不影响既有快捷键。

---

## 已知限制

- 内置词表为英文常用词兜底，专业词汇会误报——建议安装 pyspellchecker
  或在后续版本支持自定义词典/忽略词；
- 真实双显示器 / 跨屏 DPI 变化未物理验证；
- 24h+ 内存泄漏与 IME 组合输入未专项测试；
- Inno Setup 安装包未编译（本机无 ISCC）。

---

## 包校验

发布包由 GitHub Actions 在 `windows-latest` 构建：

* `QingCaoEditor-v2.4.0-windows.zip`
* `QingCaoEditor-v2.4.0-windows.zip.sha256.txt`

```powershell
Get-FileHash .\QingCaoEditor-v2.4.0-windows.zip -Algorithm SHA256
# 与 .sha256.txt 比对
```
