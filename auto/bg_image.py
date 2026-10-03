# -*- coding: utf-8 -*-
"""bg_image.py — che do MOT ANH NEN cho ca video (anh: bg).

Vi sao khong dung duong stock binh thuong: render co bo chon file thong minh
(dedup theo content, cooldown 150s, cham diem lien quan/mau). Neu chi co dung
mot file thi sau lan dung dau no bi coi la "vua dung xong" va bo chon se di lay
file khac trong kho chung assets/stock (791 content cua cac du an truoc) — hinh
se lac de hoan toan.

Nen o che do nay ta khong dung type 'stock' nua:
  1. tai MOT anh tu Wikimedia Commons theo chu de,
  2. dung thanh mot video TINH 1920x1080 (x264 stillimage, rat nhe),
  3. ghi vao assets/clips/clip-900.mp4,
  4. viet lai config.json: moi cell type 'stock' -> 'clip-mute' tro vao clip 900.

render_clip doc thang assets/clips/clip-<id>.mp4, khong qua bo chon nao.
"""
import json
import os
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "tool"))

import wiki_images as WI  # noqa: E402

BG_CLIP_ID = 900
W, H, FPS = 1920, 1080, 24
BG_DUR = 30.0           # du cho cell dai nhat (cell dai nhat do duoc ~13s)


# Anh thoi su/chien tranh hay thang diem khop ten file ("Vietnamese", "Tet")
# nhung sai hoan toan khong khi video van hoa. Loai tru tru khi chinh de tai
# nhac den chung.
CAM = {"war", "wounded", "shrapnel", "offensive", "soldier", "soldiers",
       "military", "army", "battle", "marines", "napalm", "bomb", "bombing",
       "refugee", "casualty", "corpse", "protest", "riot", "helicopter",
       "rifle", "tank", "massacre", "veteran", "1968", "1972"}


def _loai(hits, query, diem_toi_thieu=2):
    """Giu anh thuc su khop chu de: du diem ten file, khong dinh tu cam."""
    q = set(w.lower() for w in query.split())
    ra = []
    for h in hits:
        t = h["title"].lower()
        if any(w in CAM and w not in q for w in
               __import__("re").findall(r"[a-z0-9]+", t)):
            continue
        if WI._title_score(h["title"], query) < diem_toi_thieu:
            continue
        ar = h["width"] / float(h["height"] or 1)
        if ar < 1.1:                 # anh doc lam nen 16:9 se bi crop nat
            continue
        ra.append(h)
    return ra


VI_API = "https://vi.wikipedia.org/w/api.php"


