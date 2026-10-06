@echo off
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%venv\Scripts\python.exe" (
  echo DiskWala Downloader is not installed. See README.md in %ROOT%
  exit /b 1
)
"%ROOT%venv\Scripts\python.exe" -m diskwala_downloader %*
exit /b %ERRORLEVEL%
