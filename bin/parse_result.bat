
@echo off
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUNBUFFERED=1
python "%~dp0..\parse_result.py" %*
