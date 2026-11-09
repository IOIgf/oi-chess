@echo off
cd /d "%~dp0"
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
