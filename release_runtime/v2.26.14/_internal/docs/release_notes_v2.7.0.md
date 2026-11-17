# 青草编辑器 v2.7.0 发布说明

> 发布日期：2026-10-26 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.7.0`）
> 功能版本：包含 v2.6.2 全部内容。

---

## 一句话概括

v2.7.0 完成三项用户可感知改进：**主题覆盖独立对话框**、
**拼写检查一键忽略本文件可疑词**、**`--new-window` 多实例**
（独立会话与配置）。

---

## 新增 / 改进

### 主题覆盖独立顶层对话框（C-2）

- 应用级事件过滤器：**新创建**的独立对话框显示时自动套用当前主题；
- 主题切换时同步**已存在**的所有顶层窗口（QMenu/QToolTip 除外），
  并递归适配子控件内联 QSS。

### 拼写检查增强

- 新增「**忽略本文件可疑词**」：一次性把当前文档所有可疑词写入
  `data/spell_ignore.txt`（去重、保留已有词），随后清空诊断；
- 入口：工具 → 拼写检查 → 忽略本文件可疑词，以及**编辑器右键菜单**同名项；
- spell_check 保持进程内运行（沙箱试点由 `plugins/sandbox_demo` 验证，
  插件仍保留 `diagnostics()` 协议入口）。

### 多实例（`--new-window`）

- `--new-window` 启动独立实例：**独立会话文件**
  `session_w<pid>.json` + **独立设置目录**
  （便携模式 `data/instances/<pid>`，非便携在 AppData 下），
  多窗口互不覆盖布局与偏好；
- 帮助文本与 README 同步更新。

---

## 测试

新增/更新：
- `tests/test_theme_toplevel.py`（3 项：已有对话框、新对话框过滤器、菜单不误改）；
- `tests/test_spell_ignore_enhance.py`（2 项）；
- `tests/test_multi_instance.py`（3 项）。

全量 pytest 通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.6.2 → v2.7.0 无数据迁移；
2. `--new-window` 仅影响新启动的实例，默认启动行为不变；
3. 拼写忽略词仍为 `data/spell_ignore.txt`。

---

## 已知限制

- 多实例之间不广播文件变更通知（同一文件双开需自行避免）；
- 沙箱仍只支持只读扩展点；
- 真实双显示器 / 跨屏 DPI 变化未物理验证。

---

## 包校验

发布包由自托管 Runner 构建：

* `QingCaoEditor-v2.7.0-windows.zip`
* `QingCaoEditor-v2.7.0-windows.zip.sha256.txt`
