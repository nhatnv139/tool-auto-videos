# -*- coding: utf-8 -*-
"""lam_muot_kb.py — dung lai cac shot Ken Burns (anh tinh) BI GIAT trong kho
assets/stock bang renderer subpixel moi (tool/motion.kenburns).

Vi sao: truoc 13/10/2026 wiki_images._ken_burns dung ffmpeg zoompan, lam tron
x/y ve pixel nguyen moi frame -> anh zoom/pan cham bi giat (do 13/10: 224/706
shot anh). _ken_burns da sua, nhung cac shot cu la mp4 DUNG SAN nam trong cache
(ten = md5(api|keyword|idx)) nen kit khong bao gio dung lai chung, va anh goc
khong con giu (tai ve thu muc tam roi bo).

Cach lam (khong can mang): lay KHUNG DAU cua shot cu (1920x1080 — chinh la anh
goc da cat khung) lam nguon, dung lai chuyen dong moi cung do dai, zoom nhe hon
(1.0 <-> 1.10) de khong phong anh qua tay. Shot cu KHONG bi xoa: chuyen sang
assets/stock/_kb_cu/ (glob kho khong de quy nen kit khong thay no nua).
_do_muot.json khoa theo size+mtime nen tu do lai shot moi.

Dung:
    python auto\\lam_muot_kb.py            chi liet ke shot giat (khong sua gi)
    python auto\\lam_muot_kb.py --that     dung lai + sao luu shot cu
    python auto\\lam_muot_kb.py --that --jobs 4
"""
import argparse
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "tool"))

import motion  # noqa: E402
import stock as ST  # noqa: E402


def _dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def lam_lai(path, bak_dir, tmp_dir):
    """Dung lai 1 shot. -> (path, diem_truoc, diem_sau) hoac raise."""
    name = os.path.basename(path)
    dur = _dur(path)
    if dur <= 0.5:
        raise RuntimeError("khong doc duoc do dai")
    png = os.path.join(tmp_dir, name + ".png")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-frames:v", "1",
                        png], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(png):
        raise RuntimeError("khong lay duoc khung dau: " + r.stderr[-200:])
    idx = int(hashlib.md5(name.encode()).hexdigest()[:4], 16)
    new = os.path.join(os.path.dirname(path), name[:-4] + ".kbnew.tmp")
    # eq da nam san trong khung cu (grade nhe) -> khong grade lan hai
    motion.kenburns(png, new + ".mp4", round(dur, 3), idx=idx, z0=1.0, z1=1.10,
                    vf=None)
    os.replace(new + ".mp4", new)
    os.remove(png)
    os.makedirs(bak_dir, exist_ok=True)
    shutil.move(path, os.path.join(bak_dir, name))
    os.replace(new, path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--that", action="store_true", help="dung lai that (mac dinh chi liet ke)")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--sao-luu", default=None, dest="sao_luu",
                    help="thu muc cat shot cu (mac dinh assets/stock/_kb_cu; "
                         "o D day thi tro sang o C)")
    a = ap.parse_args()

    d = ST._stock_dir(KIT)
    files = sorted(f for f in glob.glob(os.path.join(d, "*.mp4"))
                   if not f.endswith(".shrink.mp4"))
    stills = [f for f in files if ST.is_still(KIT, f)]
    print(f"Kho {d}: {len(stills)} shot anh Ken Burns. Do do muot ...")
    with ThreadPoolExecutor(max(2, a.jobs * 2)) as ex:
        res = list(ex.map(ST.do_muot, stills))
    giat = [(f, r) for f, r in zip(stills, res) if ST.giat_theo_diem(r)]
    print(f"Giat: {len(giat)}/{len(stills)} "
          f"({sum(os.path.getsize(f) for f, _ in giat) / 1e6:.0f} MB)")
    if not a.that:
        for f, r in giat[:15]:
            print(f"  {os.path.basename(f)}  diem {r['diem']:.2f}")
        print("(chua sua — them --that de dung lai)")
        return
    bak = a.sao_luu or os.path.join(d, "_kb_cu")
    tmp = tempfile.mkdtemp(prefix="kbfix-")
    t0 = time.time()
    ok, loi = [], []

    def one(item):
        f, r = item
        try:
            lam_lai(f, bak, tmp)
            r2 = ST.do_muot(f)
            ok.append((f, r["diem"], (r2 or {}).get("diem")))
        except Exception as e:  # noqa: BLE001
            loi.append((f, str(e)[:160]))

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, giat))
    shutil.rmtree(tmp, ignore_errors=True)
    con_giat = [x for x in ok if x[2] is not None and x[2] >= ST.GIAT_NGUONG]
    tb_truoc = sum(x[1] for x in ok) / max(1, len(ok))
    tb_sau = sum((x[2] or 0) for x in ok) / max(1, len(ok))
    print(f"Dung lai {len(ok)} shot trong {time.time() - t0:.0f}s, loi {len(loi)}. "
          f"Diem giat TB {tb_truoc:.3f} -> {tb_sau:.3f}; con >= nguong: {len(con_giat)}")
    print(f"Shot cu sao luu o {bak} (xoa thu muc nay khi da xem on).")
    for f, e in loi[:10]:
        print(f"  LOI {os.path.basename(f)}: {e}")


if __name__ == "__main__":
    main()
