# QingCao Editor v2.24.4 发布说明

> 2026-11-11 · 上一版本：v2.24.3

## 终端（P3–P6）
- **P3 滚动区**：CSI r/S/T/L/M，LF 仅在区域内滚动；真实 PTY 验证 alt-screen + raw 回显 PASS；
- **P4**：滚动缓冲（2000 行）、24bit 真彩 + 256 色、鼠标上报（SGR ?1006）；
- **P5**：滚轮/拖动鼠标编码、滚动位置保持；
- **P6**：独立 scrollback 历史视图（查看/复制）、revision 渲染节流（内容未变跳过重绘）。

## 同时包含（v2.24.3 之后）
- 真实评分聚合：16 插件（average=5.0，count=1）签名 `ratings.json` 已上线；
- 终端 raw 输入直通（P1）、ANSI/alt-screen（P2）。

## 验证
- 终端测试 P1–P6：17/17 通过；
- P3 真实 PTY：alt-screen / raw 回显 PASS；
- 发布资产含 ZIP + SHA256 + Ed25519 `.sig`。
