# 事件生命周期与线程保证

> 对应 `docs/npp_plugin_benchmark_v2.3.md` P1-7：Notepad++ 文档明确
> `NPPN_*` 通知的顺序与时机；本文把青草事件总线的保证写清楚，
> 并由 `tests/test_event_lifecycle.py` 锁定"文档与代码一致"。

## 事件目录（15 个，`api.list_events()` 可枚举）

| 事件 | 触发时机 | 典型用途 |
|---|---|---|
| `file_opened` | 文件内容加载完成、标签建立后 | 索引/统计/大纲刷新 |
| `file_saved` | **磁盘写入成功之后**（写入失败不发） | 格式化后处理、CI 触发 |
| `file_closed` | 标签关闭、编辑器仍可访问时 | 清理每文件状态 |
| `file_modified` | 外部修改被检测到并重载后 | 提示/重新索引 |
| `editor_changed` | 编辑内容变化（已做节流） | 字数统计、实时校验 |
| `cursor_moved` | 光标移动 | 状态栏、上下文提示 |
| `selection_changed` | 选区变化 | 选区工具、右键动作 |
| `tab_changed` | 当前标签切换 | 大纲/面板刷新 |
| `tab_added` | 新标签创建 | 面板联动 |
| `tab_removed` | 标签移除 | 清理缓存 |
| `project_opened` | 项目打开 | 任务面板、Git 上下文 |
| `project_closed` | 项目关闭 | 清理 |
| `macro_started` | 宏开始录制/回放 | 禁用干扰性 UI |
| `macro_stopped` | 宏结束 | 恢复 UI |
| `theme_changed` | **主题 QSS 应用之后** | 自定义绘制控件重取色 |

## 线程保证

1. **全部事件在主线程派发**：底层是 `EventBus(QObject)` 的 pyqtSignal，
   订阅回调由 Qt 派发到主线程；插件回调里可以安全操作 UI/编辑器。
2. **禁止在后台线程 emit**：`api.run_background` 的 `func` 里不要调用
   `api.emit_event`/`api.subscribe` 的回调逻辑；需要通知 UI 时在
   `on_done` 回调里做（该回调已在主线程）。
3. **订阅/退订必须成对**：`api.subscribe(name, cb)` 与
   `api.unsubscribe(name, cb)` 共用同一映射表（15 个事件全部支持），
   插件卸载时 `cleanup()` 会自动退订。
4. **顺序保证**：`file_saved` 一定在磁盘写入成功之后；`theme_changed`
   一定在 QSS 应用之后；同一事件内多个订阅者按注册顺序调用。

## 插件开发建议

```python
def on_activate(self):
    self.api.subscribe("file_saved", self._on_saved)

def on_deactivate(self):
    # cleanup() 会自动退订；显式退订更直观
    self.api.unsubscribe("file_saved", self._on_saved)

def _on_saved(self, event):   # 主线程，可安全操作 UI
    self.api.show_status("已保存", 1500)
```

## 已知限制

* `editor_changed` 为性能做了节流（高频输入不会逐键触发）；
* 事件参数类型为 dataclass（如 `FileSavedEvent`），字段见
  `app/event_bus.py`；
* 若在非主线程误用信号，Qt 会以队列方式投递，但**不要依赖**这一点做
  线程同步 —— 用 `run_background` 的 `on_done`。
