# 发布链路加固验证（Sprint 1 / task-34）

## 已完成加固

| 项 | 实现 |
|---|---|
| Runner TLS 健康检查 | `tools/diagnose_runner_tls.ps1` |
| Package 重试 | Release workflow Compress-Archive 3 次重试 + 缺失即抛错 |
| ZIP 缺失回退 | `ci_publish_release.ensure_package()` 从 `dist/QingCaoEditor` 自动重打包 + 重算 SHA |
| 安装器资产 | 自动检测并上传 |
| 发布资产校验 | 缺失资产 / 缺失名称会失败 |

## 近期发布证据

| 版本 | 结果 | 一次成功？ |
|---|---|---|
| v2.26.19 | success | ✅ |
| v2.26.20 | 多次失败后成功（Build/环境/手动发布） | ❌ |
| v2.26.21 | 多次失败后成功（门禁参数/格式/ZIP 丢失） | ❌ |

## 结论

- 加固措施已落地并经过真实故障验证；
- “连续 3 次一次成功”目标**尚未达成**（1/3 左右）；
- 下一版 v2.26.22 作为第一次干净验证；若再失败，继续按日志修复但不降低门禁。

## 测试

`tests/test_v226_release_hardening.py` 覆盖 ZIP 缺失自动重打包。
