# 无障碍验证清单（v2.17）

> 目标：键盘全路径可达、焦点可见、字体可缩放、可访问名称完备。

## A. 键盘导航

| 项 | 操作 | 期望 |
|---|---|---|
| 菜单全路径 | `Alt` 进入菜单 → 方向键 | 各级菜单可达、可触发 |
| 面板切换 | `Tab` / 快捷键 | 焦点进入面板，不丢失 |
| 对话框 | `Tab`/`Shift+Tab` 循环 | 按钮顺序合理，`Esc` 关闭 |
| 编辑器 | `F6`/`Ctrl+Tab` | 焦点在编辑器/面板间正确切换 |

自动审计：

```powershell
python tools/audit_keyboard_a11y.py --strict --json data/a11y_report.json
```

## B. 焦点可见性

- 键盘聚焦按钮/输入框/下拉框时有 2px `palette(highlight)` 边框；
- 深色/浅色/护眼/高对比度四主题下焦点环均可见（v2.17 已加入主题 QSS）。

## C. 字体缩放

- 设置 → ⚙ 首选项 → 常规 → 无障碍 → 界面字体缩放（0.8~2.0）；
- 修改后重启应用生效；编辑器字号请在外观页单独设置；
- 缩放到 1.5 时检查面板标题/按钮不被裁切。

## D. 屏幕阅读器（真机，需 NVDA/讲述人）

1. 启动 NVDA（中文语音）；
2. 依次 Tab 主工具栏、标签栏、状态栏，应读出控件名称；
3. 打开插件市场/设置，读出「安全状态/依赖状态」等文本；
4. 记录未读出名称的控件，补 `setAccessibleName`。

## E. 自动检查

```powershell
python tools/audit_keyboard_a11y.py --strict
python tools/smoke_plugin_theme.py
python tools/theme_e2e_screenshots.py --check
```
