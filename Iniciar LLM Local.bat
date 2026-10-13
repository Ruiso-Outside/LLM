@echo off
chcp 65001 >nul
cd /d "%~dp0"
title LLM Local
where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em https://www.python.org/downloads/ marcando "Add to PATH".
  pause
  exit /b 1
)
python app\server.py %*
if errorlevel 1 pause
