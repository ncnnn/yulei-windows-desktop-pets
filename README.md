# 雷余双桌宠 Windows 版

> Windows 10/11 x64 重构版。GUI 使用 Python + PySide6，发行方式参考 `dsh-pet-indesktop`。

把 [yuhanfu513-ops/leiyu-desktop-pets](https://github.com/yuhanfu513-ops/leiyu-desktop-pets) 的 macOS 双桌宠体验重构到 Windows：双透明置顶窗口、拖动、随机独白、靠近问答、逐句字幕、弹动与歪头、原声/1.5 倍氦气、系统托盘与开机自启。

## 下载与安装

从 Releases 下载：

- `LeiYu-Desktop-Pets-Windows-v1.0.1-x64-setup.exe` — 安装版，装到 `%LOCALAPPDATA%\Programs\LeiYuDesktopPets`，无需管理员权限；
- `LeiYu-Desktop-Pets-Windows-1.0.1-x64-portable.zip` — 便携版，解压即用，数据写在同目录 `data\`；
- `SHA256SUMS.txt` — 校验和。

> 安装包未做代码签名，Windows SmartScreen 可能提示；选择“更多信息 → 仍要运行”即可。

数据目录：安装版为 `%APPDATA%\LeiYuDesktopPets`（配置、日志、导入素材）；便携版为 exe 同级 `data\`。

## 功能

- 两只独立、透明、置顶、无边框窗口，可拖动；按 PNG alpha 命中检测。
- 单击某只桌宠只播放它自己的独白；「两人对话一句」由右键/托盘菜单触发。
- 逐句字幕气泡，随音频进度同步。
- 靠近时互相歪头（距离可调），说话时轻微弹动。
- 原声 / 1.5 倍氦气两种配音，音量可调。
- 托盘菜单 + 右键菜单：显隐、播放、音量、距离、人物大小、声音模式、恢复位置、退出。
- 设置面板实时生效；开机自启写入 `HKCU\...\Run`，免提权。
- 单实例运行；重复启动会把已有实例带到前台。

## 素材

随包 `assets/default_pack/` 提供两只 AI 生成的头像与配音（17 段原声 + 17 段氦气，共 34 个音频、8 组问答），开箱即用。这些素材由项目维护者使用 AI 生成并随包分发，不涉及第三方人物肖像或音频授权。

如需替换为自己的素材：把 `lei.png`、`yu.png`、`clips.json`、`clips-helium.json`、`pairs.json` 以及 `Clips/`、`Clips-helium/` 放入 `assets/default_pack/`，或通过首次启动的导入向导导入到用户数据目录。校验规则见 [`docs/ASSETS.md`](docs/ASSETS.md)。

## 从源码运行

```powershell
# 需要 Python 3.11 - 3.13
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -e ".[dev]"
.\.venv\Scripts\python.exe -m leiyu_pet
```

## 测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe scripts\verify_public_bundle.py --mode tracked
```

## 构建与发布

onedir、便携版与安装器的构建步骤见 [`docs/BUILD.md`](docs/BUILD.md)；打 tag 自动发版流程见 [`docs/RELEASE.md`](docs/RELEASE.md)。

## 开源许可与致谢

代码与文档采用 MIT 许可证。窗口与拖动交互保留 `LICENSE-SunPet`；第三方依赖与素材边界见 `THIRD_PARTY_NOTICES.md`。

特别感谢：

- macOS 原作：[yuhanfu513-ops/leiyu-desktop-pets](https://github.com/yuhanfu513-ops/leiyu-desktop-pets)；
- Windows 工程框架参考：[MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop)；
- 交互上游参考：[Ganzhe2028/SunPet](https://github.com/Ganzhe2028/SunPet)。

完整致谢见 `CREDITS.md`。请优先支持与 Star 原作者仓库。
