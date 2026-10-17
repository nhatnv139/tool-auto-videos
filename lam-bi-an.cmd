@echo off
REM lam-bi-an.cmd - loat 10 bi an su Viet (08/10/2026), chay trong cua so rieng.
REM Chi dung bai co videos\<slug>\.san_sang; cho RAM >= 5 GB (thieu thi doi 10 phut);
REM dung -> thumbnail -> dang hen gio 20:00 noi tiep lich -> xoa video/build.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python auto\loat_su_viet.py le-chi-vien-ai-giet-vua mac-dang-dung-trieu-dai-bi-xoa-ten le-long-dinh-ngoa-trieu bi-an-mo-quang-trung kho-vang-tan-so vua-duy-tan-roi-may-bay tu-duc-khong-con ly-cong-uan-dua-tre-khong-cha y-lan-co-gai-hai-dau no-than-co-loa-co-that
echo [lam-bi-an] XONG
pause
