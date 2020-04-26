
@echo off
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUNBUFFERED=1
python3 "%~dp0..\check_tryjob.py" %*
