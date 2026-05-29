@echo off
chcp 65001 > nul
:: 设置 Python 输出 UTF-8 编码，防止 emoji 日志崩溃
set PYTHONIOENCODING=utf-8
set PYTHONLEGACYWINDOWSSTDIO=utf-8
:: 设置 Git SSH 密钥路径
set GIT_SSH_COMMAND=ssh -i "%USERPROFILE%\.ssh\id_rsa"

:: 自动定位到脚本所在目录
cd /d "%~dp0"

:: 优先用本文件夹内自带的 Python
if exist "%~dp0python\python.exe" (
    set "PYTHON=%~dp0python\python.exe"
) else (
    set "PYTHON=python"
)

:: 记录开始时间
echo [%date% %time%] ====== 开始更新 ====== >> update.log 2>&1

:: 运行抓取脚本
"%PYTHON%" "%~dp0pyro_daily_update.py" >> "%~dp0update.log" 2>&1

:: Git 提交并推送
git add data/ index.html CNAME
git diff --cached --quiet || (
    git commit -m "chore: daily update %date:~0,10%"
    git push
)
echo [%date% %time%] ====== 更新完成 ====== >> update.log 2>&1
