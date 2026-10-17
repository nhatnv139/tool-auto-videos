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
    """Nap tool/.env vao os.environ (khong de len env da co).

    Dong co gia tri RONG bi bo qua: .env mau de san `PEXELS_API_KEY=` o dau
    file, ban cu setdefault gia tri rong nay truoc roi key that ghi o cuoi file
    khong bao gio duoc nap — nhin .env thay co key ma tool van bao thieu key.
    """
    env_path = os.path.join(KIT_ROOT, "tool", ".env")
    if os.path.exists(env_path):
        # utf-8-sig: file ghi tu PowerShell co the co BOM -> ten bien dau tien
        # thanh "﻿PIXABAY_API_KEY" va khong khop gi ca.
        with open(env_path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if not v:
                    continue
                if not os.environ.get(k):      # rong hoac chua co -> ghi de
                    os.environ[k] = v


def _keys():
    _load_env()
    return (os.environ.get("PIXABAY_API_KEY"), os.environ.get("PEXELS_API_KEY"))


def _key(name):
    """Lay mot key bat ky theo ten bien (COVERR_API_KEY, UNSPLASH_ACCESS_KEY...)."""
    _load_env()
    return os.environ.get(name)


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


# Cac "kho" file trong assets/stock. Ba kho dau la VIDEO tai thang tu API;
# ba kho sau la ANH TINH da bien thanh shot Ken Burns (xem stock_photo.py).
# Ten kho chi de bam hash duong dan -> doi ten la mat toan bo cache cu.
VIDEO_APIS = ("pixabay", "pexels", "coverr")
# "wiki" = anh Wikimedia -> Ken Burns. Ban cu wiki ghi nho vao kho "pixabay" nen
# cung md5("pixabay|kw|0") voi video Pixabay that: ai tai truoc thi thang, file
# sau bi coi la "da co" va khong bao gio tai. Anh wiki cu con nam trong kho
# pixabay thi van doc duoc (stock_files quet ca hai), chi file moi ghi kho rieng.
PHOTO_APIS = ("photo", "wiki")   # anh tinh (Unsplash/Pexels/Pixabay | Commons)
APIS = VIDEO_APIS + PHOTO_APIS

# Dai idx toi da mot keyword co the chiem trong mot kho. _fetch_keyword doi
# moi nguon mot doan idx rieng (pixabay 0.., pexels count.., coverr 2*count..)
# voi count = 6 hoac 12 (fetch_stock_all) -> cao nhat la 3*12 = 36.
MAX_IDX = 36


def _cache_path(root, api, keyword, idx=0):
    h = hashlib.md5(f"{api}|{keyword}|{idx}".encode("utf-8")).hexdigest()[:12]
    return os.path.join(_stock_dir(root), f"{h}.mp4"), h


# ---------------------------------------------------------------------------
# Marker [[stock:"<canh>"|ent="<thuc the>"]] — xem script2config.py.
# Cell co `ent` lay hinh tu lieu THAT cua thuc the (kho "wiki", khoa "ent:<ten>")
# truoc, keyword chi con la duong lui.
# ---------------------------------------------------------------------------

def cell_kw(cell):
    return (cell.get("stock") or cell.get("keyword") or "").strip()


def cell_ent(cell):
    return (cell.get("ent") or "").strip()


def ent_key(ent):
    """Khoa kho cho anh tu lieu cua mot thuc the. Tien to "ent:" de khong bao
    gio trung keyword canh (keyword "Qianlong Emperor" van la keyword)."""
    return "ent:" + ent


def cell_pool_key(cell):
    """Khoa pool cua cell trong render: hai cell cung keyword nhung khac ent
    phai co pool khac nhau."""
    kw, ent = cell_kw(cell), cell_ent(cell)
    return f"{kw}||{ent}" if ent else kw


# Moi file trong kho dong gop ~8s len hinh: render cat doan 6s, shot Ken Burns
# dai 9s nen _add_offsets lay duoc 1-2 doan tu mot file. Du 1 file cho lan dedup
# content (Pexels hay tra hai clip cung canh quay).
SHOT_SEC = 8.0
SPARE = 1
# 213 am tiet/phut (chuan kenh, xem CLAUDE.md) = 3,55 tieng/giay khi chua co voice.
_TOK_PER_SEC = 3.55


def cell_seconds(root, cell):
    """Thoi luong cell: do tu build/voice/cell-N.mp3 neu co, khong thi uoc theo
    so tieng cua VO (tieng Viet: 1 am tiet = 1 token)."""
    vo_path = os.path.join(root, "build", "voice", f"cell-{cell.get('id')}.mp3")
    pause = float(cell.get("pause_after") or 0.0)
    if os.path.exists(vo_path):
        try:
            from probe import duration
            return duration(vo_path) + pause
        except (SystemExit, Exception):
            pass
    vo = cell.get("vo") or ""
    if vo:
        n = len(re.findall(r"[^\s/|^*]+", vo))
        return n / _TOK_PER_SEC + pause
    return float(cell.get("dur") or 4.0)


def n_files_for(seconds, cap=None):
    import math
    n = int(math.ceil(max(0.0, seconds) / SHOT_SEC)) + SPARE
    return min(n, cap) if cap else n


def stock_cells(cfg):
    return [c for c in cfg.get("cells", []) if c.get("type") == "stock"]


def ent_demand(root, cfg):
    """{ent: (giay, [cell id])} cho moi thuc the trong config."""
    out = {}
    for c in stock_cells(cfg):
        e = cell_ent(c)
        if not e:
            continue
        s, ids = out.get(e, (0.0, []))
        out[e] = (s + cell_seconds(root, c), ids + [c.get("id")])
    return out


def kw_demand(root, cfg, cap=None):
    """{keyword: so file can} — CHI phan con thieu cua keyword do.

    Ban cu tai co dinh (6 moi API x 3 API, --all la 12) cho moi keyword: 171
    keyword Can Long thanh ~2000 file va kho phinh len 21 GB, trong khi mot cell
    trung binh 10,2s chi dung 2 doan 6s. Nay: tong giay cac cell dung keyword /
    SHOT_SEC + SPARE, tru di file DA CO o moi kho.

    Cell co ent: keyword chi la duong lui — chi tinh khi kho anh tu lieu cua ent
    do con thieu so voi thoi luong cac cell cua no.
    """
    ent_short = {}
    for e, (sec, _ids) in ent_demand(root, cfg).items():
        have = len(stock_files(root, ent_key(e)))
        ent_short[e] = have < n_files_for(sec)
    sec_kw = {}
    for c in stock_cells(cfg):
        kw, e = cell_kw(c), cell_ent(c)
        if not kw:
            continue
        if e and not ent_short.get(e, True):
            sec_kw.setdefault(kw, 0.0)
            continue
        sec_kw[kw] = sec_kw.get(kw, 0.0) + cell_seconds(root, c)
    out = {}
    for kw, sec in sec_kw.items():
        need = n_files_for(sec, cap) if sec > 0 else 0
        out[kw] = max(0, need - len(stock_files(root, kw)))
    return out


# ---------------------------------------------------------------------------
# Circuit breaker + nhip goi API theo TUNG nguon.
#
# Do thuc te lan chay Can Long: Coverr tra 403 cho MOI luot (171 keyword x ca
# video lan anh) ma van goi tiep; Pexels dinh 429 vi 200 req/gio chia cho ca
# photo lan stock. Nay: 401/403 -> tat nguon do ca phien; 429 -> doi theo
# Retry-After/luy thua va nhan doi khoang cach giua hai luot; het quota (header
# X-Ratelimit-Remaining = 0 ma reset con xa) -> cung tat.
# ---------------------------------------------------------------------------
import threading as _th
import time as _time


class ApiDown(Exception):
    pass


class _Rt:
    def __init__(self, gap, par):
        self.gap = gap                 # giay toi thieu giua hai luot search
        self.dead = None               # ly do tat (None = dang song)
        self.lock = _th.Lock()
        self.last = 0.0
        self.sem = _th.Semaphore(par)  # so luot TAI file song song
        self.n429 = 0


# gap theo quota tai lieu: Pixabay 100 req/60s, Pexels 200 req/gio (dung chung
# anh + video), Unsplash demo 50 req/gio, Coverr demo 50 req/gio. Gap chi chan
# burst; quota gio thi do header Remaining lo.
_RT = {
    "pixabay": _Rt(0.7, 4),
    "pexels": _Rt(1.0, 4),
    "coverr": _Rt(1.5, 2),
    "unsplash": _Rt(1.2, 3),
}
_RT_LOCK = _th.Lock()


def api_alive(api):
    rt = _RT.get(api)
    return not (rt and rt.dead)


def _kill(api, why):
    rt = _RT[api]
    with _RT_LOCK:
        if rt.dead:
            return
        rt.dead = why
    print(f"  [breaker] TAT {api} ca phien: {why}")


def api_get(api, url, headers=None, timeout=30, tries=4):
    """GET mot endpoint SEARCH qua breaker. Nem ApiDown khi nguon da tat."""
    import urllib.error
    rt = _RT[api]
    last = None
    for attempt in range(tries):
        if rt.dead:
            raise ApiDown(f"{api}: {rt.dead}")
        with rt.lock:
            wait = rt.gap - (_time.monotonic() - rt.last)
            if wait > 0:
                _time.sleep(wait)
            rt.last = _time.monotonic()
        req = urllib.request.Request(
            url, headers=dict({"User-Agent": "Mozilla/5.0"}, **(headers or {})))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                rem = r.headers.get("X-Ratelimit-Remaining") or \
                    r.headers.get("X-RateLimit-Remaining")
                reset = r.headers.get("X-Ratelimit-Reset") or \
                    r.headers.get("X-RateLimit-Reset")
            try:
                if rem is not None and int(rem) <= 0:
                    # Pexels: reset = epoch; Pixabay: reset = so giay con lai
                    r_s = float(reset or 0)
                    con = r_s - _time.time() if r_s > 1e9 else r_s
                    if con > 120:
                        _kill(api, f"het quota, mo lai sau {con / 60:.0f} phut")
                    elif con > 0:
                        _time.sleep(con + 1)
            except ValueError:
                pass
            return body
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403):
                _kill(api, f"HTTP {e.code} (key sai/het han/bi chan)")
                raise ApiDown(f"{api}: HTTP {e.code}")
            if e.code == 429:
                rt.n429 += 1
                ra = e.headers.get("Retry-After") if e.headers else None
                try:
                    wait = float(ra)
                except (TypeError, ValueError):
                    wait = 5.0 * (2 ** attempt)          # 5, 10, 20, 40
                with rt.lock:
                    rt.gap = min(rt.gap * 2, 20.0)       # giam tan suat ca phien
                if wait > 120 or rt.n429 >= 8:
                    _kill(api, f"429 lap lai ({rt.n429} lan)")
                    raise ApiDown(f"{api}: 429")
                print(f"  [breaker] {api} 429 -> doi {wait:.0f}s, gap {rt.gap:.1f}s")
                _time.sleep(wait)
                continue
            if e.code >= 500:
                _time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except ApiDown:
            raise
        except Exception as e:
            last = e
            _time.sleep(1.5 * (attempt + 1))
    raise last


