; =============================================================================
; create_installer_win.iss -- Genera PongIA_Setup.exe con Inno Setup 6
; =============================================================================
; Uso:
;   iscc /DAppVersion="Alfa 0.07" scripts\create_installer_win.iss
;
; Requisitos:
;   - dist\PongIA.exe debe existir (ejecutar antes build_with_pyinstaller.py)
;   - Inno Setup 6 instalado (https://jrsoftware.org/isdownload.php)
;
; Resultado:
;   dist\PongIA_Setup.exe
; =============================================================================

#ifndef AppVersion
  #define AppVersion "dev"
#endif

[Setup]
; Identificador unico de la aplicacion (no cambiar una vez publicado)
AppId={{B7E3A1F0-4D2C-4F8B-9A6E-1C3D5F7E9B0A}
AppName=PongIA
AppVersion={#AppVersion}
AppVerName=PongIA {#AppVersion}
AppPublisher=PongIA
DefaultDirName={autopf}\PongIA
DefaultGroupName=PongIA
OutputDir=..\dist
OutputBaseFilename=PongIA_Setup
; TODO: descomentar cuando se cree assets\images\icon.ico
; SetupIconFile=..\assets\images\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
WizardStyle=modern
; No requiere admin por defecto (instala en %LOCALAPPDATA%\Programs)
PrivilegesRequired=lowest
; Permite al usuario elegir instalar para todos (con elevacion)
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PongIA.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\models.toml.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\models"
Name: "{app}\saves"

[Icons]
Name: "{group}\PongIA"; Filename: "{app}\PongIA.exe"
Name: "{group}\{cm:UninstallProgram,PongIA}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\PongIA"; Filename: "{app}\PongIA.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PongIA.exe"; Description: "{cm:LaunchProgram,PongIA}"; Flags: nowait postinstall skipifsilent
