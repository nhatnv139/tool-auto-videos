# -*- coding: utf-8 -*-
"""quet_stock_giat.py — quet kho assets/stock, tim clip VIDEO giat, ghi danh
sach den assets/stock/_giat_den.json de kit bo qua (stock.stock_files /
stock_pool doc file nay). KHONG xoa, KHONG sua file media nao.

Do muot: stock.do_muot — giai ma ~4s giua clip o nhip goc, xam 192x108, ti le
khung "bat thuong" (gan trung khung truoc hoac nhay coc so voi trung vi truot).
Giat = diem >= stock.GIAT_NGUONG (mac dinh 0.11, env STOCK_GIAT_NGUONG) VA
nhip bat thuong lap deu (chu_ky >= 0.3) hoac >= 5% khung dung lap (dup)
(stock.giat_theo_diem).
Ket qua do duoc cache vao assets/stock/_do_muot.json (theo size+mtime), chay
lai chi do file moi.

Shot Ken Burns tu anh (khong co trong _urls.json) khong vao danh sach den —
chi thong ke rieng khi --ca-anh (giat do zoompan, sua o buoc dung shot).

Dung:
    python auto\\quet_stock_giat.py               quet + ghi _giat_den.json
    python auto\\quet_stock_giat.py --xem         chi in, khong ghi danh sach den
    python auto\\quet_stock_giat.py --ca-anh      do ca shot Ken Burns (bao cao)
    python auto\\quet_stock_giat.py --jobs 8      so luong song song
"""
import argparse
import glob
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "tool"))

import stock as ST  # noqa: E402


def _mb(n):
    return n / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xem", action="store_true", help="khong ghi danh sach den")
    ap.add_argument("--ca-anh", action="store_true", help="do ca shot Ken Burns")
    ap.add_argument("--jobs", type=int,
                    default=max(2, min(10, (os.cpu_count() or 8) - 2)))
    ap.add_argument("--nguong", type=float, default=ST.GIAT_NGUONG)
    a = ap.parse_args()

    d = ST._stock_dir(KIT)
    files = sorted(glob.glob(os.path.join(d, "*.mp4")))
    files = [f for f in files if not f.endswith(".shrink.mp4")]
    vids = [f for f in files if not ST.is_still(KIT, f)]
    stills = [f for f in files if f not in set(vids)]
    todo = vids + (stills if a.ca_anh else [])
    print(f"Kho {d}: {len(files)} mp4 ({len(vids)} clip video, "
          f"{len(stills)} shot anh). Do {len(todo)} file, {a.jobs} luong...")

    t0 = time.time()
    done = [0]

    def _one(f):
        r = ST.muot_of(f)
        done[0] += 1
        if done[0] % 200 == 0:
            print(f"  {done[0]}/{len(todo)}  ({time.time() - t0:.0f}s)")
        return f, r

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(_one, todo))
    ST.save_muot(d=d)
    print(f"Do xong trong {time.time() - t0:.0f}s")

    urls = {}
    try:
        with open(os.path.join(d, "_urls.json"), encoding="utf-8") as fh:
            urls = {v: k for k, v in json.load(fh).items()}
    except Exception:
        pass

    still_set = set(stills)
    giat, giat_anh, loi = {}, [], []
    sz_giat = 0
    for f, r in res:
        if not r:
            loi.append(f)
            continue
        if not ST.giat_theo_diem(r, a.nguong):
            continue
        name = os.path.basename(f)
        if f in still_set:
            giat_anh.append((name, r["diem"]))
            continue
        size = os.path.getsize(f)
        sz_giat += size
        giat[name] = {"diem": r["diem"], "chu_ky": r.get("chu_ky"),
                      "dup": r.get("dup"), "jud": r.get("jud"),
                      "fps": r.get("fps"), "size": size, "url": urls.get(name, "")}

    n_vid = sum(1 for f, r in res if r and f not in still_set)
    sz_all = sum(os.path.getsize(f) for f in vids)
    print(f"\nNguong {a.nguong}: {len(giat)}/{n_vid} clip video GIAT, "
          f"{_mb(sz_giat):.0f} MB / {_mb(sz_all):.0f} MB clip video")
    by_fps = {}
    for v in giat.values():
        k = round(v["fps"] or 0, 2)
        by_fps[k] = by_fps.get(k, 0) + 1
    print("  theo fps file:", ", ".join(f"{k}fps x{n}" for k, n in sorted(by_fps.items())))
    for name, v in sorted(giat.items(), key=lambda kv: -kv[1]["diem"])[:15]:
        print(f"  {name}  diem {v['diem']:.2f} chu_ky {v['chu_ky']}  {v['fps']}fps  {v['url'][-50:]}")
    if a.ca_anh:
        print(f"Shot Ken Burns giat (KHONG dua vao danh sach den): "
              f"{len(giat_anh)}/{len(stills)}")
    if loi:
        print(f"Khong do duoc: {len(loi)} file (giu nguyen, khong loai)")

    if a.xem:
        print("\n--xem: khong ghi danh sach den.")
        return
    out = os.path.join(d, ST.GIAT_FILE)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"nguong": a.nguong, "ngay": time.strftime("%Y-%m-%d %H:%M"),
                   "so_clip": len(giat), "mb": round(_mb(sz_giat), 1),
                   "files": giat}, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, out)
    print(f"\nDa ghi {out} ({len(giat)} clip). Khong xoa file nao.")


if __name__ == "__main__":
    main()