def breaker_report():
    for api, rt in _RT.items():
        if rt.dead or rt.n429:
            print(f"  [breaker] {api}: {'TAT - ' + rt.dead if rt.dead else 'song'}"
                  f", 429 x{rt.n429}")


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


def theme_index(keyword, min_score=0.6):
    """Tra ve (theme_idx, score) cho keyword BAT KY.

    Keyword nguoi viet tu go (vd "nvidia chip factory") khong nam trong
    STOCK_THEMES; so khop tuyet doi se tra ve None -> pool chi 1 keyword ->
    het file sau 2-3 cell -> phai lay hinh theme khac (dut mach). Nen o day
    do do trung token de van gan duoc vao theme gan nhat.

    Nguong 0.6 (ban cu 0.15): STOCK_THEMES toan keyword AI/robot cua kenh
    commentary cong nghe. Voi kenh lich su, "chinese city street at night" trung
    dung token "city" -> 0.25 -> du qua nguong cu -> pool nuot ca theme "AI city
    futuristic" va video Tan Thuy Hoang mo ra canh robot. 0.6 doi trung qua nua
    so tu, tuc la keyword that su cung chu de moi duoc gop nhom.
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
    giat = []     # clip giat (la_giat): chi dung khi khong con gi khac
    for kw in theme_keywords(keyword):
        for f in stock_files(root, kw, bo_giat=False):
            if len(pool) >= max_files:
                break
            if f in seen_path:
                continue
            seen_path.add(f)
            if la_giat(root, f):
                giat.append(f)
                continue
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
    if not pool and giat:
        # kho chi con clip giat -> van dung (giat con hon card trong), nhung bao
        print(f"  WARN '{keyword}': chi co clip giat ({len(giat)}), van dung")
        pool = giat[:max_files]
    return pool


def cell_pool(root, cell, max_files=40):
    """Pool cho MOT cell: (list file, tap file tu lieu that cua ent).

    Cell co ent -> anh tu lieu cua chinh thuc the dung dau, keyword canh noi
    duoi lam duong lui. Khong co ent -> y nhu stock_pool(keyword).
    """
    kw, ent = cell_kw(cell), cell_ent(cell)
    ent_files = []
    if ent:
        seen = set()
        for f in stock_files(root, ent_key(ent)):
            if la_giat(root, f):      # anh Ken Burns khong bao gio bi loai
                continue
            h = _content_hash(f)
            if h and h in seen:
                continue
            if h:
                seen.add(h)
            ent_files.append(f)
    rest = stock_pool(root, kw, max_files) if kw else []
    pool = ent_files + [f for f in rest if f not in set(ent_files)]
    return pool[:max(max_files, len(ent_files))], set(ent_files)


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
        try:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", ss,
                            "-i", f, "-frames:v", "1", "-vf", "scale=48:27",
                            png], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            return None
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
        # timeout khong duoc lam sap render: may dang ban (encode song song)
        # thi ffmpeg doc 1 frame file 60 MB co the qua 8s — do 01/10.
        try:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", ss, "-i", f,
                            "-frames:v", "1", "-vf", "scale=8:8", png],
                           capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            return None
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


_VIDEO_FILES = {}


def is_still(root, f):
    """True neu f la shot Ken Burns dung tu ANH (kho photo/wiki), False neu la
    clip video tai ve (pexels/pixabay/coverr). Phan biet bang _urls.json: moi
    clip video tai ve deu ghi url -> ten file o do; anh thi khong. Khong dua vao
    duration (clip Pexels co cai 8s, ngang shot anh 9s)."""
    d = _stock_dir(root)
    if d not in _VIDEO_FILES:
        names = set()
        try:
            with open(os.path.join(d, "_urls.json"), encoding="utf-8") as fh:
                names = set(json.load(fh).values())
        except Exception:
            pass
        _VIDEO_FILES[d] = names
    return os.path.basename(f) not in _VIDEO_FILES[d]


# ---------------------------------------------------------------------------
# DO MUOT clip (chong "video nen giat"). Do 13/10 tren 43 clip kn-02:
#  - Giat that = buoc khung KHONG DEU: cu 4 khung lai 1 khung nhay gap doi
#    (clip 30fps bi shrink_clip ep fps=24 -> roi 1/5 khung, vd 899b2899703d,
#    0b6f6817c7b9) hoac nguon Pexels 25fps tu ban da lech nhip (be998586c2b7,
#    de66512acfe8), hoac khung dung lap (dup).
#  - scene_score cua ffmpeg la min(mafd, |mafd - mafd truoc|) tuc DAO HAM cua
#    chuyen dong: chuoi "0.04 0.04 0 0" chinh la 1 khung nhay vot roi tro lai,
#    khong han la khung dung.
# Cach do: giai ma ~4s giua clip o fps GOC (khong ep fps), xam 192x108, lay
# d_i = trung binh |khung i - khung i-1|. So voi trung vi truot 9 khung:
#   dup = d_i < 0.35*trung_vi   (khung gan nhu trung khung truoc)
#   jud = d_i > 1.6*trung_vi    (khung nhay coc)
# diem = dup + jud (ti le khung bat thuong). Clip gan nhu dung yen (trung vi
# < 0.25) khong danh gia duoc -> diem 0. Clip muot do duoc <= 0.06-0.08, clip
# giat 0.12-0.52 -> NGUONG 0.11 (env STOCK_GIAT_NGUONG), KEM dieu kien lap deu
# (chu_ky >= 0.3) hoac >= 5% khung dung lap (dup) — xem giat_theo_diem. Rung
# tay / canh dong ngau nhien (chu_ky < 0.3, khong dup) KHONG tinh la giat.
# ---------------------------------------------------------------------------
MUOT_FILE = "_do_muot.json"      # cache diem do (ten -> {size, mtime, diem..})
GIAT_FILE = "_giat_den.json"     # danh sach den do auto/quet_stock_giat.py ghi
GIAT_NGUONG = float(os.environ.get("STOCK_GIAT_NGUONG", "0.11"))
_MUOT_W, _MUOT_H = 192, 108
_MUOT_LOCK = _th.Lock()
_MUOT = {}        # stock_dir -> dict cache
_GIAT = {}        # stock_dir -> dict blacklist
_MUOT_DIRTY = {}  # stock_dir -> so ban ghi chua luu


_FPS_CACHE = {}


def src_fps(path):
    """Frame rate goc (r_frame_rate) cua video, 0.0 neu khong doc duoc.
    Cache theo (duong dan, mtime) — render goi moi doan 6s."""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return 0.0
    if key not in _FPS_CACHE:
        _FPS_CACHE[key] = _src_fps(path)
    return _FPS_CACHE[key]


def _src_fps(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=r_frame_rate", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30)
        a, _, b = r.stdout.strip().split("\n")[0].partition("/")
        return float(a) / float(b or 1)
    except Exception:
        return 0.0


def _dur_quick(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def do_muot(path, sample=4.0):
    """Do do muot 1 clip. -> dict {diem, dup, jud, chuyen_dong, fps, n} hoac
    None neu khong giai ma duoc. diem cang cao cang giat (xem ghi chu tren).
    Chay ~0.3-0.6s/clip (chi giai ma `sample` giay, khung xam nho)."""
    try:
        import numpy as np
    except ImportError:
        return None
    dur = _dur_quick(path)
    if dur <= 0:
        return None
    ss = max(0.0, dur / 2 - sample / 2)
    W, H = _MUOT_W, _MUOT_H
    cmd = ["ffmpeg", "-v", "error", "-threads", "2", "-ss", f"{ss:.2f}",
           "-i", path, "-t", f"{sample:.2f}", "-an",
           "-vf", f"scale={W}:{H}:flags=area,format=gray",
           "-f", "rawvideo", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=120).stdout
    except Exception:
        return None
    a = np.frombuffer(raw, np.uint8)
    n = len(a) // (W * H)
    if n < 12:
        return None
    a = a[:n * W * H].reshape(n, H, W).astype(np.int16)
    d = np.abs(np.diff(a, axis=0)).mean(axis=(1, 2))
    med = float(np.median(d))
    out = {"fps": round(src_fps(path), 3), "n": int(len(d)),
           "chuyen_dong": round(med, 3)}
    if med < 0.25:                      # gan nhu dung yen -> khong co gi de giat
        out.update(diem=0.0, dup=0.0, jud=0.0, chu_ky=0.0)
        return out
    k = 4
    pad = np.pad(d, k, mode="edge")
    loc = np.array([np.median(pad[i:i + 2 * k + 1]) for i in range(len(d))])
    # san tuyet doi: clip chuyen dong cham (trung vi 0.3) thi nhieu nen/keyframe
    # cung du lam ti le vuot 1.6 lan -> bat nham
    dup = float(np.mean((d < 0.35 * loc) & (loc - d > 0.15)))
    jud = float(np.mean((d > 1.6 * loc) & (d - loc > 0.2)))
    # CHU KY: giat that lap deu (30->24: cu 4 khung; dup: cu 5 khung), con
    # rung tay/canh dong thi ngau nhien. Tu tuong quan cua phan du d/loc o do
    # tre 2..6 khung: clip giat 0.35-0.90, clip muot -0.05-0.26 (do 13/10).
    r = np.clip(d / np.maximum(loc, 0.05) - 1, -1, 3)
    r = r - r.mean()
    v = float((r * r).mean())
    ac = max(float((r[:-L] * r[L:]).mean()) / v for L in range(2, 7)) if v > 1e-9 else 0.0
    out.update(diem=round(dup + jud, 4), dup=round(dup, 4), jud=round(jud, 4),
               chu_ky=round(ac, 3))
    return out


GIAT_CHU_KY = 0.3      # tu tuong quan toi thieu de goi la giat lap deu
GIAT_DUP = 0.05        # >=5% khung DUNG (trung khung truoc) = khung khung, giat
                       # du khong deu (vd nguon 50fps ep 24: 00e12a265380)
MUOT_VER = 2


def giat_theo_diem(r, nguong=None):
    """Quyet dinh giat tu ket qua do_muot."""
    if not r:
        return False
    nguong = GIAT_NGUONG if nguong is None else nguong
    diem = r.get("diem", 0.0)
    return diem >= nguong and (r.get("chu_ky", 1.0) >= GIAT_CHU_KY
                               or r.get("dup", 0.0) >= GIAT_DUP)


def _sig_of(path):
    st = os.stat(path)
    return st.st_size, round(st.st_mtime, 2)


def _muot_cache(d):
    if d not in _MUOT:
        try:
            with open(os.path.join(d, MUOT_FILE), encoding="utf-8") as fh:
                _MUOT[d] = json.load(fh)
        except Exception:
            _MUOT[d] = {}
    return _MUOT[d]


def _giat_list(d):
    if d not in _GIAT:
        try:
            with open(os.path.join(d, GIAT_FILE), encoding="utf-8") as fh:
                _GIAT[d] = json.load(fh).get("files", {})
        except Exception:
            _GIAT[d] = {}
    return _GIAT[d]


def save_muot(root=None, d=None):
    """Ghi cache diem muot xuong assets/stock/_do_muot.json (atomic)."""
    d = d or _stock_dir(root)
    with _MUOT_LOCK:
        if not _MUOT_DIRTY.get(d):
            return
        data = dict(_muot_cache(d))
        _MUOT_DIRTY[d] = 0
    p = os.path.join(d, MUOT_FILE)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, p)


def muot_of(path, measure=True):
    """Diem muot cua file (co cache theo size+mtime). measure=False: chi doc
    cache, chua do thi None."""
    d = os.path.dirname(os.path.abspath(path))
    name = os.path.basename(path)
    try:
        size, mt = _sig_of(path)
    except OSError:
        return None
    with _MUOT_LOCK:
        rec = _muot_cache(d).get(name)
    if (rec and rec.get("size") == size and rec.get("mtime") == mt
            and rec.get("v") == MUOT_VER):
        return rec
    if not measure:
        return None
    r = do_muot(path)
    if r is None:
        return None
    r.update(size=size, mtime=mt, v=MUOT_VER)
    with _MUOT_LOCK:
        _muot_cache(d)[name] = r
        _MUOT_DIRTY[d] = _MUOT_DIRTY.get(d, 0) + 1
        dirty = _MUOT_DIRTY[d]
    if dirty >= 50:
        try:
            save_muot(d=d)
        except Exception:
            pass
    return r


def loc_giat_bat():
    """Bo loc clip giat bat MAC DINH; STOCK_LOC_GIAT=0 de tat."""
    return os.environ.get("STOCK_LOC_GIAT", "1") != "0"


def la_giat(root, f, measure=True):
    """True neu f la CLIP VIDEO giat (danh sach den hoac diem >= nguong).

    Shot Ken Burns tu anh (is_still) KHONG bi loai o day: anh tu lieu cua thuc
    the la noi dung khong thay duoc, giat cua no la do zoompan (wiki_images),
    phai sua o buoc dung shot chu khong vut anh."""
    if not loc_giat_bat() or not f or not os.path.exists(f):
        return False
    try:
        if is_still(root, f):
            return False
    except Exception:
        return False
    d = os.path.dirname(os.path.abspath(f))
    name = os.path.basename(f)
    den = _giat_list(d).get(name)
    if den:
        try:
            if den.get("size") in (None, os.path.getsize(f)):
                return True
        except OSError:
            pass
    return giat_theo_diem(muot_of(f, measure=measure))


def prewarm_sigs(files, workers=None):
    """Tinh _content_hash + color_sig cho cac file CHUA co cache, song song.

    Ket qua y het goi tuan tu (cung ham, cung cache) — chi doi thu tu. File da
    co cache khong ton gi ngoai mot lan doc file nho.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _need(f):
        for ext in (".h", ".c"):
            try:
                with open(f + ext, encoding="utf-8") as fh:
                    lines = fh.read().split("\n")
                if len(lines) < 2 or float(lines[1]) != os.path.getmtime(f):
                    return True
            except Exception:
                return True
        return False

    def _need_muot(f):
        # clip VIDEO chua co diem muot (anh Ken Burns khong can do)
        if not loc_giat_bat():
            return False
        try:
            root_f = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(f))))
            return (not is_still(root_f, f)) and muot_of(f, measure=False) is None
        except Exception:
            return False

    todo = [f for f in dict.fromkeys(files)
            if os.path.exists(f) and (_need(f) or _need_muot(f))]
    if not todo:
        return 0
    workers = workers or int(os.environ.get("SIG_JOBS")
                             or max(2, min(12, (os.cpu_count() or 8) - 2)))
    print(f"  cache hash/mau/muot: {len(todo)} file, {workers} luong song song")

    def _one(f):
        try:
            _content_hash(f)
            color_sig(f)
        except Exception:
            pass
        try:
            if _need_muot(f):
                muot_of(f)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_one, todo))
    for d in list(_MUOT_DIRTY):
        try:
            save_muot(d=d)
        except Exception:
            pass
    return len(todo)


