# macOS 支持 spike（v3.0）

## 目标

1–2 天内判断 macOS 可行性，不承诺发布：

- PyQt5/QScintilla 在 macOS runner 可安装；
- 离屏核心测试子集可运行；
- 识别 PTY/打包/签名差距并估算工作量。

## 运行方式

GitHub Actions → **macOS Spike** → Run workflow（托管 `macos-latest`，仅手动触发）。

产物：`macos-spike-log` artifact（离屏子集 pytest 输出）。

## 覆盖范围（advisory）

- `test_v224_architecture_split`（架构门禁）
- `test_v225_key_rotation`（签名/信任清单，纯 Python）
- `test_v225_perf_dashboard`（HTML/SVG）
- `test_v225_terminal_screen`（VT 屏幕，纯逻辑）
- `test_v225_discoverability`（UI 离屏）

不覆盖：`pywinpty` 交互 PTY、Windows 注册表、托盘/全局快捷键、安装器。

## 已知差距

| 领域 | 现状 | 估计 |
|---|---|---|
| PTY | `ui/pty_session.py` 依赖 pywinpty（Windows-only） | 需 POSIX `pty`/`ptyprocess` 适配（1–2d） |
| 打包 | `build_macos.py` 存在但未在 CI 验证 | PyInstaller `.app`（2–3d） |
| 签名 | 无 Apple Developer 账号 | `codesign` + notarization（$99/年） |
| CI | 无 macOS 常驻 runner | 托管 runner 分钟成本 |

## 决策门

- 子集通过率 ≥90% 且差距可控 → 立 v3.x 里程碑（明确人力/账号）；
- 否则保持 Windows/Linux，macOS 仅记录为社区需求。
