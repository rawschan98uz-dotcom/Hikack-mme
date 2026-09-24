@echo off
title HiJack LMS - Backend
cd /d "%~dp0app\backend"
set DEBUG=true
echo Starting HiJack LMS Backend on http://127.0.0.1:8000 ...
call .venv\Scripts\activate.bat
python manage.py runserver 127.0.0.1:8000
pause
