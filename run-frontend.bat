@echo off
title HiJack LMS - Frontend
cd /d "%~dp0app\frontend"
echo Starting HiJack LMS Frontend on http://localhost:5173 ...
call npm run dev
pause
