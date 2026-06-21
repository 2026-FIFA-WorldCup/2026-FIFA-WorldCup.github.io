@echo off
powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File "D:\DESKTOP\fifa\scripts\sync_sporttery_to_github.ps1"
exit /b %ERRORLEVEL%
