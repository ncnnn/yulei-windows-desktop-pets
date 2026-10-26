# 构建

## 依赖

- Python 3.11 - 3.13（推荐 3.12 / 3.13）。
- 运行与打包依赖：`python -m pip install -e ".[dev]"`（含 PySide6、PyInstaller、pytest、ruff）。
- 安装器：Inno Setup 6（仅 Windows；CI 用 `choco install innosetup`）。

## 本地构建

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -e ".[dev]"

# 1) 生成多分辨率图标 packaging/app.ico
.\.venv\Scripts\python.exe scripts\make_icons.py

# 2) PyInstaller onedir（内含 assets\default_pack，并跑素材门禁）
pwsh -File scripts\build_onedir.ps1 -Python .venv\Scripts\python.exe

# 3) 便携版 ZIP（写入 portable.ini，并跑素材门禁）
pwsh -File scripts\make_portable_zip.ps1 -Python .venv\Scripts\python.exe -Version 1.0.1

# 4) 安装器（需 Inno Setup 6）
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.1 packaging\leiyu.iss
```

## 产物

| 产物 | 路径 |
| --- | --- |
| onedir | `dist\leiyu_pet\leiyu_pet.exe` + `_internal\` |
| 便携版 | `LeiYu-Desktop-Pets-Windows-1.0.1-x64-portable.zip` |
| 安装器 | `dist\installer\LeiYu-Desktop-Pets-Windows-v1.0.1-x64-setup.exe` |

## 打包要点

- `--onedir`（非 onefile），PySide6/Qt 动态库以独立文件保留，符合 LGPLv3 可替换要求。
- `--add-data "assets\default_pack;assets\default_pack"` 把默认素材放进 `_internal\assets`，运行时经 `sys._MEIPASS` 解析。
- 两个构建脚本都在产物上运行 `verify_public_bundle.py --mode bundle`，不通过即失败。
- 安装器为 per-user（`PrivilegesRequired=lowest`），装到 `%LOCALAPPDATA%\Programs`，无需管理员。

## 持续集成

- `.github/workflows/ci.yml`：Linux 上跑 ruff + pytest（offscreen）+ tracked 门禁。
- `.github/workflows/release.yml`：Windows 上构建三件套并发布 Release（见 `docs/RELEASE.md`）。
