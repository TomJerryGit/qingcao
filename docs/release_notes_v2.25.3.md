# QingCao Editor v2.25.3 发布说明

> 2026-11-13 · 上一版本：v2.25.2

## 安全（P0）
- **git 命令执行加固**：仅允许白名单子命令（rev-parse/status/diff/add/reset/commit/push/pull/log/show/branch/stash）；参数数组、`shell=False`、`GIT_TERMINAL_PROMPT=0`、15s 超时、1MB 输出上限；
- **AI 隐私模式**：设置页新增“禁止联网”；`AIClient._make_request` 在隐私模式下直接拒绝网络请求；
- **AI 取消守卫**：请求前检查取消状态，配合已有流式取消与超时；
- 配置页保存 `privacy_mode`，下次启动自动加载。

## 验证
- 新增 `tests/test_v226_p0_security.py`：git 白名单/截断、AI 隐私/取消、配置开关；
- P0 + 网络测试 10/10 通过。