def ahash(f):
    """Hash cam nhan (average hash 16x9 xam tai 0s/2s/4s, 432 bit) — bat duoc
    CUNG MOT CLIP tai tu hai nguon / hai do phan giai, thu _content_hash (md5
    tung byte PNG) bo lot. Do 16/10/2026: demo Tran Hung Dao co hai cell lien
    nhau (hai keyword "fisherman dugout canoe ...") cung mot canh thuyen, dung
    ngay hai ben diem chuyen chuong. Cache .a canh file."""
    cache = f + ".a"
    try:
        if os.path.exists(cache):
            with open(cache, encoding="utf-8") as fh:
                data = fh.read().split("\n")
            if len(data) >= 2 and float(data[1]) == os.path.getmtime(f):
                return data[0]
    except Exception:
        pass
    import numpy as np
    bits = ""
    for ss in ("0", "2", "4"):
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", ss, "-i", f,
                                "-frames:v", "1", "-vf", "scale=16:9,format=gray",
                                "-f", "rawvideo", "-"], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            return None
        a = np.frombuffer(r.stdout, dtype=np.uint8)
        if a.size != 144:
            if not bits:
                return None
            a = np.frombuffer(bytes.fromhex("00" * 144), dtype=np.uint8)
        bits += "".join("1" if v > a.mean() else "0" for v in a)
    try:
        with open(cache, "w", encoding="utf-8") as fh:
            fh.write(bits + "\n" + str(os.path.getmtime(f)))
    except Exception:
        pass
    return bits


