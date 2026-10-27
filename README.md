# 雷余双桌宠 Windows 版

> Windows 10/11 x64 重构版，Python + PySide6，提供安装版与免安装（便携）版。

把 [yuhanfu513-ops/leiyu-desktop-pets](https://github.com/yuhanfu513-ops/leiyu-desktop-pets) 的 macOS 双桌宠体验重构到 Windows：双透明置顶窗口、拖动、随机独白、靠近问答、逐句字幕、弹动与歪头、原声/1.5 倍氦气、**相声模式**、全局热键、系统托盘与开机自启。

## 下载与安装

从 Releases 下载：

- `LeiYu-Desktop-Pets-Windows-v1.3.0-x64-setup.exe` — 安装版，装到 `%LOCALAPPDATA%\Programs\LeiYuDesktopPets`，无需管理员权限；
- `LeiYu-Desktop-Pets-Windows-1.3.0-x64-portable.zip` — 便携版，解压即用，数据写在同目录 `data\`；
- `SHA256SUMS.txt` — 校验和。

> 安装包未做代码签名，Windows SmartScreen 可能提示；选择“更多信息 → 仍要运行”即可。
>
> **免安装版双击没反应？** 从网络下载的 exe 会被 Windows 打上「锁定」标记：右键 `leiyu_pet.exe` →
> 属性 → 常规 → 勾选「解除锁定」→ 应用，再运行。

数据目录：安装版为 `%APPDATA%\LeiYuDesktopPets`（配置、日志、导入素材）；便携版为 exe 同级 `data\`。
两个版本的设置项完全一致，区别只在数据目录位置。

## 功能

- 两只独立、透明、置顶、无边框窗口，可拖动；按 PNG alpha 命中检测。
- 单击某只桌宠只播放它自己的独白；「两人对话一句」由右键/托盘菜单触发。
- **相声模式**：两只按 1-2-1-2 交替，把 4/6/8/10/12 句连续说完，可随时停止。
- 逐句字幕气泡，随音频进度同步；字号 9–20 可调。
- 靠近时互相歪头（距离可调），说话时轻微弹动；可开启「减少动效」。
- **三组新动作**：点头、挥手、原地转圈；双击桌宠转一圈，两人对话开始时互相点头。
- 原声 / 1.5 倍氦气两种配音，音量可调；窗口透明度 30%–100% 可调。
- **免打扰时段**：支持跨午夜区间，时段内不提醒、不弹气泡。
- **整点报时 + 久坐提醒**：静音气泡提示，久坐间隔 30/45/60/90 分钟可选。
- **番茄钟**：专注 15/25/45/60 分钟 + 休息 5/10/15 分钟，托盘/右键/设置均可启停。
- **自动游走**：空闲时在屏幕内缓慢溜达，间隔可调；拖动或说话时自动让路。
- **最近说过**：保留最近 8 条播放记录，托盘/右键一键重播。
- **重叠自动对喷**：两只叠在一起时自动来一段问答（带冷却，默认关闭）。
- **设置中心**（右键「设置…」或托盘「设置」）：声音、互动、系统、关于四页，改动即时生效并落盘。
- **开机自启**开关在设置与托盘中都有，写入 `HKCU\...\Run`，免提权，卸载时清理。
- **全局热键**：`Ctrl+Alt+H` 显隐、`Ctrl+Alt+K` 相声模式、`Ctrl+Alt+R` 随机一句、
  `Ctrl+Alt+M` 静音/恢复、`Ctrl+Alt+X` 停止。
- **置顶开关**：可关闭「始终置顶」，让桌宠正常被其它窗口盖住。
- **记住位置**：退出时保存两只桌宠坐标，下次启动还原并自动夹回可见屏幕。
- **更新检查**：启动时查询 GitHub 最新 Release，发现新版本用托盘气泡提示（只提示，不自动安装）。
- **故障诊断**：`leiyu_pet.exe --selftest-audio` 检查音频解码后端并试播一段，输出 JSON。
- 日志滚动（512 KB × 3），未捕获异常写日志并弹托盘提示。
- 托盘菜单 + 右键菜单：显隐、播放、音量、距离、人物大小、声音模式、恢复位置、设置、退出。
- 单实例运行；重复启动会把已有实例带到前台。

## 素材与版权

仓库内随包分发的头像与音频**不在 MIT 许可范围内**，版权归原权利人所有。本项目仅用于学习交流与玩梗，**不用于任何商业用途**；权利人如认为使用方式不当，欢迎开 issue，我们会及时移除。详见 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

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

代码与文档采用 MIT 许可证，详见 `LICENSE`。素材权利与第三方依赖边界见 `THIRD_PARTY_NOTICES.md`。

致谢（仅此一项）：

- [yuhanfu513-ops/leiyu-desktop-pets](https://github.com/yuhanfu513-ops/leiyu-desktop-pets) — macOS 原作，本项目的玩法来源。

请优先支持与 Star 原作者仓库。完整致谢见 `CREDITS.md`。
