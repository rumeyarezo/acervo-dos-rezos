@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath(Startup) + \Acervo - fila de acordes.lnk); $s.TargetPath=%~dp0iniciar-fila.bat; $s.WorkingDirectory=%~dp0; $s.WindowStyle=7; $s.Save()"
if errorlevel 1 (echo Nao consegui criar o atalho. & pause & exit /b 1)
echo Pronto: a fila vai abrir minimizada sempre que voce entrar no Windows.
echo Para desfazer, rode o nao-iniciar-com-o-windows.bat.
pause