def near_dup(f, g, thr=0.18):
    """True neu f va g gan nhu cung mot canh (hamming < thr)."""
    if f == g:
        return True
    a, b = ahash(f), ahash(g)
    if not a or not b or len(a) != len(b):
        return False
    return sum(x != y for x, y in zip(a, b)) / len(a) < thr


def color_dist(a, b):
    """0 = cung tong mau, ~1 = nguoc han. Thieu du lieu -> 0.5 (trung tinh)."""
    if not a or not b or len(a) != len(b):
        return 0.5
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _pixabay_search(key, keyword, per=50):
    """Tra ve list (url, width, height, mo_ta) — uu tien video 16:9 chay ngang.

    `mo_ta` la chu de _rel_filter() cham diem sai thoi. Ban cu vut het chu di
    nen video khong co bo loc nao ngoai do phan giai.
    """
    q = urllib.parse.quote(keyword)
    url = (f"https://pixabay.com/api/videos/?key={key}&q={q}"
           f"&video_type=film&per_page={per}&safesearch=true"
           f"&min_width={MIN_W}&min_height={MIN_H}&order=popular")
    data = json.loads(api_get("pixabay", url).decode("utf-8"))
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
        # ban NHO NHAT con >= 1920 (khong phai upscale, khong tai 4K cho khung
        # 1080p — 4K nang gap 4 va shrink_clip cung ha ve 1080p)
        hd = [v for v in cands if (v.get("width") or 0) >= 1920]
        best = (min(hd, key=lambda v: v["width"] * (v.get("height") or 0)) if hd
                else max(cands, key=lambda v: (v.get("width") or 0)
                         * (v.get("height") or 0)))
        out.append((best["url"], best.get("width", 0), best.get("height", 0),
                    h.get("tags", "")))
    return out


