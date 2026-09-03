@echo off
setlocal
cd /d "%~dp0"
python research_cli.py %*
endlocal
