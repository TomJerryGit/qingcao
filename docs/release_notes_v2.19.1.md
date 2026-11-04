# 青草编辑器 v2.19.1 发布说明

> 类型：CI 稳定性补丁（无用户可见功能变化）
> 版本：2.19.1

## 修复
- **CI 分片原生崩溃误报**：分片 `rc=0xC0000005`（Qt 并行崩溃）且逐文件复跑全部通过时，
  自动判定为 flaky 放行；真实失败仍正常拦截。
- **运行器假失败**：GBK 控制台打印 `✅`/中文触发 UnicodeEncodeError 导致 exit 1；
  运行器启动时强制 stdout/stderr UTF-8。
- `tools/check_version.py` 支持预发布版本号（-alpha/-beta/-rc）基线比较。

## 验证
- 本地 CI 同参数连续 3 次：全部通过（153~241s，无崩溃/无 fallback 触发）；
- 自托管 CI test / test-py312 全绿。

## 升级
v2.19.0 → v2.19.1 无数据迁移。
