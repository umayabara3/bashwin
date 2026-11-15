@echo off
rem Convenience launcher for interactive use on a developer PC.
rem From a job scheduler, call python.exe directly instead of this file:
rem   python.exe <this folder>\dist\bashwin.pyz <script.sh> [args...]
python "%~dp0dist\bashwin.pyz" %*
exit /b %ERRORLEVEL%
