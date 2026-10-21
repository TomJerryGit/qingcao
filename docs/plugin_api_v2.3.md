# 插件扩展点 API v2.3：补全 / 诊断 / 后台任务

> 这三个扩展点把插件从"挂菜单、加面板"升级为**参与编辑器智能**。
> 完整 API 面见 `app/plugins.py::PluginAPI`（90+ 方法）；本文只覆盖 v2.3 新增部分。

## 1. 补全提供者

```python
def on_activate(self, api):
    api.register_completion_provider(
        self.suggest,
        language_ids=["python", ".py"],   # None = 所有语言
    )

def suggest(self, prefix, language="", filepath=""):
    # 在主线程调用，必须快速返回；重活请用 run_background 缓存结果
    if prefix.startswith("qc"):
        return ["qc_helper", "qc_config"]
    return []
```

- 候选项会合并进 `EditorWidget.local_completions()`（本地词频/关键字之后），
  并走同一条 Scintilla 弹窗通道。
- 支持返回 `str` 列表，或 `{"label": ..., "insert_text": ..., "detail": ...}`。
- 权限：`editor_read`。异常被捕获，不会影响编辑器。
- 卸载时自动注销（`cleanup()`）。

宿主侧实现：`MainWindow.collect_plugin_completions()`。

## 2. 诊断发布（实时校验）

```python
def check(self, api):
    api.publish_diagnostics([
        {"line": 3, "col": 0, "severity": "error",
         "message": "未定义的变量 x", "code": "E001"},
    ])   # filepath=None 表示当前文件

def on_close(self, api):
    api.clear_diagnostics()
```

语义（重要）：
- 只替换**本插件来源**的诊断；再次发布 = 覆盖本插件上一批；
- 不会清掉 LSP / 其它插件发布的条目；
- 诊断进入 `core.problems.ProblemManager` → 「问题」面板 / 状态栏计数。
- 权限：`editor_read`。

宿主侧实现：`core.problems.get_problem_manager()`。

## 3. 后台任务

```python
def analyze(self, api):
    api.run_background(
        lambda: expensive_scan(path),          # 子线程执行
        on_done=lambda result: api.show_status("扫描完成: %s" % result),
        on_error=lambda msg: api.log(msg, "error"),
        name="scan",
    )
```

- `func` 在 **daemon 子线程**执行；`on_done/on_error` 由 QObject 信号桥
  **排队回主线程**执行（这正是插件自己 `threading` 最容易踩的坑：
  在窗口销毁后 emit → `RuntimeError: wrapped C/C++ object has been deleted`）。
- 插件卸载（`cleanup()`）会置 `cancelled`，迟到结果被丢弃。
- 约束：**`func` 内不要直接调用 PluginAPI**（API 只在主线程安全）；
  需要读写编辑器请在 `on_done` 里做。
- 返回 `threading.Thread`（可用 `is_alive()` 查询）。
- 权限：无。

## 权限与失败策略

| API | 权限 | 失败行为 |
|---|---|---|
| `register_completion_provider` | `editor_read` | 缺权限抛 `app.plugins.PermissionError` |
| `publish_diagnostics` / `clear_diagnostics` | `editor_read` | 同上；宿主缺问题时记日志返回 0 |
| `run_background` | 无 | `func` 抛异常 → `on_error(异常文本)` |

注意：`app/plugins.py` 自定义了自己的 `PermissionError`（不是内置的），
插件与测试请 `from app.plugins import PermissionError`。
