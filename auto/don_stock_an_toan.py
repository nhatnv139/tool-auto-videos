# -*- coding: utf-8 -*-
"""don_stock_an_toan.py — xoa file stock trung noi dung, TRU file cac case dang lam.

Vi sao khong dung `stock --prune`: ham prune_stock() chon file de giu bang
kw_unique, ma vong lap tinh kw_unique chi duyet STOCK_THEMES (toan keyword
AI/robot cua kenh commentary cu). Voi keyword lich su Trung Hoa, kw_unique.get()
luon tra ve mac dinh 999 nen co che "uu tien giu file cua keyword doi" khong
chay — no xoa theo ten file. Mot keyword co the bi xoa sach file va cell do tut
xuong thanh card.

Ban nay:
  1. Doc config.json cua cac case duoc BAO VE -> tap keyword.
  2. Suy ra ten file cua tung keyword theo md5("<api>|<kw>|<idx>").
  3. Gom file theo content-hash. Trong moi nhom trung nhau, LUON giu mot file
     duoc bao ve neu co; chi xoa file KHONG thuoc case nao duoc bao ve.

Dung:
    python auto\\don_stock_an_toan.py --giu can-long-sau-muoi-nam
    python auto\\don_stock_an_toan.py --giu a --giu b --that
"""
import argparse
import hashlib
import json
import os
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "tool"))

import stock as ST  # noqa: E402


def keywords_cua_case(slug):
    p = os.path.join(KIT, "videos", slug, "config.json")
    if not os.path.exists(p):
        return set()
    cfg = json.load(open(p, encoding="utf-8"))
    return {c.get("stock") or c.get("keyword") or ""
            for c in cfg.get("cells", []) if c.get("type") == "stock"} - {""}


def ten_file_duoc_bao_ve(keywords):
    """Moi keyword sinh ra ten file o MOI kho va MOI idx — bao ve tat ca."""
    ten = set()
    for kw in keywords:
        for api in ST.APIS:
            for idx in range(ST.MAX_IDX):
                h = hashlib.md5(f"{api}|{kw}|{idx}".encode()).hexdigest()[:12]
                ten.add(h + ".mp4")
    return ten


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giu", action="append", default=[],
                    help="slug case can bao ve (lap lai duoc)")
    ap.add_argument("--that", action="store_true", help="xoa that")
    a = ap.parse_args()

    d = ST._stock_dir(KIT)
    files = sorted(f for f in os.listdir(d) if f.endswith(".mp4"))

    kws = set()
    for slug in a.giu:
        k = keywords_cua_case(slug)
        print(f"bao ve {slug}: {len(k)} keyword")
        kws |= k
    bao_ve = ten_file_duoc_bao_ve(kws)
    n_bv = len([f for f in files if f in bao_ve])
    print(f"{len(files)} file trong kho, {n_bv} file thuoc case duoc bao ve")

    by_h = {}
    for i, f in enumerate(files):
        if i % 200 == 0:
            print(f"  ...hash {i}/{len(files)}", flush=True)
        h = ST._content_hash(os.path.join(d, f))
        if h is None:
            continue
        # _content_hash tra ve chuoi (doc tu cache .h) hoac list float — nhan ca hai
        key = h if isinstance(h, str) else tuple(round(float(x), 3) for x in h)
        by_h.setdefault(key, []).append(f)

    drop = []
    for h, lst in by_h.items():
        if len(lst) < 2:
            continue
        # giu mot file: uu tien file duoc bao ve
        uu_tien = [f for f in lst if f in bao_ve] or lst
        giu = uu_tien[0]
        for f in lst:
            if f == giu or f in bao_ve:
                continue      # khong bao gio xoa file duoc bao ve
            drop.append(f)

    freed = sum(os.path.getsize(os.path.join(d, f)) for f in drop)
    print(f"\nxoa duoc {len(drop)} file trung (~{freed/1e9:.2f} GB), "
          f"giu lai {len(files)-len(drop)}")
    if not a.that:
        print("(xem truoc) them --that de xoa that")
        return
    for f in drop:
        for hau in ("", ".c", ".h"):
            p = os.path.join(d, f + hau)
            if os.path.exists(p):
                os.remove(p)
    print(f"da xoa. Giai phong ~{freed/1e9:.2f} GB")


if __name__ == "__main__":
    main()
