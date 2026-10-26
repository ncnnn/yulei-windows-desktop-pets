# 第三方声明

本项目代码采用 MIT 许可证。以下来源与运行时组件保留各自许可证与版权：

## 上游项目

- `yuhanfu513-ops/leiyu-desktop-pets`：原始雷余双桌宠的交互设计、台词清单结构、问答顺序与部分算法语义，MIT，Copyright (c) 2026 yuhanfu513-ops。
- `Ganzhe2028/SunPet`：透明窗口与拖动交互的早期参考，MIT；许可证全文见 `LICENSE-SunPet`。
- `MerZlin/dsh-pet-indesktop`：PySide6 Windows 窗口、自启、托盘、onedir 与 Inno Setup 工程方法参考，MIT。

## 运行时与构建工具

- Python：https://docs.python.org/3/license.html
- Qt for Python / PySide6：https://doc.qt.io/qtforpython/licenses.html
  - PySide6/Qt 动态库按 LGPLv3/GPLv3/商业许可证分发；本项目不修改 Qt 动态库，使用 onedir 方式保留可替换性。
- PyInstaller：https://pyinstaller.org/en/stable/license.html
- Inno Setup：https://jrsoftware.org/files/is/license.txt

## 不随公开发行包分发的素材

雷军、余承东人物图片、音频及原始视频不属于本项目 MIT 许可范围，权利归各自权利人。公开仓库、自动构建产物与 Release 不包含这些素材；用户只能导入自己有权使用的素材副本。
