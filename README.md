# 雷余双桌宠 Windows 版

> Windows 10/11 x64 重构版。GUI 使用 Python + PySide6，发行方式参考 `dsh-pet-indesktop`。

本项目正在把 [yuhanfu513-ops/leiyu-desktop-pets](https://github.com/yuhanfu513-ops/leiyu-desktop-pets) 的 macOS 双桌宠体验重构到 Windows：双透明窗口、拖动与位置记忆、随机独白、靠近问答、逐句字幕、弹动与歪头、原声/氦气模式、系统托盘和开机自启。

## 素材说明

**公开仓库和公开 Release 不包含雷军、余承东人物图片、音频或原始视频。** 这些素材不属于上游 MIT 代码许可范围，权利归各自权利人。

首次启动会提示导入你有权使用的原项目 `Assets` 文件夹或 ZIP。导入前会检查：

- `lei.png`、`yu.png` 为透明 PNG；
- `clips.json`、`clips-helium.json` 的 17 段台词完整；
- `Clips/`、`Clips-helium/` 中 34 个音频文件齐全；
- `pairs.json` 的 8 组问答引用有效。

## 当前状态

当前处于 Windows 首版开发阶段。目标产物：

- `LeiYu-Desktop-Pets-Windows-v1.0.0-x64-setup.exe`；
- `LeiYu-Desktop-Pets-Windows-v1.0.0-x64-portable.zip`；
- `SHA256SUMS.txt`。

## 从源码运行

```powershell
# 本地 Python 3.11-3.13
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -e ".[dev]"
.\.venv\Scripts\python.exe -m leiyu_pet
```

无素材时应用会打开导入向导，不会下载或嵌入第三方素材。

## 测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe scripts\verify_public_bundle.py --mode tracked
```

## 开源许可与致谢

代码与文档采用 MIT 许可证。窗口与拖动交互保留 `LICENSE-SunPet`；第三方依赖和素材边界见 `THIRD_PARTY_NOTICES.md`。

特别感谢：

- macOS 原作：[yuhanfu513-ops/leiyu-desktop-pets](https://github.com/yuhanfu513-ops/leiyu-desktop-pets)；
- Windows 工程框架参考：[MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop)；
- 交互上游参考：[Ganzhe2028/SunPet](https://github.com/Ganzhe2028/SunPet)。

完整致谢见 `CREDITS.md`。请优先支持与 Star 原作者仓库。
