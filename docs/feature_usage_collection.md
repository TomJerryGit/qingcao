# 真实使用数据采集说明（方案 A）

## 前提

- 使用 **v2.26.22**（功能使用统计已内置）；
- 统计默认开启、纯本地；关闭方式：`QINGCAO_FEATURE_USAGE=0`。

## 采集周期

- 正常使用 7–14 天；
- 不需要刻意操作，只记录真实菜单/工具栏动作。

## 数据文件

- 路径：`data/feature_usage.json`；
- 内容：动作名、次数、最后时间；
- **不含**：文本内容、文件路径、用户身份、网络信息。

## 交付方式

1. 直接发送 `data/feature_usage.json`；
2. 或粘贴文件内容。

## 我方处理

```powershell
python tools/feature_usage_report.py
```

生成 `docs/feature_usage_report.md` → 输出 Top / 低使用清单 → 完成 task-39。

## 校验

- 发送前确认文件内无路径/文本（只应有动作名）；
- 若担心隐私，可先只发动作名+次数两列。
