# 多屏 / 高 DPI 手动验证清单（v2.16）

> 目标：覆盖跨屏拖动、不同缩放、混合 DPI 场景；部分项只能真机验证。

## A. 单机可模拟（已验证/可复现）

| 项 | 操作 | 期望 |
|---|---|---|
| 全局缩放 125% | `set QT_SCALE_FACTOR=1.25` 启动 | 布局不重叠、字体清晰 |
| 全局缩放 150% | `set QT_SCALE_FACTOR=1.5` | 同上 |
| 屏幕缩放因子 | `set QT_SCREEN_SCALE_FACTORS=1;1.25` | 窗口按对应屏幕缩放 |
| 高对比度 | `python tools/simulate_high_contrast.py --on --yes` | 面板跟随系统配色，结束后 `--off` 恢复 |

## B. 真机双屏清单（需两块物理显示器，不同 DPI）

1. 主屏 100% + 副屏 150%，把窗口从主屏拖到副屏：
   - 菜单栏、工具栏、状态栏不裁切；
   - 编辑器字体/行号按新 DPI 重排；
   - 插件面板（含问题面板/插件市场）表头、搜索框不模糊。
2. 在副屏打开对话框（设置/插件市场/AI 配置）：
   - 对话框尺寸合理、按钮可见；
   - 关闭后主窗口位置不被重置。
3. 混合 DPI 下多实例：
   - 第二实例在主屏创建，第一实例在副屏；`--new-window` 焦点切换正确。
4. 截图存档到 `docs/validation_multimonitor_<dpi>.png`。

## C. 校验脚本

```powershell
python tools/verify_display_env.py
python tools/smoke_plugin_theme.py
python tools/simulate_high_contrast.py --status
```

## D. 已知限制

- 当前开发机为单显示器（1536x864 @100%），B 部分只能由用户真机执行；
- 高 DPI 下的第三方插件面板样式仅验证了内置插件。
