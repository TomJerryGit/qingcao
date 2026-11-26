# 主题视觉回归基线

## 用途

固定 4 套主题的窗口与插件面板截图，用于发现配色/布局回归。

## 生成基线

```powershell
python tools/theme_e2e_screenshots.py --out docs/theme_baseline
```

## 对比检查

```powershell
python tools/theme_e2e_screenshots.py --check --json data/theme_baseline_check.json
```

- 当前阈值：窗口平均像素差 ≤80，面板 ≤60；
- 通过输出：`[theme-e2e] 基线对比通过`；
- 失败会列出具体文件与差异值。

## 环境要求

- Windows 10/11，当前屏幕 800×600 逻辑尺寸；
- 需真实窗口渲染（不要设置 `QT_QPA_PLATFORM=offscreen`）；
- 建议在发布前、主题/菜单/QSS 改动后运行。

## 说明

- 基线包含窗口大小与字体渲染，换机器/缩放比例后需重新生成；
- 面板内容可能与插件加载时序有关，以配色为主；
- 该检查目前作为本地发布门禁，不放入 CI（CI 无稳定 GUI 渲染）。
