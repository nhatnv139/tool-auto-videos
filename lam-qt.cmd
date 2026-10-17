@echo off
REM lam-qt.cmd - dung lai Quang Trung tu buoc images (build cu da bi don).
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python auto\runner.py --slug quang-trung-than-toc --from images >> auto\logs\run_quang-trung-than-toc.log 2>&1
call "%~dp0lam-di.cmd" --slug quang-trung-than-toc >> auto\logs\run_quang-trung-than-toc.log 2>&1
echo [lam-qt] XONG %TIME%
