@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_mcp_server.ps1" %*
exit /b %errorlevel%
