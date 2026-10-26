; 雷余双桌宠 Windows 版 Inno Setup 安装脚本。
; 前置：先运行 scripts\build_onedir.ps1 生成 dist\leiyu_pet。
; 编译：ISCC.exe packaging\leiyu.iss

#define AppName "雷余双桌宠"
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#define AppPublisher "leiyu-desktop-pets-windows contributors"
#define AppExe "leiyu_pet.exe"

[Setup]
AppId={{8F3C2A1B-7D4E-4B90-A1C2-3E5F6789ABCD}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\LeiYuDesktopPets
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=LeiYu-Desktop-Pets-Windows-v{#AppVersion}-x64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=app.ico
LicenseFile=..\LICENSE
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
Source: "..\dist\leiyu_pet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'LeiYuDesktopPets');
end;
