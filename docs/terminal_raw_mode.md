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
