@echo off
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
set "RECORD=Codex工作记录"

rem Prefer the D: Anaconda installation; the Windows Store python alias is not a real interpreter.
if exist "D:\Anaconda\python.exe" set "PYTHON=D:\Anaconda\python.exe"
if not defined PYTHON (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
)
if not defined PYTHON (
    echo [错误] 未找到可用的 Python。请检查 D:\Anaconda\python.exe。
    pause
    exit /b 1
)

if not exist "%RECORD%" mkdir "%RECORD%"
set "PYINSTALLER_CONFIG_DIR=%PROJECT_DIR%%RECORD%\pyinstaller-cache"

echo 使用 Python: %PYTHON%
echo [1/3] 安装项目依赖...
"%PYTHON%" -m pip install --cache-dir "%PROJECT_DIR%%RECORD%\pip-cache" -r requirements.txt
if errorlevel 1 goto :failed

echo [2/3] 打包程序...
"%PYTHON%" -m PyInstaller --noconfirm --onefile --windowed --name "小说提取器" --distpath "%RECORD%\dist" --workpath "%RECORD%\build" --specpath "%RECORD%" src\main.py
if errorlevel 1 goto :failed

echo [3/3] 更新项目目录中的程序...
copy /Y "%RECORD%\dist\小说提取器.exe" ".\小说提取器.exe" >nul
if errorlevel 1 goto :failed

echo.
echo 打包完成: %PROJECT_DIR%小说提取器.exe
pause
exit /b 0

:failed
echo.
echo [错误] 打包未完成，请查看上方错误信息。
pause
exit /b 1
