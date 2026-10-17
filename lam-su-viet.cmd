@echo off
REM lam-su-viet.cmd - dung 3 video su Viet con do, cua so rieng (khong bi Claude Code tat khi thieu RAM).
REM Moi video chay qua lam-di (tu chay lai neu dut, resume tu buoc dang do).
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
for %%S in (ho-quy-ly-mat-nuoc quang-trung-than-toc tran-thu-do) do (
  echo ===== %%S %TIME%
  call "%~dp0lam-di.cmd" --slug %%S >> auto\logs\run_%%S.log 2>&1
  echo ----- %%S xong, ma %ERRORLEVEL%
)
echo [lam-su-viet] XONG HET %TIME%
