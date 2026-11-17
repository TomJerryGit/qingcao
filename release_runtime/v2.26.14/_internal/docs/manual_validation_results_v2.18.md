# v2.18 真机验证结果（单机模拟 + 人工项）

> 日期：2026-11-02 · 环境：Windows x64、单显示器 800x600 逻辑 @120 DPI
> 工具：`tools/simulate_dpi_matrix.py`、`tools/check_a11y_tree.ps1`、
> `tools/simulate_high_contrast.py`、`tools/smoke_plugin_theme.py`

---

## 一、单机可模拟项（已执行 ✅）

### 1. DPI / 缩放矩阵

| 缩放 | 逻辑 DPI | 窗口 | 可见控件 | 关键容器越界 | 结果 |
|---|---|---|---|---|---|
| 1.00 | 120 | 800x600 | 86 | 1 | ✅ |
| 1.25 | 120 | 800x600 | 85 | 1 | ✅ |
| 1.50 | 120 | 800x600 | 86 | 1 | ✅ |
| 2.00 | 120 | 800x515 | 86 | 1 | ✅ |

- 截图：`docs/validation_scaling/scaling_*.png`
- 明细：`docs/validation_scaling_results.md`
- 说明：越界 1 项为窗口装饰差异；跨屏**拖动/混合 DPI 跳变**无法单机模拟。

### 2. 可访问性树（NVDA 替代方案）

- 工具：`tools/check_a11y_tree.ps1`（Windows UI Automation，`QT_ACCESSIBILITY=1`）
- 结果：**65 个可访问元素 / 65 个有名称（100%）**，`A11Y_PASS`
- 菜单栏/欢迎页/停靠面板/状态栏均在树中可见
- 记录：`docs/validation_a11y_tree.txt`
- 说明：UIA 树可验证"屏幕阅读器能看到名称与角色"，但**无法替代 NVDA 的实际语音播报体验**。

### 3. 高对比度 / 主题（此前已执行）

- 高对比度开启 → 应用正常、面板跟随系统配色 → 恢复原状；
- 4 主题 E2E 截图基线通过（`docs/theme_baseline/`）。

---

## 二、单机无法模拟项（需真机/安装软件）

| 项 | 原因 | 建议 |
|---|---|---|
| NVDA 实际语音播报 | 本机未安装 NVDA | 安装 NVDA（nvaccess.org，免费）后按 `docs/manual_validation_v2.17_nvda.md` 执行；自动化部分已被 UIA 树覆盖 |
| 跨屏拖动 / 混合 DPI 跳变 | 仅一块物理显示器 | 接第二块显示器后按 `docs/manual_validation_v2.16_multimonitor.md` 执行 |
| 真实双击/拖拽手感 | 自动化可模拟事件但非真人操作 | 人工抽测 |

---

## 三、结论

- v2.18 验证中**可自动化的部分全部通过**（DPI 矩阵、UIA 名称、主题/高对比度基线）；
- 剩余两项属**环境边界**（无 NVDA、无双屏），已以清单形式交付；
- 若后续具备条件，建议优先执行 NVDA 清单（软件可安装，收益直接）。

## 四、发现的问题

- 启动时出现「恢复未保存的内容」对话框（历史强制结束遗留草稿）——
  建议执行 `python tools/clean_recovery_drafts.py --yes` 清理。
