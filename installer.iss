; SPDX-License-Identifier: MIT
; ============================================================================
;  FORECAST-SW - Inno Setup 설치 마법사 스크립트
; ----------------------------------------------------------------------------
;  이 스크립트는 "설치형(.exe Setup)" 배포본을 만든다.
;  사용자는 생성된 Setup.exe 를 실행하면 프로그램이 설치되고
;  시작 메뉴/바탕화면 바로가기와 제거(언인스톨) 항목이 만들어진다.
;
;  [사전 준비]
;    1) Inno Setup 6 설치:  https://jrsoftware.org/isdl.php
;    2) onedir 형태로 빌드:  python build_exe.py --onedir
;         → dist\FORECAST-SW\FORECAST-SW.exe 생성
;    3) 라이브러리 관리자 빌드: python build_updater.py
;         → dist\FORECAST-SW-Equation-Library-Manager.exe 생성
;
;  [설치본 만들기]
;    A) Inno Setup Compiler 에서 이 파일(installer.iss)을 열고 [Build > Compile]
;       또는
;    B) 명령줄:
;         "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
;    → installer_output\FORECAST-SW_Setup_1.1.exe 생성
;       이 Setup.exe 하나만 다른 컴퓨터로 옮겨 실행하면 설치된다.
; ============================================================================

#define MyAppName "FORECAST-SW"
#define MyAppVersion "1.1"
#define MyAppPublisher "세종수목원"
#define MyAppExeName "FORECAST-SW.exe"
#define MyLibraryManagerExeName "FORECAST-SW-Equation-Library-Manager.exe"
; --onedir 빌드 산출물 폴더 (installer.iss 기준 상대경로)
#define MyDistDir "dist\FORECAST-SW"

[Setup]
; AppId 는 프로그램을 고유 식별 (업그레이드/제거 시 동일 값 유지). 임의 고정 GUID.
AppId={{8F3C2A14-6B9E-4D77-9A2E-7C1B5E0A4F21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FORECAST-SW
DefaultGroupName=FORECAST-SW
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=FORECAST-SW_Setup_{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 64비트 전용 (PyInstaller 산출물이 64비트일 때)
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
; 관리자 권한 없이 사용자 폴더에도 설치 가능하도록 선택지 제공
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

[Languages]
; Inno Setup 기본 제공(영문). 한국어 메시지를 쓰려면 아래 Korean.isl 줄의 주석을 해제.
; (Inno Setup 설치 폴더의 Languages\Korean.isl 존재 시)
Name: "english"; MessagesFile: "compiler:Default.isl"
; Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; onedir 산출물 폴더 전체를 설치 경로로 복사
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "dist\{#MyLibraryManagerExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} Equation Library Manager"; Filename: "{app}\{#MyLibraryManagerExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
