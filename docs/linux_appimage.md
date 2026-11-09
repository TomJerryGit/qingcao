# Linux AppImage 构建（v2.23 P1-3）

## 方案
- GitHub-hosted `ubuntu-22.04`；
- PyQt5/QScintilla 使用 Ubuntu 系统包（避免源码编译）；
- PyInstaller onedir → AppDir → appimagetool → AppImage；
- 冒烟：`QINGCAO_HEADLESS_SMOKE=1` + `APPIMAGE_EXTRACT_AND_RUN=1`（无需 FUSE）。

## 本地验证（Linux）
```bash
sudo apt-get install -y python3-pyqt5 python3-pyqt5.qsci python3-pyqt5.qtmultimedia xvfb
python3 -m pip install --user -r requirements-linux-ci.txt
python3 tools/build_linux_appimage.py
QINGCAO_HEADLESS_SMOKE=1 APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a ./dist/QingCaoEditor-x86_64.AppImage
```

## 产物
`dist/QingCaoEditor-x86_64.AppImage` → CI artifact；tag 构建时自动上传 GitHub Release（`gh release upload --clobber`）。

## 限制
- 仅 x86_64；未做 ARM；
- 依赖 Ubuntu 22.04 的 Qt5 版本，其他发行版需 AppImage 自带库（PyInstaller 已收集）；
- 无自动更新通道（桌面 Linux 暂按手动下载）。
