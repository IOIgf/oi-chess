@echo off
set "PYTHONIOENCODING=utf-8:replace"
cd /d "%~dp0"

rem ==============================================================
rem  Step 1: network choice for update check / auto update
rem  Asked on EVERY launch. Press Enter to reuse the last choice.
rem  Re-choose any time:  start.bat setup
rem ==============================================================
if "%~1"=="setup" (
  del update_config.bat >nul 2>nul
  goto askproxy
)

if defined OI_CHESS_SKIP_UPDATE goto runupdate

rem Load the saved choice so we can show it as the default.
set "OI_SAVED_MODE="
set "OI_SAVED_PROXY="
if exist update_config.bat call update_config.bat
if defined OI_CHESS_PROXY_MODE set "OI_SAVED_MODE=%OI_CHESS_PROXY_MODE%"
if defined OI_CHESS_PROXY set "OI_SAVED_PROXY=%OI_CHESS_PROXY%"

:askproxy
echo === Update check: how should this PC reach GitHub? ===
if defined OI_SAVED_MODE (
  if "%OI_SAVED_MODE%"=="proxy" echo   Last choice: proxy %OI_SAVED_PROXY%
  if not "%OI_SAVED_MODE%"=="proxy" echo   Last choice: direct connection
  echo   1 = reuse last choice ^(default^)
  echo   2 = direct connection
  echo   3 = use a proxy, e.g. http://127.0.0.1:7890
  choice /c 123 /n /m "Select [1/2/3, Enter=reuse last]: "
  if errorlevel 3 goto useproxy
  if errorlevel 2 goto direct
  goto runupdate
)
echo   1 = direct connection ^(default^)
echo   2 = use a proxy, e.g. http://127.0.0.1:7890
choice /c 12 /n /m "Select [1/2]: "
if errorlevel 2 goto useproxy
:direct
set "OI_CHESS_PROXY="
set "OI_CHESS_PROXY_MODE=direct"
> update_config.bat echo set "OI_CHESS_PROXY_MODE=direct"
>> update_config.bat echo set "OI_CHESS_PROXY="
goto runupdate

:useproxy
set "OI_PROXY_URL=http://127.0.0.1:7890"
set /p "OI_PROXY_URL=Proxy URL (press Enter for default): "
set "OI_CHESS_PROXY=%OI_PROXY_URL%"
set "OI_CHESS_PROXY_MODE=proxy"
> update_config.bat echo set "OI_CHESS_PROXY_MODE=proxy"
>> update_config.bat echo set "OI_CHESS_PROXY=%OI_CHESS_PROXY%"
goto runupdate

rem ==============================================================
rem  Step 2: check for a new release and install it automatically.
rem  Player saves under data\ are never overwritten.
rem ==============================================================
:runupdate
where py >nul 2>nul
if not errorlevel 1 (
  py -3 auto_update.py
  py -3 server.py
) else (
  python -c "import sys; sys.exit(0 if sys.version_info.major == 3 else 1)"
  if errorlevel 1 (
    echo Python 3 is required. Install Python 3 and try again.
    pause
    exit /b 1
  )
  python auto_update.py
  python server.py
)
pause
