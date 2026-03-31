@echo off
chcp 65001 > nul
:: 自动定位到脚本所在目录，U盘拷贝到任何电脑都能用
cd /d "%~dp0"

:: 优先用本文件夹内自带的 Python（用绝对路径，确保定时任务后台运行时也能找到）
if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
) else (
    set "PYTHON=python"
)

"%PYTHON%" "%~dp0pyro_daily_update.py" >> "%~dp0update.log" 2>&1
