"""
stock.py — Tai stock footage (Pixabay/Pexels API) theo keyword, cache lai.

Doc danh sach cell type 'stock' trong config.json:
  {"type": "stock", "stock": "server room ai", "dur": 8, "vo": "..."}

Tool tim video theo keyword, tai file MP4 ve assets/stock/<hash>.mp4.
Cache theo (api, keyword) — tải 1 lần, tái dùng. Hỗ trợ ca Pixabay va
Pexels (thu ca hai, lay cai co ket qua truoc).

API keys doc tu tool/.env hoac env var:
  PIXABAY_API_KEY, PEXELS_API_KEY
Khong co key hoac khong tim thay -> bo qua (render fallback ve card).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
    """Nap tool/.env vao os.environ (khong de len env da co)."""
    env_path = os.path.join(KIT_ROOT, "tool", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _keys():
    _load_env()
    return (os.environ.get("PIXABAY_API_KEY"), os.environ.get("PEXELS_API_KEY"))


def _stock_dir(root=None):
    """Thu muc stock DUNG CHUNG cua project (tai 1 lan, nhieu video dung).

    Neu root la video -> van tro ve assets/stock/ cap project de khong tai lai.
    """
    base = root or KIT_ROOT
    # Neu root tro toi videos/<topic>/ -> day len project (kho stock dung chung).
    # Ban cu con doi ten thu muc project phai dung bang "ai-frontier"; thu muc
    # that ten "ai-frontier-kit" nen dieu kien khong bao gio dung -> moi video di
    # tim kho rieng trong videos/<topic>/assets/stock (rong) va tai lai tu dau.
    if os.path.basename(os.path.dirname(os.path.abspath(base))) == "videos":
        base = KIT_ROOT
    d = os.path.join(base, "assets", "stock")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_path(root, api, keyword, idx=0):
    h = hashlib.md5(f"{api}|{keyword}|{idx}".encode("utf-8")).hexdigest()[:12]
    return os.path.join(_stock_dir(root), f"{h}.mp4"), h


# Nhom keyword LIEN QUAN cung theme — de khi 1 keyword it variant, dung keyword
# khac trong nhom de co pool stock du lon, khong lap file. Giu visual lien mach
# (cung theme) nhung khong trung. CHU Y: keyword phai dung CHU DE AI (san pham
# cua kenh), khong dung thu ky thuat chung (camera/circuit/server).
STOCK_THEMES = [
    ["AI robot humanoid", "robot AI futuristic", "cyborg AI", "humanoid robot",
     "AI robot walking", "android robot"],
    ["artificial intelligence abstract", "AI technology animation",
     "AI network animation", "smart technology AI", "AI data processing",
     "digital AI background"],
    ["digital human face", "AI assistant hologram", "AI chatbot interface",
     "hologram AI", "digital human 3d", "virtual assistant AI"],
    ["neural network animation", "machine learning visualization",
     "deep learning nodes", "AI brain visualization", "artificial intelligence brain"],
    ["future technology AI", "AI city futuristic", "sci-fi interface",
     "technology data AI", "AI virtual world", "futuristic digital screen"],
    # them 2 theme AI moi de da dang hon
    ["data visualization", "big data animation", "data stream visualization",
     "digital data flow", "analytics dashboard", "data particles"],
    ["futuristic HUD interface", "sci-fi holographic interface", "digital HUD",
     "hologram technology", "virtual reality interface", "augmented reality"],
    # them 3 theme AI mo rong — canh that khac biet hon (tranh trung noi dung)
    ["robot arm industrial", "android face closeup", "futuristic robot head",
     "robot hand touch human", "humanoid robot walking street", "robot dog robot"],
    ["holographic chart", "hologram globe", "holographic earth rotating",
     "augmented reality glasses", "smart glasses technology", "digital avatar talking"],
    ["neural network glowing", "AI neurons firing", "brain hologram rotating",
     "binary code screen", "quantum computer processor", "AI chatbot smartphone"],
]

# Map keyword -> nhom (fallback: nhom dau tien chua no)
_THEME_OF = {}
for ti, group in enumerate(STOCK_THEMES):
    for kw in group:
        _THEME_OF.setdefault(kw, ti)


# Tu bo qua khi so khop keyword voi theme (qua chung, khong phan biet duoc theme)
_STOP = {"ai", "the", "a", "an", "of", "and", "in", "on", "for", "with",
         "technology", "digital", "futuristic", "abstract"}


def _toks(s):
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower())
            if t and t not in _STOP}


_THEME_TOKS = [set().union(*[_toks(k) for k in g]) for g in STOCK_THEMES]


def theme_index(keyword, min_score=0.15):
    """Tra ve (theme_idx, score) cho keyword BAT KY.

    Keyword nguoi viet tu go (vd "nvidia chip factory") khong nam trong
    STOCK_THEMES; so khop tuyet doi se tra ve None -> pool chi 1 keyword ->
    het file sau 2-3 cell -> phai lay hinh theme khac (dut mach). Nen o day
    do do trung token de van gan duoc vao theme gan nhat.
    """
    if keyword in _THEME_OF:
        return _THEME_OF[keyword], 1.0
    kt = _toks(keyword)
    if not kt:
        return None, 0.0
    best, best_score = None, 0.0
    for i, tt in enumerate(_THEME_TOKS):
        s = len(kt & tt) / len(kt)
        if s > best_score:
            best, best_score = i, s
    return (best, best_score) if best_score >= min_score else (None, 0.0)


def theme_keywords(keyword):
    """Tra ve list keyword cung theme (keyword goc dung dau)."""
    idx, _ = theme_index(keyword)
    if idx is None:
        return [keyword]
    return [keyword] + [k for k in STOCK_THEMES[idx] if k != keyword]


def stock_pool(root, keyword, max_files=40):
    """Tra ve list FILE stock khac nhau cho keyword (tu keyword + cung theme).

    Dedup theo NOI DUNG bang hash 3 frame (0s/2s/4s) — loai video that trung
    (cung canh quay) du frame dau khac. Gioi han max_files de khong cham.
    """
    import subprocess
    seen_path, seen_content, pool = set(), set(), []
    for kw in theme_keywords(keyword):
        for i in range(8):
            if len(pool) >= max_files:
                break
            f = stock_file(root, kw, i)
            if not f or f in seen_path:
                continue
            seen_path.add(f)
            try:
                h = _content_hash(f)
                if h is None:
                    continue
                if h in seen_content:
                    continue
                seen_content.add(h)
            except Exception:
                pass
            pool.append(f)
    return pool


def _content_hash(f):
    """Hash 3 frame (0s/2s/4s) scale nho -> phat hien video trung noi dung.
    Co cache theo mtime de khong re-extract moi lan."""
    import subprocess, time
    cache = f + ".h"
    try:
        if os.path.exists(cache):
            with open(cache, "rb") as fh:
                data = fh.read().split(b"\n")
            if len(data) == 2 and float(data[1]) == os.path.getmtime(f):
                return data[0].decode()
    except Exception:
        pass
    hashes = []
    for ss in ("0", "2", "4"):
        png = f + f".{ss}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", ss,
                        "-i", f, "-frames:v", "1", "-vf", "scale=48:27",
                        png], capture_output=True, timeout=8)
        if not os.path.exists(png):
            return None
        with open(png, "rb") as fh:
            hashes.append(hashlib.md5(fh.read()).hexdigest()[:8])
        os.remove(png)
    h = "".join(hashes)
    try:
        with open(cache, "wb") as fh:
            fh.write(h.encode() + b"\n" + str(os.path.getmtime(f)).encode())
    except Exception:
        pass
    return h


def color_sig(f):
    """Chu ky mau: mean RGB cua frame 8x8 tai 0s/2s/4s -> vector 9 chieu.

    Dung de do do "hop tong" giua canh truoc va canh sau: hai clip cung chu de
    nhung mot cai xanh lanh, mot cai vang chay thi cat lien nhau van thay coc.
    Cache ra file .c ben canh video (giong _content_hash).
    """
    cache = f + ".c"
    try:
        if os.path.exists(cache):
            with open(cache, encoding="utf-8") as fh:
                data = fh.read().split("\n")
            if len(data) >= 2 and float(data[1]) == os.path.getmtime(f):
                return [float(x) for x in data[0].split(",")]
    except Exception:
        pass
    import numpy as np
    from PIL import Image
    vals = []
    for ss in ("0", "2", "4"):
        png = f + f".c{ss}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", ss, "-i", f,
                        "-frames:v", "1", "-vf", "scale=8:8", png],
                       capture_output=True, timeout=8)
        if not os.path.exists(png):
            return None
        try:
            a = np.asarray(Image.open(png).convert("RGB"), dtype=float) / 255.0
            vals += [float(x) for x in a.mean(axis=(0, 1))]
        finally:
            os.remove(png)
    try:
        with open(cache, "w", encoding="utf-8") as fh:
            fh.write(",".join(f"{v:.4f}" for v in vals) + "\n"
                     + str(os.path.getmtime(f)))
    except Exception:
        pass
    return vals


def color_dist(a, b):
    """0 = cung tong mau, ~1 = nguoc han. Thieu du lieu -> 0.5 (trung tinh)."""
    if not a or not b or len(a) != len(b):
        return 0.5
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _pixabay_search(key, keyword, per=50):
    """Tra ve list (url, width, height) — uu tien video 16:9 chay ngang."""
    q = urllib.parse.quote(keyword)
    url = (f"https://pixabay.com/api/videos/?key={key}&q={q}"
           f"&video_type=film&per_page={per}&safesearch=true"
           f"&min_width={MIN_W}&min_height={MIN_H}&order=popular")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    hits = data.get("hits", [])
    out = []
    for h in hits:
        vids = h.get("videos", {})
        # chon theo PIXEL that su, khong theo ten size: Pixabay luon tra du ca
        # 4 key large/medium/small/tiny, va entry khong ton tai co width=0.
        cands = [v for v in vids.values()
                 if v.get("url") and (v.get("width") or 0) >= MIN_W]
        if not cands:
            continue
        best = max(cands, key=lambda v: (v.get("width") or 0) * (v.get("height") or 0))
        out.append((best["url"], best.get("width", 0), best.get("height", 0)))
    return out


def _pexels_search(key, keyword, per=50):
    q = urllib.parse.quote(keyword)
    url = (f"https://api.pexels.com/videos/search?query={q}&per_page={per}"
           f"&orientation=landscape&size=large")
    req = urllib.request.Request(url, headers={"Authorization": key,
                                               "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("link") and f.get("file_type", "").startswith("video")
                 and (f.get("width") or 0) >= MIN_W]
        if not files:
            continue
        # ban nho nhat trong so cac ban >= 1920 rong: khong bao gio phai upscale,
        # ma cung khong tai ve file 4K nang gap 4 lan cho mot khung 1080p.
        hd = [f for f in files if (f.get("width") or 0) >= 1920]
        best = (min(hd, key=lambda f: f["width"] * f["height"]) if hd
                else max(files, key=lambda f: f["width"] * f["height"]))
        out.append((best["link"], best.get("width", 0), best.get("height", 0)))
    return out


MIN_W, MIN_H = 1280, 720


def _pick_landscape(items):
    """Loai portrait + duoi HD, uu tien do phan giai CANG CAO CANG TOT.

    Ban cu cham diem bang abs(h - 1080) nen phat ca hai chieu: clip 4K bi xep
    duoi clip 540p, va vi _fetch_keyword lay items[i] theo thu tu nay nen ban
    540p duoc tai ve con ban 4K gan nhu khong bao gio duoc dung. Nguon 540p
    phong len 1920x1080 chinh la mot nguyen nhan "video mo".
    """
    def ok(it):
        _, w, h = it
        return w and h and w >= MIN_W and h >= MIN_H and (w / h) >= 1.5

    def score(it):
        _, w, h = it
        rs = 1.0 - min(abs(w / h - 1.7778) / 0.6, 1.0)
        if h >= 2160:
            hs = 1.00        # 4K: downscale ve 1080 -> net nhat
        elif h >= 1440:
            hs = 0.98
        elif h >= 1080:
            hs = 0.95
        else:
            hs = 0.45        # 720p: phai upscale -> tru diem manh
        return hs * 0.65 + rs * 0.35
    return sorted([i for i in (items or []) if ok(i)], key=score, reverse=True)


def fetch_stock(root, cfg, force=False):
    """Tai stock clip cho cac cell type 'stock'. Tra ve so clip tai.

    Moi keyword co the duoc dung nhieu lan trong 1 video — tai NHIEU VARIANT
    (index 0,1,2...) de moi cell dung mot clip khac nhau, tranh trung lap.
    """
    stock_cells = [c for c in cfg.get("cells", []) if c.get("type") == "stock"]
    if not stock_cells:
        print("(rong) config khong co cell type 'stock'")
        return 0
    pk, px = _keys()
    if not pk and not px:
        print("WARN: thieu PIXABAY_API_KEY / PEXELS_API_KEY trong tool/.env — bo qua")
        return 0

    # dem so lan moi keyword xuat hien -> so variant can tai
    from collections import Counter
    occ = Counter(c.get("stock") or c.get("keyword") or "" for c in stock_cells)

    # Gom theo theme: moi theme can du variant de moi cell co nhieu file khac nhau.
    theme_needs = {}   # theme idx -> so luong variant can (dinh muc: 6/keyword trong theme)
    for kw, count in occ.items():
        if not kw:
            continue
        idx = _THEME_OF.get(kw)
        if idx is None:
            # keyword ngoai theme: tai 6 variant cho rieng no
            _fetch_keyword(root, kw, 6, pk, px, force)
            continue
        theme_needs[idx] = theme_needs.get(idx, 0) + 6

    # tai cho moi keyword trong theme so variant du (de pool lon)
    n = 0
    for ti, need in theme_needs.items():
        for kw in STOCK_THEMES[ti]:
            n += _fetch_keyword(root, kw, max(3, need // len(STOCK_THEMES[ti])), pk, px, force)
    return n


def _fetch_keyword(root, kw, count, pk, px, force):
    """Tai variant cho 1 keyword tu CA Pixabay va Pexels.

    Pixabay dung idx 0..count-1, Pexels dung idx count..2*count-1 — de moi API
    co cache rieng, khong trung, pool lon gap doi.
    """
    got = 0
    offsets = {"pixabay": 0, "pexels": count}
    for api, key in (("pixabay", pk), ("pexels", px)):
        if not key:
            continue
        try:
            items = _pixabay_search(key, kw) if api == "pixabay" else _pexels_search(key, kw)
        except Exception as e:
            print(f"  WARN {api} '{kw}': {e}")
            continue
        items = _pick_landscape(items)
        if not items:
            print(f"  WARN {api} khong tim thay '{kw}'")
            continue
        # items[i % len(items)] cua ban cu tai CUNG mot URL vao nhieu file khac
        # nhau khi ket qua it hon count -> pool "to" nhung toan ban sao.
        seen_url, picked = set(), []
        for it in items:
            if it[0] in seen_url:
                continue
            seen_url.add(it[0])
            picked.append(it)
            if len(picked) >= count:
                break
        off = offsets[api]
        for i, (url, w, h) in enumerate(picked):
            idx = off + i
            path, _ = _cache_path(root, api, kw, idx)
            if os.path.exists(path) and not force:
                got += 1
                continue
            print(f"  tai '{kw}'#{idx} ({w}x{h}) tu {api} ...")
            try:
                _download(url, path)
            except Exception as e:
                print(f"  WARN tai that bai '{kw}'#{idx}: {e}")
                continue
            if not _verify_hd(path):
                continue
            print(f"stock '{kw}'#{idx} -> {os.path.relpath(path, root)}")
            got += 1
    return got


def _verify_hd(path):
    """Kiem tra file vua tai co dung do phan giai khong — API co the tra sai."""
    try:
        from probe import streams
        v = streams(path).get("video")
        if not v or (v.get("h") or 0) < 900:
            print(f"  BO {os.path.basename(path)}: chi {v.get('w')}x{v.get('h')}"
                  if v else f"  BO {os.path.basename(path)}: khong co video stream")
            os.remove(path)
            return False
    except Exception:
        pass
    return True


def fetch_stock_all(root=None, variants=12, force=False):
    """Tai TOAN BO stock cho moi keyword moi theme (dung chung cho nhieu video).

    Moiz keyword tai `variants` file khac nhau tu Pixabay/Pexels -> pool lon.
    """
    pk, px = _keys()
    if not pk and not px:
        print("WARN: thieu key stock")
        return 0
    n = 0
    total_kw = sum(len(g) for g in STOCK_THEMES)
    for ti, group in enumerate(STOCK_THEMES):
        for kw in group:
            got = _fetch_keyword(root, kw, variants, pk, px, force)
            n += got
        print(f"  theme {ti}/{len(STOCK_THEMES)} done")
    print(f"\nfetch_stock_all: tong {n} file cho {total_kw} keyword (shared stock)")
    return n


def list_stock_usage(root, cfg):
    """List file stock dung o moi cell + canh bao trung lap.

    Doc build/stock-state.json (timeline: cell -> file -> [start,end]) do render
    ghi lai — NHANH, khong hash lai segment. Neu chua co timeline (render cu),
    fallback scan build/tmp/stockseg-*.mp4.
    """
    import glob, json
    timeline = []
    sp = os.path.join(root, "build", "stock-state.json")
    if os.path.exists(sp):
        try:
            timeline = json.load(open(sp, encoding="utf-8")).get("stock_timeline", [])
        except Exception:
            timeline = []

    used = {}      # cell -> [ {file, content, start, end} ]
    warns = []
    if timeline:
        for rec in timeline:
            cid = rec.get("cell")
            used.setdefault(cid, []).append(rec)
    else:
        # fallback: scan segment files (khong co timeline -> hash lai)
        seg_cell = {}
        for p in glob.glob(os.path.join(root, "build", "tmp", "stockseg-*.mp4")):
            b = os.path.basename(p)
            m = re.match(r"stockseg-(\d+)-\d+\.mp4", b)
            if m:
                seg_cell[p] = int(m.group(1))
        seen_h = {}
        for p, cid in seg_cell.items():
            h = _content_hash(p)
            if h and h in seen_h and seen_h[h] != p:
                warns.append(f"  TRUNG noi dung: cell {cid} {os.path.basename(p)} "
                             f"~ cell {seg_cell.get(seen_h[h])} {os.path.basename(seen_h[h])}")
            if h:
                seen_h.setdefault(h, p)
            used.setdefault(cid, []).append({"file": p, "content": h})

    print("\n=== Stock usage (timeline) ===")
    for c in cfg.get("cells", []):
        if c.get("type") != "stock":
            continue
        cid = c["id"]
        recs = used.get(cid, [])
        for r in recs:
            print(f"cell {cid:>3} ({c.get('stock','')[:28]:<30}) "
                  f"[{r.get('start',0):6.1f}-{r.get('end',0):6.1f}] "
                  f"{os.path.basename(r['file'])}")

    # canh bao: 1 content dung 2 cell gan nhau (trong COOLDOWN) hoac 2 noi dung
    # trung trong cung cell -> lua chon de khong lap.
    by_content = {}   # content -> [(cell, start, end)]
    for cid, recs in used.items():
        for r in recs:
            if r.get("content"):
                by_content.setdefault(r["content"], []).append(
                    (cid, r.get("start", 0), r.get("end", 0)))
    import re as _re
    for h, entries in by_content.items():
        if len(entries) > 1:
            entries.sort(key=lambda e: e[1])
            for i in range(1, len(entries)):
                gap = entries[i][1] - entries[i - 1][2]
                if gap < 60:
                    warns.append(
                        f"  TRUNG content {h[:8]}: cell {entries[i-1][0]} "
                        f"@{entries[i-1][1]:.0f}s va cell {entries[i][0]} "
                        f"@{entries[i][1]:.0f}s (cach {gap:.0f}s < 60s)")

    if warns:
        print("\n=== CANH BAO ===")
        for w in warns:
            print(w)
    else:
        print("\n(OK) khong co stock trung trong 60s.")
    return warns


def prune_stock(root, dry_run=True):
    """Xoa cac file stock trung NOI DUNG (hash 3 frame) trong assets/stock.

    Giu 1 ban moi content-hash. Chien luoc giu: uu tien file thuoc keyword co it
    content nhat (de pool khong dói). Tra ve (giu, xoa, freed_mb).
    """
    import glob
    d = _stock_dir(root)
    files = [f for f in os.listdir(d) if f.endswith(".mp4")]
    # hash moi file (dung .h cache neu co)
    by_h = {}
    for f in files:
        h = _content_hash(os.path.join(d, f))
        if h is None:
            continue  # khong hash duoc -> khong dong toi
        by_h.setdefault(h, []).append(os.path.join(d, f))
    # dem content unique cua moi keyword de biet keyword nao "doi"
    kw_unique = {}
    for kw in sorted({k for g in STOCK_THEMES for k in g}):
        seen = set()
        for f in files:
            p = os.path.join(d, f)
            if os.path.exists(p + ".h"):
                h = open(p + ".h").read().splitlines()[0]
                if h:
                    seen.add(h)
        kw_unique[kw] = len(seen)
    # quyet dinh giu: moi hash giu 1 file, uu tien keyword it content nhat
    import hashlib as _hl
    fmap = {}  # filename-without-ext -> (api, kw, idx)
    for kw in sorted({k for g in STOCK_THEMES for k in g}):
        for api in ("pixabay", "pexels"):
            for idx in range(8):
                h = _hl.md5(f"{api}|{kw}|{idx}".encode()).hexdigest()[:12]
                fmap.setdefault(h, (api, kw, idx))

    def _score(p):
        kw = fmap.get(os.path.basename(p)[:-4], (None, None, None))[1]
        return (kw_unique.get(kw, 999), os.path.basename(p))

    keep, drop = [], []
    for h, lst in by_h.items():
        lst.sort(key=_score)
        keep.append(lst[0])
        drop.extend(lst[1:])
    freed = sum(os.path.getsize(p) for p in drop) / 1e6
    if dry_run:
        print(f"prune (dry-run): giu {len(keep)} file, xoa {len(drop)} file "
              f"(~{freed:.0f} MB)")
        return len(keep), len(drop), freed
    for p in drop:
        try:
            os.remove(p)
            for ext in (".h", ".0.png", ".2.png", ".4.png"):
                if os.path.exists(p + ext):
                    os.remove(p + ext)
        except OSError:
            pass
    print(f"prune: xoa {len(drop)} file trung (~{freed:.0f} MB). "
          f"Giu {len(keep)} content unique.")
    return len(keep), len(drop), freed


def _download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    tmp = path + ".part"
    with urllib.request.urlopen(req, timeout=60) as r:
        with open(tmp, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    os.replace(tmp, path)


def stock_file(root, keyword, idx=0):
    """Tra ve duong dan clip stock variant idx cho keyword, hoac None.

    KHONG phu thuoc API key: key chi can luc TAI. Ban cu bo qua ca file da co
    san khi thieu key, nghia la mat key thi toan bo kho stock da tai thanh vo
    hinh va video im lang rot ve card.
    """
    for api in ("pixabay", "pexels"):
        path, _h = _cache_path(root, api, keyword, idx)
        if os.path.exists(path):
            return path
    return None


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "videos/test-60s"
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as CFG
    cfg = CFG.load(root)
    fetch_stock(root, cfg)


if __name__ == "__main__":
    main()
