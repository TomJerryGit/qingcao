# v2.13.0 真机/模拟验证报告

> 日期：2026-10-28 · 主机：Windows x64 单显示器 1536x864 @100%
> 工具：`tools/simulate_high_contrast.py` / `tools/verify_display_env.py`

---

## 1. 高对比度模式模拟验证（已执行）

| 步骤 | 结果 |
|---|---|
| 原始状态 | `high_contrast = false` |
| 通过 Win32 `SPI_SETHIGHCONTRAST` 开启 | `high_contrast = true` ✅ |
| 启动青草编辑器 | 正常启动，窗口标题 `青草编辑器 v2.12.1 - 青草编辑器` ✅ |
| 截图留证 | `docs/validation_high_contrast.png` |
| 恢复原设置 | `high_contrast = false`，**与原始一致** ✅ |

### 观察结论

1. 高对比度模式下应用**正常运行**，无崩溃、无白屏；
2. 应用使用**自身主题**（未跟随系统高对比度调色板）：
   - 欢迎页/编辑器浅色区域文字对比度可读；
   - 菜单栏/强调色仍为应用主题色（非系统 HC 配色）；
3. 启动时弹出「崩溃恢复」对话框（因此前强制结束进程遗留草稿），
   与高对比度无关。

### 待改进（v2.13.0 P0 建议）

- 启动检测系统高对比度：可选自动切换为内置高对比度主题（或最小化自定义 QSS）；
- 菜单栏/强调色在高对比度模式下改为系统色（`QPalette` 优先）。

---

## 2. 缩放模拟验证（此前已完成）

| 缩放 | 结果 |
|---|---|
| 125% | 修复主题事件过滤器崩溃后，合跑 3 次通过 |
| 150% | 全量相关测试通过 |
| 真实跨屏拖动 | ⛔ 单机无法模拟（需第二块物理屏） |

---

## 3. 单机可模拟 vs 不可模拟

| 项目 | 可模拟 | 说明 |
|---|---|---|
| 高对比度 | ✅ | Win32 API 开关，`--yes` 确认，自动恢复 |
| 全局缩放比例 | ✅ | `QT_SCALE_FACTOR` |
| 多屏缩放因子 | 🟡 部分 | `QT_SCREEN_SCALE_FACTORS`（单屏效果有限） |
| 多显示器拖动/跨屏 DPI 跳变 | ⛔ | 需两块物理显示器 |
| 窗口 DPI 切换 | ✅ | 通过缩放因子间接模拟 |

---

## 4. 复现命令

```powershell
python tools/verify_display_env.py            # 环境自检
python tools/simulate_high_contrast.py --status
python tools/simulate_high_contrast.py --on --yes    # 临时开启
# ... 手动检查应用 ...
python tools/simulate_high_contrast.py --off          # 恢复
```