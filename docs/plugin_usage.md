# 插件使用统计（P2，隐私安全）

## 采集内容

- 插件名、激活/停用次数、首次/最近时间戳；
- **不采集**：文件路径、文本内容、用户身份、网络信息。

## 存储与关闭

- 本地文件：`data/plugin_usage.json`（原子写）；
- 关闭：环境变量 `QINGCAO_PLUGIN_USAGE=0`；
- 报告：`python tools/plugin_usage_report.py` → `docs/plugin_usage_report.md`。

## 用途

- 识别低频/高频插件，辅助优化排序与维护优先级；
- 不做任何上传/遥测。
