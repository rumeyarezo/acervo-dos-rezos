@echo off
chcp 65001 >nul
powershell -NoProfile -Command "Remove-Item -ErrorAction SilentlyContinue ([Environment]::GetFolderPath(Startup) + \Acervo - fila de acordes.lnk)"
echo A fila nao vai mais abrir sozinha com o Windows.
pause
