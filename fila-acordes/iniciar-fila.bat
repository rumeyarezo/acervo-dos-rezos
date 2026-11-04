@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Acervo dos Rezos - fila de acordes
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
:loop
uv run python fila.py
echo.
echo A fila parou. Ela volta sozinha em 30 segundos. Para encerrar de vez, feche esta janela.
timeout /t 30 >nul
goto loop
