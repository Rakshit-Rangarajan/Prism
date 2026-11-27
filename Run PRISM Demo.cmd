@echo off
title PRISM - One-click Demo
powershell.exe -NoProfile -File "%~dp0scripts\demo-one-click.ps1" %*
if errorlevel 1 (
    echo.
    echo PRISM could not complete the demo. Check the run folder shown above.
    pause
    exit /b 1
)
