@echo off
REM ---------------------------------------------------------------------------
REM Starts the web front end on this computer, for dictating from a phone.
REM
REM It listens on localhost only; Tailscale is what makes it reachable from
REM the phone (see "Use it from your phone" in the README). Double-click to
REM run it in a window, or point a Task Scheduler "at log on" task at it so
REM it is always up when the PC is.
REM ---------------------------------------------------------------------------

cd /d "%~dp0\.."
python -m webapp
pause
