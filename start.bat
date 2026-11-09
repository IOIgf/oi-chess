@echo off
set "PYTHONIOENCODING=utf-8:replace"
cd /d "%~dp0"

rem ===== Update check proxy choice (first run asks once, saves to update_config.bat) =====
rem Re-run the choice any time:  start.bat setup
if "%~1"=="setup" (
  del update_config.bat >nul 2>nul
  goto askproxy
)
if defined OI_CHESS_SKIP_UPDATE goto runcheck
if exist update_config.bat (
  call update_config.bat
  goto runcheck
)
:askproxy
echo === Update check: how should this PC reach GitHub? ===
echo   1 = direct connection ^(default^)
echo   2 = use a proxy, e.g. http://127.0.0.1:7890
choice /c 12 /n /m "Select [1/2]: "
if errorlevel 2 goto useproxy
> update_config.bat echo rem direct connection
goto runcheck
:useproxy
set "OI_PROXY_URL=http://127.0.0.1:7890"
set /p "OI_PROXY_URL=Proxy URL (press Enter for default): "
> update_config.bat echo set "OI_CHESS_PROXY=%OI_PROXY_URL%"
call update_config.bat
:runcheck

where py >nul 2>nul
if not errorlevel 1 (
  py -3 check_update.py
  py -3 server.py
) else (
  python -c "import sys; sys.exit(0 if sys.version_info.major == 3 else 1)"
  if errorlevel 1 (
    echo Python 3 is required. Install Python 3 and try again.
    pause
    exit /b 1
  )
  python check_update.py
  python server.py
)
pause
