# QingCao Editor v2.26.2 发布说明

> 2026-11-13 · 上一版本：v2.26.1

## P3 体验
- JSON：JSONC（注释/尾逗号）、Schema 校验、选区格式化；
- wordcount：选区统计、CJK 词数、目标进度；
- logtail：正则过滤、暂停、多文件切换、轮转重读。

## 工程
- **Test 主路径迁移托管**：`test-fallback`（windows-latest）承接 push 全量测试；自托管 Test 改为每日深度检查；发布门禁接受同 SHA fallback；
- 样例清理：`my_plugin` 默认禁用；新增 `docs/plugin_samples.md`。

## 验证
- P3 测试 5/5；插件相关测试通过；
- 托管 Test Fallback 在 main push 实测 **success**（17:05–17:07）。
