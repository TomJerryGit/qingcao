# AI 自动调试运行器安全策略（Sprint 1）

## 默认策略

- **禁止网络**：默认子进程内 `socket.socket` / `create_connection` 直接抛错；
- 超时：默认 15 秒，超时强杀；
- 输出上限：100KB；
- 内存：默认 512MB（psutil 可用时监控，超限 kill）；
- CPU：可选 `max_cpu_seconds`；
- 仅允许运行存在的 `.py` 文件。

## 显式放开

```python
run_python_file(path, allow_network=True)  # 仅受控场景
run_python_file(path, max_memory_mb=256)   # 收紧
```

## 限制说明

- 网络阻断是 **Python 层** 尽力而为，不阻止原生扩展直接发包；
- 无强 OS 沙箱/文件系统隔离；不要对不可信代码开启网络；
- 自动调试菜单使用默认禁网策略。
