@echo off
rem Lancador da vigia (tarefa "GestaoUsuarios-Vigia", ao fazer logon).
rem 1o argumento: python a usar; 2o (opcional): --executar. Saida em logs\vigia_console.log (o log principal e logs\AAAA-MM-DD.log).
cd /d "%~dp0.."
if not exist logs mkdir logs
set PY=%~1
if "%PY%"=="" set PY=.venv\Scripts\python.exe
set PYTHONPATH=%CD%\src
echo ===== %date% %time% vigia (python: %PY%) %2 >> logs\vigia_console.log
"%PY%" -m gestao_usuarios vigiar %2 >> logs\vigia_console.log 2>&1
set RC=%ERRORLEVEL%
echo ===== vigia terminou rc=%RC% >> logs\vigia_console.log
exit /b %RC%