def _anh_bai_wikipedia(tu_khoa_vi, log=print):
    """Anh dai dien cua bai vi.wikipedia sat de tai.

    Tim kiem tieng Anh tren Commons rat yeu voi de tai van hoa Viet: no cham
    diem theo ten file nen "Vietnamese ... Tet" ra anh chien tranh Mau Than,
    "ancestral" ra phong tranh to tien mot cung dien o Munich. Bai vi.wikipedia
    thi tra dung anh cua chinh chu de.
    """
    import urllib.parse
    import urllib.request

    def _goi(q):
        req = urllib.request.Request(VI_API + "?" + urllib.parse.urlencode(q),
                                     headers={"User-Agent": WI.UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            log(f"    (bo qua) wikipedia VN loi: {e}")
            return {}

    chung = {"action": "query", "format": "json",
             "prop": "pageimages", "piprop": "original", "pilicense": "any"}
    # 1) TEN BAI CHINH XAC truoc. Tim kiem toan van rat lech: "Tao Quan" ra bai
    #    mot nghe si, "Mam ngu qua" ra bai Tet Nguyen Dan.
    data = _goi(dict(chung, titles=tu_khoa_vi, redirects="1"))
    pages = [p for p in (data.get("query") or {}).get("pages", {}).values()
             if "missing" not in p and (p.get("original") or {}).get("source")]
    if not pages:
        # 2) khong co bai dung ten -> moi den tim kiem
        data = _goi(dict(chung, generator="search", gsrsearch=tu_khoa_vi,
                         gsrlimit="3"))
        pages = sorted((data.get("query") or {}).get("pages", {}).values(),
                       key=lambda p: p.get("index", 99))
    if not pages:
        # 3) bai co that nhung khong co anh dai dien ngang -> lay anh TRONG BAI
        data = _goi({"action": "query", "format": "json", "titles": tu_khoa_vi,
                     "redirects": "1", "generator": "images", "gimlimit": "20",
                     "prop": "imageinfo", "iiprop": "url|size|mime",
                     "iiurlwidth": "1920"})
        for p in (data.get("query") or {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            w, h = ii.get("width", 0), ii.get("height", 0)
            if not ii.get("mime", "").startswith("image/"):
                continue
            if ii.get("mime") in ("image/svg+xml", "image/gif"):
                continue
            if w < 900 or h < 600 or w < h:
                continue
            ten = p.get("title", "").lower()
            if any(x in ten for x in ("icon", "logo", "flag", "map of", "commons-",
                                      "ambox", "question", "edit-")):
                continue
            return ii.get("thumburl") or ii.get("url"), {
                "title": p.get("title", ""), "license": "xem trang anh",
                "credit": "Wikimedia Commons qua bai " + tu_khoa_vi,
                "page": "https://vi.wikipedia.org/wiki/"
                        + urllib.parse.quote(tu_khoa_vi.replace(" ", "_")),
                "width": w, "height": h}

    for p in pages:
        org = p.get("original") or {}
        url = org.get("source")
        if not url or org.get("width", 0) < 700:
            continue
        if org.get("width", 0) < org.get("height", 1):   # anh doc
            continue
        return url, {"title": p.get("title", ""), "license": "xem trang bai",
                     "credit": "vi.wikipedia " + p.get("title", ""),
                     "page": "https://vi.wikipedia.org/wiki/"
                             + urllib.parse.quote(p.get("title", "").replace(" ", "_")),
                     "width": org.get("width"), "height": org.get("height")}
    return None, None


def _tai_anh(query, tmpdir, min_bytes=60_000, thu=6):
    """Lay anh khop chu de nhat tu Wikimedia Commons cho `query`."""
    os.makedirs(tmpdir, exist_ok=True)
    tho = WI.search_commons(query, limit=30, want=thu * 4)
    if not tho:
        return None, None
    hits = _loai(tho, query)
    if not hits:                      # noi long dan thay vi chiu tay trang
        hits = _loai(tho, query, diem_toi_thieu=1)
    if not hits:
        hits = tho
    import hashlib
    for h in hits[:thu * 3]:
        try:
            data = WI._get(h["url"], timeout=45)
        except Exception:
            continue
        if len(data) < min_bytes:
            continue
        ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
        p = os.path.join(tmpdir, hashlib.md5(h["url"].encode()).hexdigest()[:10] + ext)
        with open(p, "wb") as f:
            f.write(data)
        return p, h
    return None, None


def _anh_tinh(img, out, dur=BG_DUR):
    """Anh -> video tinh 1920x1080. Nen tinh nen file chi vai tram KB."""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},setsar=1,format=yuv420p")
    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", img,
           "-t", f"{dur:.2f}", "-r", str(FPS), "-vf", vf,
           "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast",
           "-crf", "26", "-g", "48", "-an", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _tu_khoa(root):
    """Doc script/bg.txt -> (tu khoa tieng Viet, truy van tieng Anh).

    Dinh dang bg.txt:
        vi: Mam ngu qua
        en: Vietnamese five fruit tray altar
    """
    vi = en = None
    p = os.path.join(root, "script", "bg.txt")
    if os.path.exists(p):
        # utf-8-sig: file ghi tu PowerShell co BOM, doc bang utf-8 thuong thi
        # dong dau thanh "﻿vi: ..." va khong khop tien to nao.
        for line in open(p, encoding="utf-8-sig").read().splitlines():
            s = line.strip()
            if s.lower().startswith("vi:"):
                vi = s[3:].strip()
            elif s.lower().startswith("en:"):
                en = s[3:].strip()
            elif s and not en:
                en = s
    if not en:
        kws = WI.keywords_from_config(root)
        en = kws[0] if kws else None
    return vi, en


def dung_bg(root, query=None, log=print):
    """Tai anh + dung clip tinh + viet lai config.json. Tra ve (file, credit)."""
    cfg_path = os.path.join(root, "config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    vi, en = _tu_khoa(root)
    if query:
        en = query
    if not (vi or en):
        raise RuntimeError("khong co tu khoa de tim anh nen")

    tmpdir = os.path.join(root, "build", "tmp", "bg")
    os.makedirs(tmpdir, exist_ok=True)
    img = hit = None

    # 1) anh bai vi.wikipedia — dung chu de nhat
    if vi:
        log(f"    tim anh nen (wikipedia VN): \"{vi}\"")
        url, meta = _anh_bai_wikipedia(vi, log=log)
        if url:
            try:
                import hashlib
                data = WI._get(url, timeout=60)
                ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
                img = os.path.join(tmpdir,
                                   hashlib.md5(url.encode()).hexdigest()[:10] + ext)
                with open(img, "wb") as f:
                    f.write(data)
                hit = meta
            except Exception as e:
                log(f"    (bo qua) tai anh wikipedia loi: {e}")
                img = None

    # 2) Commons, co loc
    if not img and en:
        log(f"    tim anh nen (Commons): \"{en}\"")
        img, hit = _tai_anh(en, tmpdir)
    if not img:
        raise RuntimeError(f"khong tim duoc anh nen cho \"{vi or en}\"")

    out = os.path.join(root, "assets", "clips", f"clip-{BG_CLIP_ID}.mp4")
    _anh_tinh(img, out)
    log(f"    anh nen: {hit['title'][:60]} ({os.path.getsize(out) / 1e6:.1f} MB)")

    doi = 0
    for c in cfg["cells"]:
        if c.get("type") == "stock":
            c["type"] = "clip-mute"
            c["clip"] = BG_CLIP_ID
            c.pop("stock", None)
            c.pop("src", None)      # khong hien chu thich nguon tren hinh
            doi += 1
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    log(f"    doi {doi} cell sang dung anh nen chung")

    # Shot da render truoc do van om anh nen CU: render khong biet file clip-900
    # vua doi ruot (duong dan khong doi). Xoa de no dung lai.
    # Phai xoa CA build/trim: assemble giai doan 1 thay batch-0.mp4 con do la
    # dung lai luon, nen du shot da render lai theo anh moi thi ban ghep cuoi
    # van la hinh cu.
    import shutil as _sh
    n = 0
    for d, exts in ((os.path.join(root, "build", "shots"), (".mp4",)),):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(exts):
                    os.remove(os.path.join(d, f))
                    n += 1
    trim = os.path.join(root, "build", "trim")
    if os.path.isdir(trim):
        _sh.rmtree(trim, ignore_errors=True)
    if n:
        log(f"    xoa {n} shot + ban trim cu de dung lai theo anh nen moi")

    credit = {
        "query": vi or en, "title": hit["title"], "license": hit["license"],
        "credit": hit["credit"],
        "page": hit.get("page") or ("https://commons.wikimedia.org/wiki/"
                                    + hit["title"].replace(" ", "_")),
    }
    with open(os.path.join(root, "build", "bg-credit.json"), "w",
              encoding="utf-8") as f:
        json.dump(credit, f, ensure_ascii=False, indent=2)
    return out, credit


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--q", default=None, help="tu khoa tim anh (mac dinh: keyword dau trong config)")
    a = ap.parse_args()
    dung_bg(os.path.abspath(a.case), a.q)


if __name__ == "__main__":
    main()
