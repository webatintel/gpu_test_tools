
@echo off
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUNBUFFERED=1
python "%~dp0..\build_chrome.py" %*
