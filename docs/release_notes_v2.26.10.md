# QingCao Editor v2.26.10 发布说明

> 2026-11-16 · 上一版本：v2.26.9

## 测试/安全
- **隔离插件 UI 级 e2e**：git_deep 菜单 → 子进程 RPC → 宿主 Git API → 对话框；
- 隔离 API 补齐 `get_current_filepath`、`show_text_dialog`；
- git_deep 声明 `editor_read` 权限，完善插件目录元数据；
- 发布上传超时改为 900s + 3 次重试（修复大资产上传失败）。

## 验证
- 隔离 UI/市场/conformance 14/14；全量测试通过。
