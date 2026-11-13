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

## 实测结果（2026-11-12）

工作流：`macos-spike.yml`（run 成功，托管 macos-latest / Apple Silicon）

| 项 | 结果 |
|---|---|
| Python | 3.11.9 |
| PyQt5 | 5.15.11（arm64 wheel） |
| QScintilla | 2.14.1（arm64 wheel） |
| Qt | 5.15.14 |
| 离屏子集 | **27/27 通过**（首次 26/29：缺 `cryptography`，补装后全绿） |
| 覆盖 | 架构门禁、密钥轮换、性能看板、终端屏幕、发现性 |

**决策门结论：PASS（≥90%）**。macOS 可行性成立，剩余为 PTY 适配、`.app` 打包、签名/公证（见上表差距）。

## 决策门

- 子集通过率 ≥90% 且差距可控 → 立 v3.x 里程碑（明确人力/账号）；
- 否则保持 Windows/Linux，macOS 仅记录为社区需求。

## R4 实现（2026-11-13）

### POSIX PTY
- `ui/pty_session.py` 双后端：Windows 用 pywinpty；macOS/Linux 用 `pty.openpty` + `subprocess`（`HAS_PTY`）；
- 新增 `tools/verify_terminal_posix.py`：/bin/sh 回显 + alt-screen 验证（Windows 下 SKIP）；
- 终端面板改用 `HAS_PTY` 判断交互 PTY 能力。

### .app 冒烟
- `macos-spike.yml` 新增：POSIX PTY 检查、`pip install pyinstaller`、`python build_macos.py`（advisory）；
- 结果写入 `macos_spike.log` 并上传 artifact，检查 `dist/*.app` 是否生成。

### 实测结果（2026-11-13）

macOS Spike 工作流（macos-latest / arm64）成功：

- `[posix-pty] echo=PASS alt-screen=PASS`（`tools/verify_terminal_posix.py`）；
- PyInstaller 构建：**APP_OK**（`dist/*.app` 生成）；
- 结论：macOS 终端与打包可行性验证通过；剩余为 `.app` 启动冒烟、签名/公证与 CI 常驻成本。
