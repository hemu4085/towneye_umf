@echo off
setlocal
REM One-step offline bundle: mirror repo + Windows-native wheels under C:\aiops.
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0prepare_offline_bundle.ps1" -Root "C:\aiops" %*
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" echo FAILED exit=%ERR% >&2
exit /b %ERR%
