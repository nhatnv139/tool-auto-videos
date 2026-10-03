@echo off
REM lam-di.cmd - chay hang doi video, tu chay lai neu tien trinh chet giua chung.
REM
REM    lam-di                 lam het muc chua xong trong queue.yml
REM    lam-di --only 1        chi lam 1 video dau
REM    lam-di --slug abc      chi lam muc nay
REM
REM Runner co resume: chay lai thi no di tiep tu buoc dang do, khong lam lai tu dau.
setlocal
cd /d "%~dp0"
set LAN=0
:lap
set /a LAN+=1
python auto\runner.py %*
if %ERRORLEVEL% EQU 0 goto xong
if %LAN% GEQ 5 goto het
echo.
echo [lam-di] lan %LAN% dut (ma %ERRORLEVEL%) - chay tiep sau 10 giay...
timeout /t 10 /nobreak >nul
goto lap

:het
echo [lam-di] da thu %LAN% lan van khong xong - xem auto\logs\
exit /b 1

:xong
echo [lam-di] xong.
exit /b 0