def _pexels_search(key, keyword, per=50):
    q = urllib.parse.quote(keyword)
    url = (f"https://api.pexels.com/videos/search?query={q}&per_page={per}"
           f"&orientation=landscape&size=large")
    data = json.loads(api_get("pexels", url,
                              headers={"Authorization": key}).decode("utf-8"))
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
        out.append((best["link"], best.get("width", 0), best.get("height", 0),
                    _pexels_slug(v.get("url", ""))))
    return out


def _pexels_slug(page_url):
    """API video cua Pexels khong co truong mo ta — chu duy nhat nam o slug URL.

    https://www.pexels.com/video/a-woman-in-a-red-dress-dancing-12345/
      -> "a woman in a red dress dancing"
    Bo cum so cuoi (id video) de khong lam nhieu diem.
    """
    slug = (page_url or "").rstrip("/").rsplit("/", 1)[-1]
    tu = [t for t in slug.split("-") if t and not t.isdigit()]
    return " ".join(tu)


def _coverr_search(key, keyword, per=30):
    """Coverr — thu vien nho (vai nghin clip) nhung quay dep, it "stock-y".

    Tra ve ban 1080p (urls.mp4). max_width/max_height la kich thuoc THAT cua
    ban goc: nhieu clip cu chi 1024x512 nen phai loc, khong tin ten "1080p".
    Key demo: 50 request/gio — cache trong assets/stock lo phan con lai.
    """
    q = urllib.parse.quote(keyword)
    url = (f"https://api.coverr.co/videos?query={q}&page_size={per}"
           f"&urls=true&api_key={key}")
    data = json.loads(api_get("coverr", url).decode("utf-8"))
    out = []
    for v in data.get("hits", []):
        u = (v.get("urls") or {}).get("mp4_download") or (v.get("urls") or {}).get("mp4")
        w, h = v.get("max_width") or 0, v.get("max_height") or 0
        if not u or w < MIN_W or h < MIN_H:
            continue
        # max_width/max_height la kich thuoc BAN GOC, nhung URL Coverr tra ve la
        # ban "1080p.mp4". Khai bao 3840x2160 cho mot file 1080p se lam
        # _pick_landscape cham no diem 4K (1.00) va xep tren clip Pexels 4K that.
        if "/1080p." in u and h > 1080:
            w, h = int(round(1080 * (w / h))), 1080
        out.append((u, w, h, " ".join(filter(None, [
            v.get("title", ""), v.get("description", ""),
            " ".join(v.get("tags") or [])]))))
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
        w, h = it[1], it[2]
        return w and h and w >= MIN_W and h >= MIN_H and (w / h) >= 1.5

    def score(it):
        w, h = it[1], it[2]
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


