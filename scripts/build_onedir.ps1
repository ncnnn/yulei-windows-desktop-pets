# 构建 PyInstaller onedir 产物，并跑公开素材门禁。
# 用法： pwsh -File scripts/build_onedir.ps1 [-Python .venv\Scripts\python.exe]
param(
    [string]$Python = "python",
    [string]$Name = "leiyu_pet"
)

# 原生命令（PyInstaller）会往 stderr 写日志；把 stderr 当终止错误会让构建中断。
# 统一改为按退出码判定成败。
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path "packaging\app.ico")) {
    & $Python scripts\make_icons.py
    if ($LASTEXITCODE -ne 0) { throw "生成图标失败" }
}

& $Python -m PyInstaller `
    --noconfirm --clean --onedir --windowed `
    --name $Name `
    --icon packaging\app.ico `
    --paths src `
    --add-data "assets\default_pack;assets\default_pack" `
    packaging\entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }

& $Python scripts\verify_public_bundle.py --mode bundle --root "dist\$Name"
if ($LASTEXITCODE -ne 0) { throw "产物素材门禁未通过" }

Write-Host "onedir 产物：dist\$Name"
