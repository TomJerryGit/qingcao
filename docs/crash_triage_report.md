# 崩溃聚合报告（crash triage）

- 生成时间：2026-11-13 09:10:18
- faulthandler/dump 文件：9（空文件 5）
- WER/minidump 数量：5
- CI flaky 记录：8

| 次数 | 签名 | 来源 |
|---|---|---|
| 2 | unknown | ? | crashed_test_v218_p2.py.log, crashed_test_v223_linux_appimage.py.log |
| 1 | Windows fatal exception: code 0x8001010d | main_window.py:_show_daily_tip | crash_dump_1116.log |
| 1 | Windows fatal exception: code 0x8001010d | socket.py:getaddrinfo | crash_dump_11256.log |
