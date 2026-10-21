; AirWave 安装脚本（Inno Setup 6/7）
#define MyAppName "AirWave 局域网音频"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "AirWave"
#define MyAppExeName "AirWaveServer.exe"
#define MyPort "13666"

[Setup]
AppId={{A7C41E62-5B3D-4C11-9A7E-2D8B6F0C4E21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AirWave
DefaultGroupName=AirWave
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\app.ico
SetupIconFile=assets\app.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist\installer
OutputBaseFilename=AirWaveSetup-{#MyAppVersion}
CloseApplications=yes
MinVersion=10.0.17763

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"
Name: "firewall"; Description: "添加 Windows 防火墙规则（UDP {#MyPort}，推荐）"; GroupDescription: "网络:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=AirWave_UDP_{#MyPort} dir=in action=allow protocol=UDP localport={#MyPort} profile=private,domain"; Flags: runhidden; Tasks: firewall
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=AirWave_UDP_{#MyPort}"; Flags: runhidden; RunOnceId: "RemoveAirWaveFirewallRule"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
