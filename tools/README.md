# tools/ - 开发工具集

青草编辑器的辅助工具目录。

## 统一 CLI

所有常用工具通过 `qingcao.py` 统一调用：

```bash
# 列出所有命令
python tools/qingcao.py list

# 依赖检查
python tools/qingcao.py check

# 项目健康扫描
python tools/qingcao.py health

# AI 配置诊断
python tools/qingcao.py diagnose-ai

# 代理环境诊断
python tools/qingcao.py diagnose-proxy

# 快速自检
python tools/qingcao.py quick-check

# 创建插件骨架
python tools/qingcao.py new-plugin my_plugin
```

## 目录说明

| 文件 | 说明 |
|------|------|
| `qingcao.py` | CLI 主入口 |
| `check_deps.py` | 依赖版本检查 |
| `health_check.py` | 项目健康扫描 |
| `diagnose_ai.py` | AI 配置诊断 |
| `diagnose_proxy.py` | 代理环境诊断 |
| `quick_check.py` | 快速验证修复 |
| `create_plugin.py` | 插件脚手架 |
| `_archive/` | 一次性修复脚本归档 |

## 单独运行

每个脚本仍可独立执行：

```bash
python tools/check_deps.py
python tools/health_check.py
```

## 归档脚本（`_archive/`）

2026-09 的 P0/P2/P3 修复脚本已完成使命，
归档保留以备参考。**日常不需要执行**。
