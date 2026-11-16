# QingCao Editor v2.26.5 发布说明

> 2026-11-16 · 上一版本：v2.26.4

## 工程
- Release gate 修复：托管 fallback 运行中/API 抖动时保持等待，不再提前判失败；
- `test-fallback` 增加 tag（v*）触发，发布标签自动创建同 SHA 的托管全量测试；
- 验证：门禁单测 6/6。

## 验证
- 全量测试 3 片通过；ruff/format 全绿。
