@echo off
cd /d "%~dp0"
set "HF_HOME=%CD%\model_cache\hf_home"
set "HF_HUB_OFFLINE=1"
set "NO_PROXY=127.0.0.1,localhost,::1"
set "PYTHONIOENCODING=utf-8"
echo Starting PDF Translator Tool. Your browser will open http://127.0.0.1:7860
echo Close this window to quit the tool.
"python\python.exe" "app\pdf2zh_gui_cn.py"
pause