def fetch_stock(root, cfg, force=False, cap=6, workers=6):
    """Tai video stock cho cac cell type 'stock' — CHI phan con thieu.

    So file moi keyword = kw_demand() (thoi luong cell / SHOT_SEC + du 1, tru
    file da co o moi kho: anh photo/wiki da tai thi video khong tai trung).
    Ban cu tai 6 file x 3 API cho moi keyword bat ke cell dai bao nhieu.
    Tai song song theo keyword; moi API co semaphore + nhip rieng (_RT).
    """
    import time as _t
    from concurrent.futures import ThreadPoolExecutor, as_completed
    cells = stock_cells(cfg)
    if not cells:
        print("(rong) config khong co cell type 'stock'")
        return 0
    pk, px = _keys()
    cv = _key("COVERR_API_KEY")
    if not pk and not px and not cv:
        print("WARN: thieu PIXABAY/PEXELS/COVERR_API_KEY trong tool/.env — bo qua")
        return 0
    need = {k: n for k, n in kw_demand(root, cfg, cap=cap).items() if n > 0}
    if force:
        need = {cell_kw(c): n_files_for(cell_seconds(root, c), cap)
                for c in cells if cell_kw(c)}
    total_need = sum(need.values())
    print(f"stock: {len(need)} keyword con thieu, can {total_need} file "
          f"(cap {cap}/keyword, {workers} luong)")
    if not need:
        return 0
    t0 = _t.monotonic()
    n = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_keyword, root, kw, cnt, pk, px, force, cv): kw
                for kw, cnt in need.items()}
        for fu in as_completed(futs):
            try:
                n += fu.result()
            except Exception as e:
                print(f"  ERR {futs[fu]}: {e}")
    breaker_report()
    print(f"stock: tai {n}/{total_need} file trong {_t.monotonic() - t0:.0f}s")
    enforce_cache_limit(root, protect=files_of_config(root, cfg))
    return n


SEARCHERS = {
    "pixabay": _pixabay_search,
    "pexels": _pexels_search,
    "coverr": _coverr_search,
}

# Xem stock_photo.TOP_TRUST: may ket qua dau moi nguon duoc tin du khong khop chu.
# Video de hon anh mot bac (4 thay vi 6): mo ta video coc hon mo ta anh that,
# nhung mot clip sai thoi hai hon mot anh sai thoi — no dong day 8 giay.
# 05/10/2026: ha 4 -> 0. Do tren tran-thu-do: 59/94 clip Pexels sai (anh Assad,
# tran nha tho baroque, san bong...) deu la ket qua hang 0-2 KHONG khop chu nao.
# Gio clip phai co it nhat 1 tu khoa khop moi duoc giu. Doi lai bang VIDEO_TOP_TRUST=4.
VIDEO_TOP_TRUST = int(os.environ.get("VIDEO_TOP_TRUST", "0"))


def _rel_filter(keyword, items, api):
    """Loai clip sai thoi / sai vung — cung luat da dung cho anh.

    Ban truoc KHONG co buoc nay: _pick_landscape chi xet do phan giai va ti le
    khung, nen "Tang dynasty empress" tra ve mot co gai cosplay quay 4K thi clip
    do duoc cham diem CAO NHAT (4K = 1.00) va chac chan len song. Day la ly do
    queue.yml phai tat han `stock` cho video ke su.

    Tat bang STOCK_STRICT=0 (hoac PHOTO_STRICT=0 de tat ca anh lan video).
    """
    if os.environ.get("STOCK_STRICT", os.environ.get("PHOTO_STRICT", "1")) == "0":
        return items
    # Import tre: stock_photo `import stock as ST` o dau file nen import nguoc
    # o muc module se thanh vong tron.
    try:
        from stock_photo import _rel_score
    except Exception:
        return items

    giu, bo = [], 0
    for rank, it in enumerate(items):
        text = it[3] if len(it) > 3 else ""
        s = _rel_score(keyword, text)
        if s < 0:                       # dau hieu thoi nay / sai vung -> loai han
            bo += 1
            continue
        if s >= 1 or rank < VIDEO_TOP_TRUST:
            giu.append(it)
        else:
            bo += 1
    if bo:
        print(f"  (loc) {api} '{keyword}': bo {bo}/{len(items)} clip khong khop")
    return giu


def _free_idx(root, api, kw, start=0):
    """idx trong dau tien cua (kho, keyword) — khong ghi de file cu."""
    i = start
    while i < MAX_IDX:
        if not os.path.exists(_cache_path(root, api, kw, i)[0]):
            return i
        i += 1
    return None


_URL_LOCK = __import__("threading").Lock()


def _url_registry(root):
    """assets/stock/_urls.json: url -> ten file. Chong tai lai CUNG mot clip vao
    idx khac khi chay bu (ban cu khong nho url nen chi dua vao thu tu API)."""
    p = os.path.join(_stock_dir(root), "_urls.json")
    try:
        with open(p, encoding="utf-8") as f:
            return p, json.load(f)
    except Exception:
        return p, {}


def _url_mark(root, url, path):
    with _URL_LOCK:
        p, reg = _url_registry(root)
        reg[url] = os.path.basename(path)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f)
        os.replace(tmp, p)


