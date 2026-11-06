@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "System Files\PointLayer.py"
) else (
    python "System Files\PointLayer.py"
)
if errorlevel 1 pause
