# 青草编辑器 v2.15.0 发布说明（草稿）

> 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.15.0`）
> 主题：**插件体验与开发安全**

---

## 新增

### 沙箱诊断按文件聚合展示
- 对所有已打开文件分别运行沙箱子进程诊断；
- 问题面板按文件分组显示（来源 `sandbox:<插件名>`）；
- 实时诊断仍只计算当前文件，避免多文件频繁 RPC。

### python_debugger 安全复核
- 新增受限表达式求值 `_safe_eval`：
  - 仅允许表达式（非语句）；
  - 拒绝 dunder 名称/属性与危险内建（open/exec/eval/compile/__import__ 等）；
  - 表达式长度限制 4000 字符，语法错误返回可读文本。
- 安全复核文档：`docs/security_review_python_debugger_v2.15.md`。

## 验证

- 定向/全量测试通过；ruff 0；
- 新增 `tests/test_sandbox_diag_aggregate.py`、`tests/test_debugger_eval_guard.py`。

## 升级注意事项

- v2.14.2 → v2.15.0 无数据迁移；
- 调试器表达式限制属安全加固，若遇受限表达式可反馈白名单需求。