@echo off
REM lam-hql.cmd - dung lai Ho Quy Ly tu buoc images voi bo loc anh moi (05/10).
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python auto\runner.py --slug ho-quy-ly-mat-nuoc --from images >> auto\logs\run_ho-quy-ly-mat-nuoc.log 2>&1
call "%~dp0lam-di.cmd" --slug ho-quy-ly-mat-nuoc >> auto\logs\run_ho-quy-ly-mat-nuoc.log 2>&1
echo [lam-hql] XONG %TIME%
