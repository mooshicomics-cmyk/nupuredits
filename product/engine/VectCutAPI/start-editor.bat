@echo off
REM Double-click this to turn on your editing engine (Windows).
REM Keep the window it opens open while you edit. Close it when you are done.
cd /d "%~dp0"

REM Already running? Don't start a second one. But only say "you're good" when the one running is
REM THIS copy: a second copy of the engine (an old download still on) can hold the same port.
netstat -ano | findstr /R /C:"LISTENING" | findstr /C:":9001" >nul 2>&1
if %errorlevel%==0 (
  curl -s --max-time 3 http://127.0.0.1:9001/engine_home 2>nul | findstr /I /X /L /C:"%CD%" >nul 2>&1
  if not errorlevel 1 (
    echo Your editing engine is already on ^(localhost:9001^). You are good to go.
    echo You can close this window.
    pause
    exit /b 0
  )
  echo Another editing engine is already running, so this one can't start.
  echo It is from a different folder, or it is an older engine from before your latest update.
  echo.
  echo To fix it: close the engine window that is already open ^(or restart your computer^), then double-click this again.
  pause
  exit /b 1
)

REM A workspace that is missing, or there but will not load the engine's own tools, gets its setup run once,
REM right here (through Git Bash's bash, which setup needs), instead of a "not set up" and a stop.
set "VPY=venv-capcut\Scripts\python.exe"
set "REE_ROOT=%~dp0..\..\.."
set "REE_OK="
if exist "%VPY%" "%VPY%" -c "import flask, requests, json5, imageio, psutil" >nul 2>&1 && set "REE_OK=1"
if not defined REE_OK (
  where bash >nul 2>&1
  if not errorlevel 1 (
    echo The engine's workspace is not set up yet ^(or would not load^). Setting it up now, one time only...
    set "REE_SETUP_RAN=1"
    bash setup-editor-engine.sh
    if exist "%VPY%" "%VPY%" -c "import flask, requests, json5, imageio, psutil" >nul 2>&1 && set "REE_OK=1"
  )
)
if not defined REE_OK (
  echo The engine's workspace still would not load.
  echo Run /report-a-problem, or just tell Claude "set me up".
  pause
  exit /b 1
)
REM setup ran from here and it worked: one line in _local\fallbacks.log for the problem report
if defined REE_SETUP_RAN "%VPY%" "%REE_ROOT%\product\fallbacks.py" note capcut-draft "the editing engine's workspace was missing or would not load; start-editor ran its setup once" >nul 2>&1

REM config.json is the engine's port. It is not shipped, and without it the server used to fall back to port 9000
REM while every build calls 9001. Written here when missing, with the same contents setup writes.
if not exist "config.json" (
  > "config.json" echo {
  >> "config.json" echo   "draft_profile": "capcut_legacy",
  >> "config.json" echo   "is_capcut_env": true,
  >> "config.json" echo   "draft_domain": "http://localhost:9001",
  >> "config.json" echo   "port": 9001,
  >> "config.json" echo   "preview_router": "/draft/downloader",
  >> "config.json" echo   "is_upload_draft": false
  >> "config.json" echo }
  "%VPY%" "%REE_ROOT%\product\fallbacks.py" note capcut-draft "the editing engine had no config.json; wrote the standard one (port 9001)" >nul 2>&1
)

REM Windows console is not UTF-8 by default; without this the server's status output can crash.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo Starting your editing engine...
echo Keep this window open while you edit. You'll see 'Running on ... 9001' when it's ready.
echo.
"venv-capcut\Scripts\python.exe" capcut_server.py
pause
