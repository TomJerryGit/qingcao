# 插件安全沙箱（P2 第一阶段：静态能力审计）

## 为什么先做静态审计

插件 API 是进程内 QObject/信号模型；把插件整体迁移到子进程需要完整 RPC
代理，破坏兼容性且工程量大。真正的风险是**插件声明低权限却偷偷联网 /
起进程 / 删文件**——这类问题可在上架/CI 阶段用 AST 静态审计拦截。
本模块即"准入控制"层；运行时进程隔离留作后续阶段。

## 用法

```powershell
python -m tools.audit_plugins                  # 审计 plugins/ 全部
python -m tools.audit_plugins path/to/plugin   # 审计指定插件
python -m tools.audit_plugins --json           # 机器可读
python -m tools.audit_plugins --strict         # review/warn 也判失败
```

退出码：默认仅存在 `reject` 时返回 1；`--strict` 下 `review/warn` 也返回 1。

## 规则

| 代码 | 级别 | 含义 |
|---|---|---|
| SBX000 | high | 语法错误，无法审计 |
| SBX001 | high | manifest 无法读取 |
| SBX101 | warning | 导入需权限的模块（socket/http/urllib/requests → network；subprocess/multiprocessing/ctypes → process） |
| SBX102 | high | 调用危险函数（os.system/popen/exec*、os.remove/rmdir、shutil.rmtree → process/filesystem） |
| SBX103 | high | `eval/exec/compile/__import__` 动态执行 → **danger**（需人工评审） |
| SBX104 | warning | 以写模式 `open()` → filesystem |

## 判定

| verdict | 条件 | 处理 |
|---|---|---|
| `pass` | 无发现 | 直接上架 |
| `warn` | 有发现但权限已声明 | 允许，记录 |
| `review` | 缺权限声明 **或** 含 danger 项 | 人工评审（如调试器 eval） |
| `reject` | manifest/语法不可读等硬错误 | 拒绝 |

## 内置插件现状（`python -m tools.audit_plugins`）

- 8 个 pass；`spell_check`、`json_formatter` 等因真实文件写入/网络能力
  声明对应权限后为 `warn`；
- `python_debugger` 合法使用 `eval/compile`（调试器核心功能）+ process
  权限，判为 `review`（人工评审），不自动拒绝。

## 接入建议

- CI：`python -m tools.audit_plugins --strict` 对内置插件保留白名单；
- 商店：上架前 `reject/review` 插件不得自动安装；`warn` 展示能力徽章。
