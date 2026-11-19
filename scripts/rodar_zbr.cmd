@echo off
rem Lancador da tarefa semanal da lista de ZBR. 1o argumento: python a usar (o agendar_zbr.ps1 passa).
cd /d "%~dp0.."
if not exist logs mkdir logs
set PY=%~1
if "%PY%"=="" set PY=.venv\Scripts\python.exe
echo ===== %date% %time% atualizar_zbr (python: %PY%) >> logs\tarefa_zbr.log
"%PY%" -I scripts\atualizar_zbr.py >> logs\tarefa_zbr.log 2>&1
set RC=%ERRORLEVEL%
echo ===== fim rc=%RC% >> logs\tarefa_zbr.log
exit /b %RC%
