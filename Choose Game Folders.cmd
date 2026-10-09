@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0scripts\select-game-folders.ps1"
if errorlevel 1 pause
