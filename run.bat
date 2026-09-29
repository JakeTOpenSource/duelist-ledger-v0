@echo off
rem Duelist Ledger v0: double-click to run the tests and all scenarios.
set PYTHONUTF8=1
cd /d "%~dp0"
py -3.14 run.py %*
set RC=%ERRORLEVEL%
if "%~1"=="" pause
exit /b %RC%
