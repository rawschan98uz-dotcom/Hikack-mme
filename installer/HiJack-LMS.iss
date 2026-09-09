; Hi Jack LMS - Inno Setup script

#define MyAppName "Hi Jack LMS"
#define MyAppVersion "1.2.6"
#define MyAppPublisher "Hi Jack LMS"
#define MyAppURL "http://127.0.0.1:8000/"

[Setup]
AppId={{7E1F4C92-6A3B-4D58-9F0C-21B7A9D3E5F1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\HiJack-LMS
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=D:\projects\Hijack-mme
OutputBaseFilename=HiJack-LMS-Setup
SetupIconFile=D:\projects\Hijack-mme\app\desktop\assets\lms.ico
UninstallDisplayIcon={app}\assets\lms.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Dirs]
Name: "{app}\app\backend\media"; Permissions: users-modify
Name: "{app}"; Permissions: users-modify

[Files]
; Всё приложение, КРОМЕ базы данных
Source: "D:\projects\Hijack-mme\portable\HiJack-LMS\*"; DestDir: "{app}"; Excludes: "app\backend\db.sqlite3,db.sqlite3"; Flags: recursesubdirs createallsubdirs ignoreversion
; База данных: ставится только если её ещё нет - данные пользователя переживают обновление
Source: "D:\projects\Hijack-mme\portable\HiJack-LMS\app\backend\db.sqlite3"; DestDir: "{app}\app\backend"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\launcher.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\lms.ico"; Comment: "Запустить Hi Jack LMS (сервер на 127.0.0.1:8000)"
Name: "{group}\Остановить {#MyAppName}"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\stop.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\lms.ico"; Comment: "Остановить сервер Hi Jack LMS"
Name: "{group}\Инструкция {#MyAppName}"; Filename: "{app}\README.txt"; Comment: "Как пользоваться Hi Jack LMS"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\launcher.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\lms.ico"; Tasks: desktopicon; Comment: "Запустить Hi Jack LMS"

[Run]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\launcher.pyw"""; WorkingDir: "{app}"; Description: "Запустить Hi Jack LMS"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\runtime\python\pythonw.exe"; Parameters: """{app}\stop.pyw"""; Flags: runhidden; RunOnceId: "StopHiJackServer"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}')) then
    Exec(ExpandConstant('{app}\runtime\python\pythonw.exe'),
         ExpandConstant('"{app}\stop.pyw"'), '', SW_HIDE,
         ewWaitUntilTerminated, ResultCode);
end;

function UpdateReadyMemo(Space, NewLine, MemoFileInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine +
            'Данные для входа в систему:' + NewLine +
            '  Логин (телефон): 946263200' + NewLine +
            '  Пароль: HiJack2024!' + NewLine + NewLine +
            'Адрес в браузере: http://127.0.0.1:8000' + NewLine +
            'Пароль можно изменить в настройках профиля.';
end;