def _fetch_keyword(root, kw, count, pk, px, force, cv=None):
    """Tai TONG CONG `count` video cho 1 keyword, lan luot Pixabay -> Pexels ->
    Coverr, du thi dung.

    Ban cu tai `count` file cho MOI nguon (x3) va van goi Coverr du no da tra 403
    ca chuc lan. Nguon da bi breaker tat thi bo qua, khong ton request.
    Coverr chi an truy van ngan (xem CLAUDE.md) nen chi goi khi keyword <= 3 tu.
    """
    got = 0
    if cv is None:
        cv = _key("COVERR_API_KEY")
    _p, reg = _url_registry(root)
    known = set(reg)
    for api, key in (("pixabay", pk), ("pexels", px), ("coverr", cv)):
        if got >= count:
            break
        if not key or not api_alive(api):
            continue
        if api == "coverr" and len(kw.split()) > 3:
            continue
        try:
            items = SEARCHERS[api](key, kw)
        except ApiDown:
            continue
        except Exception as e:
            print(f"  WARN {api} '{kw}': {e}")
            continue
        # Loc TRUOC _pick_landscape: bo loc dung thu hang do chinh API xep
        # (VIDEO_TOP_TRUST), ma _pick_landscape sap xep lai theo do phan giai.
        items = _rel_filter(kw, items, api)
        items = _pick_landscape(items)
        if not items:
            continue
        seen_url, picked = set(), []
        for it in items:
            if it[0] in seen_url or it[0] in known:
                continue
            seen_url.add(it[0])
            picked.append(it)
            if len(picked) >= count - got:
                break
        rt = _RT[api]
        idx = 0
        for url, w, h in ((p[0], p[1], p[2]) for p in picked):
            idx = _free_idx(root, api, kw, idx)
            if idx is None:
                break
            path, _ = _cache_path(root, api, kw, idx)
            idx += 1
            try:
                with rt.sem:
                    _download(url, path)
            except Exception as e:
                print(f"  WARN tai that bai '{kw}' {api}: {e}")
                continue
            if not _verify_hd(path):
                continue
            # cat/nen ngay khi tai xong: clip 55s 41 Mbps -> 18s ~7 Mbps
            try:
                with rt.sem:
                    shrink_clip(path)
            except Exception as e:
                print(f"  WARN thu gon {os.path.basename(path)}: {e}")
            _url_mark(root, url, path)
            print(f"  + {api} {w}x{h} '{kw}' -> {os.path.basename(path)}")
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
    d = _stock_dir(root)
    files = [f for f in os.listdir(d) if f.endswith(".mp4")]
    # hash moi file (dung .h cache neu co)
    by_h = {}
    for f in files:
        h = _content_hash(os.path.join(d, f))
        if h is None:
            continue  # khong hash duoc -> khong dong toi
        by_h.setdefault(h, []).append(os.path.join(d, f))
    # Ten file -> (kho, keyword, idx). Keyword lay tu STOCK_THEMES + MOI
    # config.json trong videos/ (ca khoa "ent:<ten>"). Ban cu chi co
    # STOCK_THEMES (keyword AI) nen keyword lich su khong bao gio map duoc.
    import glob as _glob
    import hashlib as _hl
    kws = {k for g in STOCK_THEMES for k in g}
    for cp in _glob.glob(os.path.join(KIT_ROOT, "videos", "*", "config.json")):
        try:
            with open(cp, encoding="utf-8") as fh:
                for c in stock_cells(json.load(fh)):
                    if cell_kw(c):
                        kws.add(cell_kw(c))
                    if cell_ent(c):
                        kws.add(ent_key(cell_ent(c)))
        except Exception:
            continue
    fmap = {}  # filename-without-ext -> (api, kw, idx)
    for kw in sorted(kws):
        for api in APIS:
            for idx in range(MAX_IDX):
                h = _hl.md5(f"{api}|{kw}|{idx}".encode()).hexdigest()[:12]
                fmap.setdefault(h, (api, kw, idx))
    # So content unique CUA TUNG keyword. Ban cu vong lap khong loc file theo
    # keyword -> moi keyword deu dem ra tong so content cua ca kho (cung mot so),
    # nen "uu tien giu file cua keyword doi" khong bao gio co tac dung.
    kw_contents = {}
    for h, lst in by_h.items():
        for pth in lst:
            kw = fmap.get(os.path.basename(pth)[:-4], (None, None, None))[1]
            if kw:
                kw_contents.setdefault(kw, set()).add(h)
    kw_unique = {kw: len(v) for kw, v in kw_contents.items()}

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
            # .c = cache chu ky mau (color_sig) — ban cu bo sot, de lai rac
            for ext in (".h", ".c", ".0.png", ".2.png", ".4.png",
                        ".c0.png", ".c2.png", ".c4.png"):
                if os.path.exists(p + ext):
                    os.remove(p + ext)
        except OSError:
            pass
    print(f"prune: xoa {len(drop)} file trung (~{freed:.0f} MB). "
          f"Giu {len(keep)} content unique.")
    return len(keep), len(drop), freed


# ---------------------------------------------------------------------------
# Thu gon kho. Do 01/10: assets/stock 21,5 GB / 2347 file; file to nhat 282 MB
# cho 55s 1080p (~41 Mbps), shot Ken Burns ultrafast 26-66 MB cho 9s — trong
# khi render chi dung 6-9s moi file va tu encode lai crf14 o 24 fps.
# ---------------------------------------------------------------------------
SHRINK_MAX_SEC = 18.0     # render dung 1-3 doan 6s moi file -> 18s la du
SHRINK_CRF = 22
SHRINK_MAX_BPS = 7e6      # duoi 7 Mbps + <= 1080p + <= 20s thi khong dong vao
CACHE_GB_DEFAULT = 6.0


def _caches_of(path):
    return [path + e for e in (".h", ".c", ".0.png", ".2.png", ".4.png",
                               ".c0.png", ".c2.png", ".c4.png")]


def needs_shrink(path):
    """-> (can thu gon?, duration, h). Doc bang ffprobe."""
    try:
        from probe import streams, duration
        dur = duration(path)
        v = streams(path).get("video") or {}
    except (SystemExit, Exception):
        return False, 0.0, 0
    h = v.get("h") or 0
    size = os.path.getsize(path)
    bps = size * 8 / max(dur, 0.1)
    need = (h > 1080) or (dur > SHRINK_MAX_SEC + 2) or (bps > SHRINK_MAX_BPS)
    return need, dur, h


def fps_blend_can(r, out=24):
    """True neu doi nhip r -> out bang fps= (roi/lap khung) se GIAT thay ro:
    30/29.97/60/59.94 -> 24 roi 1 trong 5 khung (buoc 1-1-1-2). Nguon 24/48/
    120 (boi so sach) va 25/50/100 (25->24 chi lech 1 khung/giay, do 13/10 diem
    giat van 0.00-0.06) giu fps= nhu cu. STOCK_FPS_BLEND=0 de tat."""
    if os.environ.get("STOCK_FPS_BLEND", "1") == "0" or r <= 0:
        return False
    for base in (out, 25):
        q = r / base
        if abs(q - round(q)) < 0.02 and round(q) >= 1:
            return False
    return r > out


def _shrink_fps(r):
    """Filter fps cho shrink_clip -> chuoi "fps=...," hoac "".

    Ban cu ep fps=24 cho MOI nguon. Do 13/10: nguon Pexels 30fps (va 60fps chua
    noi dung 30) ep xuong 24 bi roi 1/5 khung -> cu 4 khung co 1 khung nhay coc
    (899b2899703d, 0b6f6817c7b9, 25529c68aded, 3bcc2f970d01, ca050c78c2c1:
    diem giat 0.13-0.24), va hong VINH VIEN vi file goc bi ghi de. Nay giu
    nhip goc; chi chia doi nguon >= 47fps (60->30, 50->25: roi deu 1/2 khung,
    khong lech) va ha nguon >62fps ve boi so sach (120->24, 100->25). Doi ve 24
    la viec cua render (_stock_scale_chain: tron khung, khong roi khung)."""
    if r <= 0 or r <= 31:
        return ""
    if r <= 62:
        return f"fps={r / 2:.5f},"
    for base in (24, 25, 30):
        if abs(r / base - round(r / base)) < 0.01:
            return f"fps={base},"
    return "fps=30,"


