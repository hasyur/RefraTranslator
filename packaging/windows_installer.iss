#ifndef AppSourceDir
  #error AppSourceDir must point to the staged application directory
#endif

#ifndef AppVersion
  #error AppVersion must be passed by build_windows_installer.py
#endif

#ifndef WindowsVersion
  #error WindowsVersion must be passed by build_windows_installer.py
#endif

#ifndef PortableBuild
  #define PortableBuild "0"
#endif

#if PortableBuild == "1"
  #define OutputBaseName "RefraTranslator-Portable-Smoke"
  #define InstallUninstaller "no"
#else
  #define OutputBaseName "RefraTranslator-Setup"
  #define InstallUninstaller "yes"
#endif

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Setup]
AppId={{69A2D263-38BE-4B62-A105-1A6DDBEA7602}
AppName=RefraTranslator
AppVersion={#AppVersion}
VersionInfoVersion={#WindowsVersion}
AppPublisher=RefraTranslator
DefaultDirName={localappdata}\Programs\RefraTranslator
DefaultGroupName=RefraTranslator
MinVersion=10.0
DisableProgramGroupPage=yes
UsePreviousAppDir=no
UsePreviousGroup=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
Uninstallable={#InstallUninstaller}
OutputBaseFilename={#OutputBaseName}
WizardStyle=modern
LicenseFile={#AppSourceDir}\LICENSE
SetupLogging=no
Compression=lzma2/max
SolidCompression=yes
CloseApplications=no
RestartApplications=no

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

#if PortableBuild == "0"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Icons]
Name: "{autoprograms}\RefraTranslator"; Filename: "{app}\RefraTranslator.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\RefraTranslator"; Filename: "{app}\RefraTranslator.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\RefraTranslator.exe"; WorkingDir: "{app}"; Description: "启动 RefraTranslator"; Flags: postinstall nowait skipifsilent
#endif
