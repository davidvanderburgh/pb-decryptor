; PB Asset Decryptor — Inno Setup Script
; Compile with: ISCC.exe /DAppVersion=1.0.0 /DPythonDir=build\python /DProjectDir=.. pb_decryptor.iss
; Or use build.ps1 which handles everything automatically.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef ProjectDir
  #define ProjectDir ".."
#endif

#ifndef PythonDir
  #define PythonDir "build\python"
#endif

[Setup]
AppId={{B7E5F2C4-6A9D-4B8E-B1F3-2C4A8E6B9D1F}
AppName=PB Asset Decryptor
AppVersion={#AppVersion}
AppVerName=PB Asset Decryptor v{#AppVersion}
AppPublisher=David Vanderburgh
AppPublisherURL=https://github.com/davidvanderburgh/pb-decryptor
AppSupportURL=https://github.com/davidvanderburgh/pb-decryptor/issues
DefaultDirName={autopf}\PB Asset Decryptor
DefaultGroupName=PB Asset Decryptor
OutputBaseFilename=PB_Asset_Decryptor_Setup_v{#AppVersion}_Windows
SetupIconFile={#ProjectDir}\pb_decryptor\icon.ico
UninstallDisplayIcon={app}\pb_decryptor\icon.ico
LicenseFile={#ProjectDir}\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
WizardSizePercent=110
DisableProgramGroupPage=auto
VersionInfoVersion={#AppVersion}.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "runprereqs"; Description: "Install WSL2 prerequisites (only needed for Clonezilla .iso extraction)"; GroupDescription: "Prerequisites:"; Flags: unchecked

[Files]
; Bundled Python with tkinter
Source: "{#PythonDir}\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion

; Application package
Source: "{#ProjectDir}\pb_decryptor\__init__.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\__main__.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\app.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\clonezilla.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\config.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\executor.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\formats.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\gui.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\pipeline.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\updater.py"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\icon.ico"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion
Source: "{#ProjectDir}\pb_decryptor\icon.png"; DestDir: "{app}\pb_decryptor"; Flags: ignoreversion

; Entry point and launcher
Source: "{#ProjectDir}\PB Asset Decryptor.pyw"; DestDir: "{app}"; Flags: ignoreversion
Source: "launcher.vbs"; DestDir: "{app}"; Flags: ignoreversion

; Prerequisites installer (can be re-run from Start Menu)
Source: "install_prerequisites.ps1"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "{#ProjectDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\PB Asset Decryptor"; Filename: "wscript.exe"; Parameters: """{app}\launcher.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\pb_decryptor\icon.ico"; Comment: "Extract and re-pack Pinball Brothers game assets"
Name: "{group}\Install Prerequisites"; Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install_prerequisites.ps1"""; WorkingDir: "{app}"; Comment: "Install WSL2 + Ubuntu (only needed for Clonezilla .iso extraction)"
Name: "{group}\{cm:UninstallProgram,PB Asset Decryptor}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{autodesktop}\PB Asset Decryptor"; Filename: "wscript.exe"; Parameters: """{app}\launcher.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\pb_decryptor\icon.ico"; Tasks: desktopicon; Comment: "Extract and re-pack Pinball Brothers game assets"

[Run]
; Run prereqs installer if user opted in
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install_prerequisites.ps1"""; WorkingDir: "{app}"; StatusMsg: "Installing prerequisites..."; Flags: runascurrentuser shellexec waituntilterminated; Tasks: runprereqs

; Offer to launch the app after install
Filename: "wscript.exe"; Parameters: """{app}\launcher.vbs"""; WorkingDir: "{app}"; Description: "Launch PB Asset Decryptor"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\pb_decryptor\__pycache__"

[Code]
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  if Version.Major < 10 then
  begin
    MsgBox('PB Asset Decryptor requires Windows 10 or later.', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  Result := True;
end;
