# 发布流程

## 1. 更新版本号

同时修改：

- `src/leiyu_pet/__init__.py` 的 `__version__`
- `pyproject.toml` 的 `version`

安装器版本由 tag 通过 `/DAppVersion=` 传入，无需改 `leiyu.iss`。

## 2. 打 tag 触发自动发版

```bash
git add -A
git commit -m "release: v1.0.1"
git tag v1.0.1
git push origin main --tags
```

`.github/workflows/release.yml` 在 Windows runner 上依次执行：

1. 安装依赖并跑 pytest；
2. `build_onedir.ps1` 构建 onedir 并跑素材门禁；
3. `make_portable_zip.ps1` 生成便携版 ZIP 并跑门禁；
4. 安装 Inno Setup 并编译安装器；
5. 生成 `SHA256SUMS.txt`；
6. `gh release create` 上传三件套。

## 3. Release 产物

- `LeiYu-Desktop-Pets-Windows-v<version>-x64-setup.exe`
- `LeiYu-Desktop-Pets-Windows-<version>-x64-portable.zip`
- `SHA256SUMS.txt`

## 4. 校验

下载后可在 PowerShell 校验：

```powershell
Get-FileHash .\LeiYu-Desktop-Pets-Windows-v1.0.1-x64-setup.exe -Algorithm SHA256
# 与 SHA256SUMS.txt 中对应行比对
```

## 说明

- 安装包未做代码签名，Windows SmartScreen 可能提示；Release 说明中已提示用户选择“仍要运行”。
- 发版前务必确认 `verify_public_bundle.py --mode tracked` 通过，且 `assets/default_pack` 内容与预期一致。
