@echo off
setlocal
REM One-step offline bundle: mirror repo + Linux wheels under C:\aiops (WSL pip).
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare_offline_bundle.ps1" -Root "C:\aiops" -UseWslPython %*
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" echo FAILED exit=%ERR% >&2
exit /b %ERR%
