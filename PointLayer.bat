@echo off
setlocal
cd /d "%~dp0"
title PointLayer 2.1
echo Starting Ready to Fly - on an older PC this first step can take a few minutes, please wait...
echo (Windows Defender may check the files first and slow the PC. That is normal - do not close this window.)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0System Files\Ready_To_Fly.ps1" -Folder "%~dp0System Files" -Tool "PointLayer" -NeedTk
if errorlevel 1 goto rtf_stopped
set "PYEXE="
set /p PYEXE=<"%~dp0System Files\python_path.txt"
if not defined PYEXE goto rtf_stopped
"%PYEXE%" "System Files\PointLayer.py"
if errorlevel 1 pause
exit /b 0

:rtf_stopped
echo.
echo PointLayer did not start - read the message above.
echo A log is in System Files\Ready_To_Fly_log.txt
pause
exit /b 1
