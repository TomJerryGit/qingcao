# 终端原始模式（v2.25 P1）

## 已实现（P1）
- `PtyLineEdit.raw_mode`：按键直通，不等待回车；
- `key_event_to_bytes()`：回车/退格/Tab/Esc/方向键/Home/End/Delete/PgUp/PgDn/Ctrl+A-Z 映射到 PTY 字节；
- `PtyTerminalTab` 顶部 **raw** 按钮切换；`send_raw()` 可直接注入字节；
- 窗口 resize 仍同步 PTY 尺寸（rows/cols）。

## 测试
`tests/test_v225_terminal_raw.py`：按键映射（回车/退格/方向/Esc/Ctrl+C/普通字符）+ raw 信号发射。

## 下一步（P2）
- ANSI/VT 子集渲染：alt-screen（`?1049h/l`）、光标定位、清屏、SGR 颜色；
- 可引入 `pyte`（纯 Python）解析，失败回退纯文本；
- `vim`/`top` 冒烟（伪终端 + 录制回放）。

## 说明
原始输入已可让交互程序收到正确按键；屏幕渲染仍为“追加输出”模式，因此全屏程序显示尚不完整（P2 解决）。

## P2（已实现）
- `ui/terminal_screen.py`：轻量 VT 屏幕模拟器（字符网格 + 属性）；
- 支持：`\r`/`\n`/`\b`/`\t`、光标定位 `CSI H/f/A/B/C/D/G`、清屏 `CSI J`/行清 `CSI K`、SGR 基本色/粗体、**alt-screen `?1049h/l` / `?47`**、ESC c 重置、CJK 宽字符；
- `PtyTerminalTab` 输出改为屏幕渲染（HTML pre），resize 同步行列；
- 测试：`tests/test_v225_terminal_screen.py`（文本/清屏/光标/alt-screen 回切/颜色）。

### P2 限制
- 尚未实现：滚动区、鼠标上报、复杂 VT（DEC 私有模式）、真彩色 24bit；
- `vim`/`top` 可进入 alt-screen 并显示内容；整屏重绘性能与细节（如行内移动光标刷新）仍需真实桌面验证。

## P3（已实现）
- `TerminalScreen` 支持**滚动区**：`CSI r` 设定区域、`CSI S/T` 区域内滚动、`CSI L/M` 插入/删除行、行尾 LF 只在区域内滚动；
- 真机验证脚本 `tools/verify_terminal_p3.py`：
  - 真实 **PTY**（pywinpty）子进程输出 alt-screen 序列 → 解析器识别并回切主屏；
  - **raw 输入回显**：向真实 PTY 写入 `PING`，子程序读 stdin 后回显 `RAW-OK:PING`；
  - 结果：两项 **PASS**（本机 Windows 无 vim/top，改用等价真实 PTY 验证；有 vim 的机器可手动按同样步骤验证）。
- 测试：`tests/test_v225_terminal_scroll.py`（滚动区/LF 隔离/插删行/区域重置）。
