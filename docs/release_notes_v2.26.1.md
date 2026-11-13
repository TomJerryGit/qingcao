# QingCao Editor v2.26.1 发布说明

> 2026-11-13 · 上一版本：v2.26.0

## P2 功能
- **AI 助手**：替换前 unified diff 预览；流式输出/选区优先上下文回归测试；
- **Git**：状态栏分支/脏文件数（5s 刷新）；切换/新建分支；暂存差异；**hunk 级暂存**（git apply --cached）；
- **Python 调试器**：条件断点（driver 求值跳过）；监视表达式（break 事件返回、面板展示）。

## 验证
- AI diff/流式/选区、Git hunk、调试器条件/监视测试通过；
- debugger 全量 78/78；ruff/format 全绿。
