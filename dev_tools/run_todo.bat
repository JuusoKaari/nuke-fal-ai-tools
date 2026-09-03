@echo off
REM Purpose: Unattended Cursor CLI loop over a wave checklist (this checkout).
REM Stdlib Python only. Config: unattended-todo.json at repo root (or --config).
REM The checklist is required (bare names resolve under todo_lists/).
REM Examples:
REM   run_todo.bat settings_todo.md
REM   run_todo.bat settings_todo.md --dry-run
REM   run_todo.bat settings_todo.md --wave 2
REM   run_todo.bat settings_todo.md --wave all
REM   run_todo.bat settings_todo.md --only W1 --allow-dirty
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 run_todo.py %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3.10+ and try again.
  exit /b 1
)

python run_todo.py %*
exit /b %ERRORLEVEL%
