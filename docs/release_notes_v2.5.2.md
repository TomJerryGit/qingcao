# 青草编辑器 v2.5.2 发布说明

> 发布日期：2026-10-23 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.5.2`）
> 补丁版本：包含 v2.5.1 全部内容 + 性能与启动修复。

---

## 一句话概括

v2.5.2 把输入延迟从 **211 µs/键降到 57 µs/键**（约 3.7 倍），并修复启动
主题通知的隐藏错误、优化主题切换遍历；纯性能/稳定性补丁，无接口变化。

---

## 性能

### 输入延迟 211 → 57 µs/键

cProfile（2000 次 insertAt）定位到每键的 provider 同步与撤销栈开销：

1. **provider 同步缓存**：`_sync_provider_now()` 用内存缓存
   `_last_synced_text` 比较，去掉每次按键的 `provider.read_text()` 整篇
   解码；
2. **单块快速写入**：小文件（单块）直接写 block 0，省去逐块循环；
3. **撤销栈惰性物化**：`InsertCmd` 改为分片存储并原地追加；连续单字符
   输入走 `try_append_typing()` 快路径，跳过 CommandPool 与命令对象
   分配（多光标/列模式仍走原逻辑）。

实测（同一台机器，三次采样）：**211 → 149 → 57.2 µs/键**
（56.2 / 57.2 / 72.8，2000 次总计 0.114 s）。
`typing_2000` 基准阈值从 0.9 s 收紧到 **0.20 s**，锁定收益。

### 主题切换遍历优化

- `adapt_widget_styles()` 去掉重复的 `findChildren` 遍历（原先扫两遍）；
- 增加主题/控件级缓存：同一主题重复套用直接短路
  （首次 34.6 ms → 同主题 0.026 ms）；切换主题仍从原始 QSS 重新适配，
  不会叠加失真。

---

## 修复

### 启动主题通知参数错误

`apply_startup_theme()` 调用了 `ThemeLoader.notify_widgets(
visible_only=...)`，但该方法不接受该参数 → 启动主题通知**静默失败**
（被 except 吞掉）。已修正调用，启动主题现在完整生效。

---

## 测试

- 撤销语义 38 项定向测试通过（惰性物化后撤销/重做行为不变）；
- 主题适配测试更新：同主题二次调用返回 0、换主题重新适配；
- 全量 pytest 套件通过；ruff 0；`tools/check_version` 通过。

---

## 升级注意事项

1. v2.5.1 → v2.5.2 无数据迁移；
2. 无接口/插件兼容性变化；
3. 输入与主题行为均向后兼容。

---

## 已知限制

- 主题切换仍受 Qt 全局 `setStyleSheet` ~1s 量级成本限制（下一阶段改为
  按面板局部 QSS + palette 优化）；
- 沙箱为静态审计（准入控制），运行时进程隔离留作后续阶段；
- 真实双显示器 / 跨屏 DPI 变化未物理验证。

---

## 包校验

发布包由 GitHub Actions 在 `windows-latest` 构建：

* `QingCaoEditor-v2.5.2-windows.zip`
* `QingCaoEditor-v2.5.2-windows.zip.sha256.txt`

```powershell
Get-FileHash .\QingCaoEditor-v2.5.2-windows.zip -Algorithm SHA256
# 与 .sha256.txt 比对
```
