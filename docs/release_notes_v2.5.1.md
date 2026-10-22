# 青草编辑器 v2.5.1 发布说明

> 发布日期：2026-10-22 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.5.1`）
> 补丁版本：包含 v2.5.0 全部内容 + 以下修复。

---

## 一句话概括

v2.5.1 修复 v2.5.0 用户反馈的两个 UI 问题：**切换主题报错崩溃** 与
**浅色主题下面板仍为黑底**；同时补齐 Notepad++ 风格的**菜单选中对号**。

---

## 修复

### 1. 主题切换失败（UnboundLocalError）

- 现象：切换主题（尤其"跟随系统"）弹出
  `cannot access local variable 'QApplication' where it is not associated
  with a value`；
- 根因：`_apply_theme_by_name()` 函数后文有局部
  `from PyQt5.QtWidgets import QApplication`，Python 因此把
  `QApplication` 当作整个函数的局部变量；在 import 之前使用即抛
  `UnboundLocalError`；
- 修复：把导入移到函数最前面。

### 2. 浅色主题下面板仍是黑底

- 现象：浅色/护眼主题下，插件面板、全局搜索、性能诊断、目录树内容
  仍为深色（截图确认）；
- 根因：这些面板只在**内部子控件**上设置硬编码深色内联 QSS，
  dock 级 `refresh_theme` 覆盖不到；
- 修复：新增 `adapt_widget_styles(root, theme)` 递归适配控件树内联
  QSS；保存首次原始 QSS 并从原始值重适配（幂等，多次切换不叠加）；
  接入惰性面板首次打开与主题切换两条路径。

### 3. 菜单选中对号（对齐 Notepad++）

- 「编码」菜单勾选当前编码；切换到其他编码后，下次打开菜单 ✓ 移动到
  新编码（同一时刻只有一个勾）；
- 「换行符」子菜单勾选当前 EOL（LF/CRLF/CR）；
- 「语言」菜单勾选当前语言包 / 「自动（按扩展名）」；
- 通过 `aboutToShow` 从当前文档真实状态同步。

---

## 测试

新增：
- `tests/test_menu_checks.py`：主题导入顺序回归、编码/EOL 勾选当前项、
  勾选跟随状态切换（✓ 移动且唯一）、语言自动勾选；
- `tests/test_panel_theme_adapt.py`：子控件深色 QSS 被改写 + 幂等。

全量 pytest 套件通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.5.0 → v2.5.1 无数据迁移；
2. 仅 UI 修复，无接口/插件兼容性变化。

---

## 已知限制

- 编码勾选为编码代码精确（忽略大小写）匹配；若出现别名
  （如 gb2312 vs gbk）可能无勾选，后续可加别名归一化；
- 沙箱为静态审计（准入控制），运行时进程隔离留作后续阶段；
- 真实双显示器 / 跨屏 DPI 变化未物理验证；
- Inno Setup 安装包未编译（本机无 ISCC）。

---

## 包校验

发布包由 GitHub Actions 在 `windows-latest` 构建：

* `QingCaoEditor-v2.5.1-windows.zip`
* `QingCaoEditor-v2.5.1-windows.zip.sha256.txt`

```powershell
Get-FileHash .\QingCaoEditor-v2.5.1-windows.zip -Algorithm SHA256
# 与 .sha256.txt 比对
```
