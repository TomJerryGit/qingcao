; QingCao Editor Installer Script
; 需要 Inno Setup 6+ : https://jrsoftware.org/isdl.php

#define MyAppName "青草编辑器"
#define MyAppNameEn "QingCao Editor"
; C4 修复：版本号由 build_installer.py 生成的 installer_version.iss 提供
; 若该文件不存在，回退到默认值
#if FileExists("installer_version.iss")
#include "installer_version.iss"
#else
#define MyAppVersion "2.4.0"
#endif
#define MyAppPublisher "hedongwei"
#define MyAppURL "https://github.com/qingcao-editor/qingcao"
#define MyAppExeName "QingCaoEditor.exe"

[Setup]
AppId={{8D4F5E7A-1234-4B5C-9D8E-123456789ABC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\QingCaoEditor
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=installer
OutputBaseFilename=QingCaoEditor_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
SetupIconFile=resources\icons\qingcao.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"
Name: "quicklaunchicon"; Description: "创建快速启动栏图标"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "dist\QingCaoEditor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\backup"

[Registry]
; 文件关联
Root: HKA; Subkey: "Software\Classes\.qc"; ValueType: string; ValueName: ""; ValueData: "QingCao.Document"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\QingCao.Document"; ValueType: string; ValueName: ""; ValueData: "青草文档"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\QingCao.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\QingCao.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; 右键菜单
Root: HKA; Subkey: "Software\Classes\*\shell\QingCao"; ValueType: string; ValueName: ""; ValueData: "通过青草编辑器打开"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\*\shell\QingCao"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\*\shell\QingCao\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""