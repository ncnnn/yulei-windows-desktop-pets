# 把 onedir 产物打包成便携版 ZIP（写入 portable.ini 标记）。
# 用法： pwsh -File scripts/make_portable_zip.ps1 [-Version 1.0.0] [-Python .venv\Scripts\python.exe]
param(
    [string]$Python = "python",
    [string]$Name = "leiyu_pet",
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$source = "dist\$Name"
if (-not (Test-Path $source)) { throw "缺少 $source，请先运行 build_onedir.ps1" }

$folderName = "LeiYu-Desktop-Pets-Windows-$Version-x64"
$stage = "dist\portable\$folderName"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Copy-Item -Recurse -Force "$source\*" $stage
$portableIni = @"
[portable]
version=$Version
"@
Set-Content -Path (Join-Path $stage "portable.ini") -Value $portableIni -Encoding ASCII

& $Python scripts\verify_public_bundle.py --mode bundle --root $stage
if ($LASTEXITCODE -ne 0) { throw "便携版素材门禁未通过" }

$zip = "LeiYu-Desktop-Pets-Windows-$Version-x64-portable.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $stage -DestinationPath $zip -Force

Write-Host "便携版：$zip"