def shrink_clip(path, max_sec=SHRINK_MAX_SEC, crf=SHRINK_CRF, force=False):
    """Cat con <= max_sec (doan GIUA — dau/cuoi clip stock hay la fade, logo),
    dua ve 1920x1080 (giu nhip goc, xem _shrink_fps), bo tieng, x264 veryfast
    crf22. Giu nguyen TEN file
    (hash) nen render/plan van tim thay. -> (byte cu, byte moi) hoac None."""
    need, dur, _h = needs_shrink(path)
    if not need and not force:
        return None
    old = os.path.getsize(path)
    ss = max(0.0, (dur - max_sec) / 2) if dur > max_sec + 2 else 0.0
    tmp = path + ".shrink.mp4"
    vf = ("scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,"
          "crop=1920:1080,setsar=1," + _shrink_fps(src_fps(path)) + "format=yuv420p")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{ss:.2f}", "-i", path,
           "-t", f"{max_sec:.2f}", "-vf", vf, "-an", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", str(crf),
           # tran bitrate: clip mua/hat nhieu (do 01/10: 282 MB/55s) crf22 van
           # ra 28 Mbps; 5 Mbps x 18s = ~11 MB, render encode lai crf14 sau.
           "-maxrate", "5M", "-bufsize", "10M", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 10_000
    if ok:
        try:
            from probe import duration
            ok = duration(tmp) > 1.0
        except (SystemExit, Exception):
            ok = False
    if not ok or os.path.getsize(tmp) >= old:
        if os.path.exists(tmp):
            os.remove(tmp)
        return None
    st = os.stat(path)
    os.replace(tmp, path)
    # giu atime (LRU) — mtime moi lam .h/.c tu tinh lai, nhung xoa luon cho sach
    try:
        os.utime(path, (st.st_atime, os.path.getmtime(path)))
    except OSError:
        pass
    for c in _caches_of(path):
        if os.path.exists(c):
            try:
                os.remove(c)
            except OSError:
                pass
    return old, os.path.getsize(path)


def touch_used(path):
    """Danh dau file vua duoc render chon (atime = bay gio, GIU mtime vi .h/.c
    cache so mtime). enforce_cache_limit xoa theo atime cu nhat."""
    try:
        os.utime(path, (_time.time(), os.path.getmtime(path)))
    except OSError:
        pass


def files_of_config(root, cfg):
    """Moi ten file kho CO THE thuoc config nay (moi kho, moi idx, keyword+ent)."""
    out = set()
    for c in stock_cells(cfg):
        keys = [k for k in (cell_kw(c),) if k]
        if cell_ent(c):
            keys.append(ent_key(cell_ent(c)))
        for k in keys:
            for api in APIS:
                for i in range(MAX_IDX):
                    out.add(_cache_path(root, api, k, i)[0])
    return out


def enforce_cache_limit(root=None, protect=(), limit_gb=None, dry_run=False,
                        log=print):
    """Giu kho <= STOCK_CACHE_GB (mac dinh 6). Vuot -> xoa file atime cu nhat,
    tru file trong `protect`. File hardlink (cung inode) tinh dung 1 lan va
    chi giai phong khi xoa het ten. -> (byte truoc, byte sau, so file xoa)."""
    if limit_gb is None:
        try:
            limit_gb = float(os.environ.get("STOCK_CACHE_GB", CACHE_GB_DEFAULT))
        except ValueError:
            limit_gb = CACHE_GB_DEFAULT
    d = _stock_dir(root)
    protect = {os.path.normcase(os.path.abspath(p)) for p in protect}
    groups = {}   # inode -> [names], size, atime
    for f in os.listdir(d):
        if not f.endswith(".mp4") or f.endswith(".shrink.mp4"):
            continue
        p = os.path.join(d, f)
        try:
            st = os.stat(p)
        except OSError:
            continue
        g = groups.setdefault((st.st_dev, st.st_ino) if st.st_ino else p,
                              {"names": [], "size": st.st_size, "atime": 0.0})
        g["names"].append(p)
        g["atime"] = max(g["atime"], st.st_atime)
    total = sum(g["size"] for g in groups.values())
    limit = limit_gb * 1e9
    before = total
    n_del = 0
    if total <= limit:
        return before, total, 0
    cand = [g for g in groups.values()
            if not any(os.path.normcase(os.path.abspath(n)) in protect
                       for n in g["names"])]
    cand.sort(key=lambda g: g["atime"])
    for g in cand:
        if total <= limit:
            break
        total -= g["size"]
        n_del += len(g["names"])
        if dry_run:
            continue
        for n in g["names"]:
            for x in [n] + _caches_of(n):
                try:
                    if os.path.exists(x):
                        os.remove(x)
                except OSError:
                    pass
    log(f"kho stock: {before / 1e9:.2f} GB -> {total / 1e9:.2f} GB "
        f"(tran {limit_gb:g} GB, {'se ' if dry_run else ''}xoa {n_del} file LRU)")
    if total > limit:
        log(f"  WARN file duoc bao ve da vuot tran {limit_gb:g} GB")
    return before, total, n_del


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
    for api in APIS:
        path, _h = _cache_path(root, api, keyword, idx)
        if os.path.exists(path):
            return path
    return None


def stock_files(root, keyword, per=MAX_IDX, bo_giat=True):
    """MOI file da co cho keyword, tren CA BON kho (video + anh Ken Burns).

    stock_file() tra ve mot file cho moi idx (kho dau tien thang), nen neu cung
    mot keyword vua co clip Pexels vua co anh Pexels thi ban anh khong bao gio
    lot vao pool. Ham nay quet het de pool tron duoc ca hai — dung cho video
    lich su: anh tu lieu tinh + b-roll khong khi.

    per phai phu HET dai idx ma _fetch_keyword ghi ra (xem MAX_IDX): ban cu quet
    range(8) trong khi Pexels ghi vao idx 6..11 -> bon file Pexels moi keyword
    tai ve roi nam im trong o cung, khong bao gio duoc dung.

    bo_giat=True (mac dinh): bo clip VIDEO da biet la giat (danh sach den
    _giat_den.json hoac diem trong _do_muot.json >= nguong). Chi doc cache,
    khong do moi o day (do song song o prewarm_sigs / auto/quet_stock_giat.py).
    Clip giat bi bo thi kw_demand thay keyword thieu va tai clip khac bu vao;
    file KHONG bi xoa. STOCK_LOC_GIAT=0 de tat.
    """
    out = []
    for api in APIS:
        for i in range(per):
            path, _h = _cache_path(root, api, keyword, i)
            if os.path.exists(path):
                if bo_giat and api in VIDEO_APIS and la_giat(root, path, measure=False):
                    continue
                out.append(path)
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "videos/test-60s"
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as CFG
    cfg = CFG.load(root)
    fetch_stock(root, cfg)


if __name__ == "__main__":
    main()
