# 移植说明（macOS → Windows）

## 从原作到本版

| 原作（macOS） | 本版（Windows） |
| --- | --- |
| 进程/Cocoa 窗口 | 单进程 PySide6，两个独立 `QWidget` 透明置顶窗口 |
| 跨进程/Apple 事件 | 单进程内 `PetRuntime` 统一装配窗口、音频、控制器 |
| 系统音频通道 | `QMediaPlayer` + `QAudioOutput` 单通道 `AudioCoordinator` |
| `Assets/` 素材 | 随包 `assets/default_pack/` + 用户导入 store |
| macOS 登录项 | `HKCU\...\Run`（`winreg`，免提权） |
| 无安装包 | PyInstaller onedir + Inno Setup per-user 安装器 + 便携 ZIP |

## 纯逻辑分层（不依赖 PySide6）

`models`、`clips`、`shuffle`、`proximity`、`dialogue`、`subtitles`、`manifest`、
`asset_importer`、`config`、`paths`、`autostart` 保持纯 Python，便于单元测试。
Qt 相关代码集中在窗口、音频、控制器、托盘、对话框。

## 关键语义

- 17 段台词：`lei` 9 段、`yu` 8 段；8 组问答按 `pairs.json` 顺序。
- 字幕按 `clips*.json` 的 `lines` 逐句显示；氦气版时间轴按 1.5 倍压缩。
- 靠近判定用人物脸部矩形距离（`proximity`），阈值来自配置 `distance`。
- 声音模式：`normal` 读 `Clips/`，`helium` 读 `Clips-helium/`，两者文件同名。

## 工程约定

- `src/` 布局，`pythonpath=["src"]`；ruff `line-length=100`，`select E/F/I/UP/B`。
- 配置与路径解析集中在 `paths.py` / `config.py`，安装版与便携版共用。
- 素材门禁 `verify_public_bundle.py` 只放行 `assets/default_pack/`。

## 致谢映射

- 玩法与台词结构：[yuhanfu513-ops/leiyu-desktop-pets](https://github.com/yuhanfu513-ops/leiyu-desktop-pets)
