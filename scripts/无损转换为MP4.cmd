@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "TASK_PYTHON="
set "TASK_PY_ARGS="
python -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
if not errorlevel 1 set "TASK_PYTHON=python"
if defined TASK_PYTHON goto run
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
if not errorlevel 1 set "TASK_PYTHON=py"
if defined TASK_PYTHON set "TASK_PY_ARGS=-3"
if defined TASK_PYTHON goto run
echo 需要 Python 3.9 或更新版本，请先安装 Python。
pause
exit /b 2
:run
if "%~1"=="" (
  "%TASK_PYTHON%" %TASK_PY_ARGS% "%~dp0lossless_to_mp4.py" "%~dp0."
) else (
  "%TASK_PYTHON%" %TASK_PY_ARGS% "%~dp0lossless_to_mp4.py" %*
)
set "TASK_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %TASK_EXIT%
