# 真机首帧 QA（v2.25 阶段 3.5）

- 样本数：5（Windows 平台，非 offscreen）
- 首帧中位数：**0.517s**
- 首帧 P95：**0.772s**（阈值 < 0.8s）
- MainWindow 构造中位数：0.489s
- 结论：PASS

## 原始样本

- run1：first_paint=0.502s，mainwindow=0.478s，paint500=446，polish500=326
- run2：first_paint=0.517s，mainwindow=0.489s，paint500=292，polish500=326
- run3：first_paint=0.489s，mainwindow=0.464s，paint500=372，polish500=326
- run4：first_paint=0.706s，mainwindow=0.673s，paint500=139，polish500=326
- run5：first_paint=0.772s，mainwindow=0.732s，paint500=200，polish500=326
