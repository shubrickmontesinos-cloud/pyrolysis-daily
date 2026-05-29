@echo off
chcp 65001 > nul
echo Registering pyrolysis weekly update task...

schtasks /create /tn "pyro-weekly" /tr "C:\Users\78333\pyrolysis-daily\run_update.bat" /sc WEEKLY /d MON /st 11:00 /f /rl HIGHEST

if %errorlevel% equ 0 (
    echo.
    echo [OK] Task registered!
    echo Name: pyro-weekly
    echo Schedule: Every Monday at 11:00
) else (
    echo.
    echo [FAILED] Try running as Administrator.
)

pause
