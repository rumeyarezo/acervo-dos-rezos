@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Acervo dos Rezos - instalando a fila de acordes
echo.
echo === Acervo dos Rezos: instalando a fila de acordes ===
echo.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo [1/4] Instalando o uv, o gerenciador de Python...
  powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)
where uv >nul 2>nul
if errorlevel 1 (
  echo Nao consegui instalar o uv. Veja o LEIA-ME.md.
  pause
  exit /b 1
)
echo [1/4] uv ok.
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [2/4] Instalando o ffmpeg pelo winget...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  echo.
  echo O ffmpeg foi instalado agora. FECHE esta janela e rode o instalar.bat de novo
  echo para o Windows reconhecer o ffmpeg.
  pause
  exit /b 0
)
echo [2/4] ffmpeg ok.
echo [3/4] Instalando o motor de acordes (cerca de 600 MB na primeira vez)...
uv sync --python 3.12
if errorlevel 1 (
  echo Falhou a instalacao do motor. Veja o LEIA-ME.md.
  pause
  exit /b 1
)
uv run python -c "from chordotomy.cli import app; app()" fetch-weights
if errorlevel 1 (
  echo Falhou o download dos pesos do Beat This!. Confira a internet e rode de novo.
  pause
  exit /b 1
)
echo [4/4] Motor pronto.
if not exist config.env (
  copy config.exemplo.env config.env >nul
  echo.
  echo Abrindo o config.env: cole a chave service_role do Supabase, salve e feche.
  notepad config.env
)
echo.
echo Tudo pronto! Para ligar a fila, abra o iniciar-fila.bat.
echo Para ela abrir sozinha com o Windows, rode o iniciar-com-o-windows.bat.
pause
