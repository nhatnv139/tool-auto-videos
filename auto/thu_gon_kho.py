# -*- coding: utf-8 -*-
"""thu_gon_kho.py — thu gon assets/stock TAI CHO, giu nguyen ten file (hash).

Do 01/10/2026: kho 21,5 GB / 2347 file. File to nhat 282 MB cho 55s 1080p
(~41 Mbps); shot Ken Burns ultrafast 26-66 MB cho 9s; co file trung het tung
byte (151550605 byte x2). Trong khi render chi dung 6-9s moi file va encode lai
crf14 o 24 fps.

Ba luat, theo thu tu:
  1. Trung lap: file giong het tung byte (cung size + md5), hoac cung content
     hash 3 frame + cung do dai + cung khung -> giu MOT ban, cac ten con lai
     thanh HARDLINK toi ban do (render van mo duoc bang ten cu, dia chi ton 1 lan).
  2. Thu gon: file > 1080p, dai > 20s hoac > 7 Mbps -> cat 18s giua, 1920x1080
     24fps, x264 veryfast crf22 tran 5 Mbps, bo tieng (stock.shrink_clip).
  3. Tran kho STOCK_CACHE_GB (mac dinh 6): vuot thi xoa file atime cu nhat
     (render ghi atime khi chon file — stock.touch_used). File cua case CHUA
     XONG (chua co video trong OUTBOX va shot chua du) duoc bao ve.

Dung:
    python auto\\thu_gon_kho.py                   xem truoc, khong dong gi
    python auto\\thu_gon_kho.py --gioi-han 20     chi xu ly 20 file (thu an toan)
    python auto\\thu_gon_kho.py --that            lam that
    python auto\\thu_gon_kho.py --that --tran 8   tran 8 GB thay vi 6
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "tool"))

import stock as ST  # noqa: E402


def _md5(p, chunk=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def case_dang_do():
    """Case co config.json ma chua xong: chua co video trong OUTBOX va shot
    chua du so cell -> file stock cua no con can de render."""
    out = []
    outbox = os.path.join(KIT, "OUTBOX")
    xong = set()
    if os.path.isdir(outbox):
        for d in os.listdir(outbox):
            if os.path.exists(os.path.join(outbox, d, "video.mp4")):
                xong.add(d.split("-", 3)[-1] if d[:4].isdigit() else d)
    for cp in glob.glob(os.path.join(KIT, "videos", "*", "config.json")):
        root = os.path.dirname(cp)
        slug = os.path.basename(root)
        if slug in xong or slug.startswith("_"):
            continue
        try:
            with open(cp, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            continue
        n_cell = len(cfg.get("cells", []))
        shots = glob.glob(os.path.join(root, "build", "shots", "cell-*.mp4"))
        if len(shots) >= n_cell and n_cell:
            continue          # da render du shot -> assemble khong can kho
        out.append((root, cfg))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--that", action="store_true", help="lam that")
    ap.add_argument("--gioi-han", type=int, default=0,
                    help="chi xu ly N file dau (thu an toan)")
    ap.add_argument("--tran", type=float, default=None,
                    help="tran kho GB (mac dinh STOCK_CACHE_GB hoac 6)")
    ap.add_argument("--luong", type=int, default=3)
    a = ap.parse_args()

    d = ST._stock_dir(KIT)
    files = sorted(os.path.join(d, f) for f in os.listdir(d)
                   if f.endswith(".mp4") and not f.endswith(".shrink.mp4"))
    if a.gioi_han:
        # file to truoc: thu tren nhom ton cho nhat
        files = sorted(files, key=os.path.getsize, reverse=True)[:a.gioi_han]
    t0 = time.monotonic()

    def inode(p):
        st = os.stat(p)
        return (st.st_dev, st.st_ino)

    truoc = sum(os.path.getsize(p) for p in
                {inode(p): p for p in files}.values())
    print(f"kho: {len(files)} file, {truoc / 1e9:.2f} GB, "
          f"TB {truoc / max(1, len(files)) / 1e6:.1f} MB/file")

    # --- 1. trung lap ---------------------------------------------------
    by_size = {}
    for p in files:
        by_size.setdefault(os.path.getsize(p), []).append(p)
    groups = []           # [giu, [ten thanh hardlink]]
    da_nhom = set()
    for size, lst in by_size.items():
        if len(lst) < 2:
            continue
        uniq = {}                       # ten da hardlink san thi bo qua
        for p in lst:
            uniq.setdefault(inode(p), p)
        if len(uniq) < 2:
            continue
        by_md5 = {}
        for p in uniq.values():
            by_md5.setdefault(_md5(p), []).append(p)
        for same in by_md5.values():
            if len(same) >= 2:
                groups.append([same[0], same[1:]])
                da_nhom.update(same)
    n_byte = len(groups)
    # cung content hash + cung do dai + cung khung (hai lan tai cung mot clip
    # nhung byte khac nhau vi CDN tra ban khac)
    try:
        from probe import duration, streams
    except Exception:
        duration = streams = None
    by_c = {}
    for p in files:
        if p in da_nhom or not os.path.exists(p + ".h"):
            continue       # chi dung hash da cache — khong ffmpeg 2000 file
        h = ST._content_hash(p)
        if h:
            by_c.setdefault(h, []).append(p)
    for h, lst in by_c.items():
        if len(lst) < 2 or not duration:
            continue
        sig = {}
        for p in lst:
            try:
                v = streams(p).get("video") or {}
                k = (round(duration(p), 1), v.get("w"), v.get("h"))
            except (SystemExit, Exception):
                continue
            sig.setdefault(k, []).append(p)
        for k, same in sig.items():
            if len(same) >= 2:
                groups.append([same[0], same[1:]])
                da_nhom.update(same)
    n_dup = sum(len(g[1]) for g in groups)
    mb_dup = sum(os.path.getsize(x) for g in groups for x in g[1]
                 if inode(x) != inode(g[0])) / 1e6
    print(f"1. trung lap: {len(groups)} nhom ({n_byte} giong tung byte), "
          f"{n_dup} ten se thanh hardlink (~{mb_dup:.0f} MB)")

    # --- 2. thu gon -----------------------------------------------------
    link_to = {x: g[0] for g in groups for x in g[1]}
    reps = [p for p in files if p not in link_to]
    can = []
    for i, p in enumerate(reps):
        if i and i % 400 == 0:
            print(f"   ...probe {i}/{len(reps)}", flush=True)
        need, dur, h = ST.needs_shrink(p)
        if need:
            can.append((p, dur))
    mb_can = sum(os.path.getsize(p) for p, _d in can) / 1e6
    # uoc: 5 Mbps tran, thuc te do 01/10 ra 0,2-0,65 MB/s
    uoc = sum(min(os.path.getsize(p), min(d, ST.SHRINK_MAX_SEC) * 0.55e6)
              for p, d in can) / 1e6
    print(f"2. thu gon: {len(can)} file ({mb_can:.0f} MB) -> uoc ~{uoc:.0f} MB")

    if not a.that:
        sau_uoc = truoc / 1e6 - mb_dup - mb_can + uoc
        print(f"(xem truoc) sau buoc 1-2 uoc ~{sau_uoc / 1e3:.2f} GB")
        bv = set()
        for root, cfg in case_dang_do():
            bv |= ST.files_of_config(root, cfg)
        tran = a.tran or float(os.environ.get("STOCK_CACHE_GB",
                                              ST.CACHE_GB_DEFAULT))
        print(f"3. tran kho {tran:g} GB: bao ve "
              f"{len([f for f in files if f in bv])} file cua case dang do; "
              + (f"se xoa them ~{sau_uoc / 1e3 - tran:.2f} GB file LRU"
                 if sau_uoc / 1e3 > tran else "khong phai xoa LRU"))
        print("Chay lai voi --that de lam that.")
        return

    # lam that: thu gon ban giu truoc, roi moi hardlink (hardlink roi moi encode
    # thi os.replace chi thay mot ten, cac ten kia van tro inode cu to).
    done = {"n": 0, "old": 0, "new": 0, "fail": 0}

    def one(item):
        p, _d = item
        try:
            r = ST.shrink_clip(p)
        except Exception as e:
            print(f"   ERR {os.path.basename(p)}: {e}")
            done["fail"] += 1
            return
        if r:
            done["n"] += 1
            done["old"] += r[0]
            done["new"] += r[1]
            if done["n"] % 50 == 0:
                print(f"   ...{done['n']}/{len(can)} "
                      f"{done['old'] / 1e9:.2f} -> {done['new'] / 1e9:.2f} GB "
                      f"({time.monotonic() - t0:.0f}s)", flush=True)

    with ThreadPoolExecutor(max_workers=a.luong) as ex:
        list(ex.map(one, can))
    print(f"2. da thu gon {done['n']} file: {done['old'] / 1e9:.2f} -> "
          f"{done['new'] / 1e9:.2f} GB ({done['fail']} loi)")

    n_link = 0
    for keep, others in groups:
        for x in others:
            if not os.path.exists(keep) or inode(x) == inode(keep):
                continue
            tmp = x + ".lnk.tmp"
            try:
                os.link(keep, tmp)
                os.replace(tmp, x)
                n_link += 1
                for c in ST._caches_of(x):
                    if os.path.exists(c):
                        os.remove(c)
            except OSError as e:
                print(f"   WARN hardlink {os.path.basename(x)}: {e}")
                if os.path.exists(tmp):
                    os.remove(tmp)
    print(f"1. da hardlink {n_link} ten trung")

    bv = set()
    for root, cfg in case_dang_do():
        bv |= ST.files_of_config(root, cfg)
    if not a.gioi_han:
        ST.enforce_cache_limit(KIT, protect=bv, limit_gb=a.tran)
    all_f = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".mp4")]
    sau = sum(os.path.getsize(p) for p in {inode(p): p for p in all_f}.values())
    print(f"XONG trong {time.monotonic() - t0:.0f}s: kho con {len(all_f)} file, "
          f"{sau / 1e9:.2f} GB (TB {sau / max(1, len(all_f)) / 1e6:.1f} MB/file)")


if __name__ == "__main__":
    main()
