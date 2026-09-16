@echo off
chcp 65001 >nul
title Gundem Takip
cd /d "%~dp0"

set PY=
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3
if not defined PY (
  where python >nul 2>nul
  if %errorlevel%==0 set PY=python
)

if not defined PY (
  echo.
  echo  Python bulunamadi. Bir kez kurmak yeterli:
  echo.
  echo    winget install -e --id Python.Python.3.12
  echo.
  echo  ya da https://www.python.org/downloads/ adresinden indir.
  echo  Kurulumda "Add python.exe to PATH" secenegini isaretle.
  echo.
  pause
  exit /b 1
)

echo.
echo  Gundem Takip baslatiliyor. Tarama birkac dakika surebilir.
echo  Tarayici kendiliginden acilir; kapatmak icin bu pencerede Ctrl+C.
echo.
%PY% scripts\serve.py %*
echo.
pause
