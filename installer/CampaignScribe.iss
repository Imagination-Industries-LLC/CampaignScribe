; CampaignScribe slim installer (Inno Setup 6). Built by build_installer.bat, which
; assembles build\installer-root\ first and passes /DAppVersion=<version>.
; The speech engine (torch etc.) is NOT bundled; the app downloads it on first run
; into %LOCALAPPDATA%\CampaignScribe\env.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId is fixed forever: it is how upgrades find the previous install.
AppId={{F6D8D313-407B-4B40-9E76-62DABEFD8B90}
AppName=CampaignScribe
AppVersion={#AppVersion}
AppPublisher=Imagination Industries LLC
AppPublisherURL=https://github.com/Imagination-Industries-LLC/CampaignScribe
AppSupportURL=https://github.com/Imagination-Industries-LLC/CampaignScribe
; Paths below are relative to the repo root.
SourceDir=..
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\CampaignScribe
DefaultGroupName=CampaignScribe
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=LICENSE
InfoBeforeFile=PRIVACY.md
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
CloseApplications=yes
RestartApplications=no
OutputDir=dist-installer
OutputBaseFilename=CampaignScribe-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
FinishedLabel=Setup has finished installing [name] on your computer.%n%nThe first time you start it, CampaignScribe downloads its speech engine.%n%nYour campaigns, transcripts and settings live in the AppData\Roaming\CampaignScribe folder of your user profile. Uninstalling never removes that folder.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "build\installer-root\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\CampaignScribe"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\bootstrap\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; AppUserModelID: "ImaginationIndustries.CampaignScribe"
Name: "{autodesktop}\CampaignScribe"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\bootstrap\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; AppUserModelID: "ImaginationIndustries.CampaignScribe"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\bootstrap\launcher.py"""; WorkingDir: "{app}"; Description: "Launch CampaignScribe"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\bootstrap"

[Code]
function DirBytes(const Dir: String): Int64;
var
  FindRec: TFindRec;
begin
  Result := 0;
  if FindFirst(Dir + '\*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          begin
            if (FindRec.Attributes and FILE_ATTRIBUTE_REPARSE_POINT) = 0 then
              Result := Result + DirBytes(Dir + '\' + FindRec.Name);
          end
          else
            Result := Result + (Int64(FindRec.SizeHigh) shl 32) + FindRec.SizeLow;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

{ Silent uninstall defaults to Yes: it removes the re-creatable speech engine, never user data.
  For all-users installs only the uninstalling account's engine is offered/removed. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  EnvDir, SizeText: String;
  Bytes: Int64;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  { Only the uninstalling user's engine is touched. %APPDATA%\CampaignScribe (user data) is never removed. }
  EnvDir := ExpandConstant('{localappdata}\CampaignScribe\env');
  if not DirExists(EnvDir) then
    Exit;
  Bytes := DirBytes(EnvDir);
  SizeText := Format('%.1f GB', [Bytes / 1073741824.0]);
  if SuppressibleMsgBox(
       'Also remove the downloaded speech engine (about ' + SizeText +
       ' in %LOCALAPPDATA%\CampaignScribe)?',
       mbConfirmation, MB_YESNO or MB_DEFBUTTON1, IDYES) = IDYES then
  begin
    DelTree(EnvDir, True, True, True);
    DeleteFile(ExpandConstant('{localappdata}\CampaignScribe\env-setup.log'));
  end;
end;
