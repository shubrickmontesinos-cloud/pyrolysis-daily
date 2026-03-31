@echo off
chcp 65001 > nul
:: %~dp0 自动获取本脚本所在目录，U盘拷贝到任何路径都能用
set "PROJECT_DIR=%~dp0"
:: 去掉末尾反斜杠
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo 项目目录：%PROJECT_DIR%
echo 正在注册热解日报每日更新任务...

:: 检查是否有自带 Python，否则提示安装
if exist "%PROJECT_DIR%\python\python.exe" (
    echo [Python] 使用项目自带 Python，无需系统安装
) else (
    echo [Python] 未找到自带 Python，尝试使用系统 Python...
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未检测到 Python，请先从 https://python.org 安装
        pause
        exit /b 1
    )
    echo [Python] 使用系统 Python
)

:: 注册 Windows 定时任务，每天 7:30 执行
schtasks /create ^
    /tn "热解日报每日更新" ^
    /tr "\"%PROJECT_DIR%\run_update.bat\"" ^
    /sc DAILY ^
    /st 11:00 ^
    /f ^
    /rl HIGHEST

if %errorlevel% equ 0 (
    echo.
    echo [成功] 定时任务已注册！
    echo 任务名称：热解日报每日更新
    echo 执行时间：每天 11:00
    echo 日志文件：%PROJECT_DIR%\update.log
    echo.
    echo 你可以在「任务计划程序」中查看和管理此任务。
) else (
    echo [错误] 定时任务注册失败，请右键以管理员身份运行此脚本。
)

pause

