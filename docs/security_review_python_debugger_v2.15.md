# python_debugger 安全复核（v2.15）

> 日期：2026-10-29 · 插件：python_debugger 2.0.0 · 审计工具：tools/audit_plugins.py

## 风险面

| 能力 | 位置 | 说明 |
|---|---|---|
| eval(expression) | driver.py | 调试目标**子进程**内对用户输入表达式求值 |
| compile(source) | driver.py | 编译被调试脚本（调试器固有） |
| subprocess.Popen | session.py / __init__.py | 启动被调试进程（插件固有） |

## 处置（本次）

1. **表达式长度限制** 4000 字符（已有）；
2. **受限求值 `_safe_eval`**：
   - 仅允许表达式（`ast.parse(mode="eval")`）；
   - 拒绝 dunder 名称/属性（`__import__`、`(1).__class__` 等）；
   - 拒绝危险内建：`open/exec/eval/compile/input/breakpoint/exit/quit/
     globals/locals/vars/getattr/setattr/delattr/memoryview/help`；
   - 语法错误返回可读文本，不中断调试会话。
3. **权限声明**：manifest 已含 `process`（v2.14.0），与实际 subprocess 使用匹配；
4. subprocess 调用**不使用 shell=True**，调试目标为标准 Python 进程。

## 残余风险（接受并记录）

- 调试器本质上需要在目标进程中执行用户代码/表达式，无法做到完全沙箱化；
- 表达式仍可调用目标进程内已有对象的公开方法（如已打开文件对象的 write），
  属调试器功能范围，需用户确认被调试代码可信；
- 后续可考虑：表达式求值迁移到受限 RPC 或增加显式"允许任意表达式"开关。

## 验证

- `tests/test_debugger_eval_guard.py`：正常表达式、dunder/危险内建拦截、
  语法错误文本；
- 安全审计：`python -m tools.audit_plugins`（review 属预期）。