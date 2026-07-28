@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_mcp_server.ps1" %*
exit /b %errorlevel%
