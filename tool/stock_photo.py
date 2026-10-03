# -*- coding: utf-8 -*-
"""stock_photo.py — ANH tu Pexels/Pixabay, bien thanh shot Ken Burns 1920x1080.

Vi sao can rieng module nay: stock.py chi goi endpoint VIDEO (/videos/search,
/api/videos/). Ma anh tinh do phan giai cao thuong dep va "sach" hon clip stock
cho video ke chuyen — anh 4000-6000px, crop 16:9, pan/zoom cham thi net hon han
clip 1080p bi nen.

File ghi DUNG duong dan ma stock.stock_files() doc:
    assets/stock/<md5("pexels-photo|<keyword>|<idx>")[:12]>.mp4
nen render/plan/assemble khong phai sua gi. Giong cach wiki_images.py lam, chi
khac kho: wiki ghi vao kho "wiki", module nay ghi vao kho "photo" —
nho vay anh Wikimedia va anh Pexels cung ton tai, pool tron duoc ca hai.

Dung:
    python tool/run.py --case videos/<topic> photo --per 4
    python tool/stock_photo.py videos/<topic> --per 4 --keyword "silk road"

Key: PEXELS_API_KEY (bat buoc), PIXABAY_API_KEY (tuy chon) trong tool/.env.
"""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import stock as ST  # noqa: E402
import wiki_images as WI  # noqa: E402

# Ken Burns can khung nguon rong hon dich de con dat zoom (xem WI._ken_burns
# scale ve 2560x1440). Xin dung 2560 ngay tu luc tai: anh goc Pexels 6000px
# nang 5-8 MB/tam, tai 130 keyword x 4 tam la vai GB vo ich.
DL_WIDTH = 2560
MIN_SRC_W = 1920          # duoi muc nay thi phong len 1920x1080 se mem
MIN_AR = 1.2              # anh gan vuong crop 16:9 con mat dau mat duoi

# Bao nhieu ket qua dau cua moi API duoc tin khong can khop tu khoa.
TOP_TRUST = 6

LICENSES = {
    "unsplash-photo": "Unsplash License (bat buoc ghi ten tac gia)",
    "pexels-photo": "Pexels License",
    "pixabay-photo": "Pixabay Content License",
}


_RATE_LOCK = threading.Lock()
_MIN_GAP = 0.25           # Pexels: 200 request/gio -> 0.25s/req la thoai mai
_last_req = [0.0]


def _throttle():
    with _RATE_LOCK:
        wait = _MIN_GAP - (time.monotonic() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.monotonic()


def _get(url, headers=None, timeout=45, tries=3):
    last = None
    for attempt in range(tries):
        _throttle()
        req = urllib.request.Request(
            url, headers=dict({"User-Agent": "Mozilla/5.0"}, **(headers or {})))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):
                time.sleep(3.0 * (2 ** attempt))
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def _p(msg):
    """print an toan tren console cp1252 (ten tac gia co dau)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _pexels_photos(key, keyword, per_page=40):
    """List dict {url, width, height, page, credit, title} tu Pexels."""
    q = urllib.parse.quote(keyword)
    api = (f"https://api.pexels.com/v1/search?query={q}&per_page={per_page}"
           f"&orientation=landscape&size=large")
    data = json.loads(ST.api_get("pexels", api,
                                 headers={"Authorization": key}).decode("utf-8"))
    out = []
    for p in data.get("photos", []):
        w, h = p.get("width") or 0, p.get("height") or 0
        if w < MIN_SRC_W or not h or (w / h) < MIN_AR:
            continue
        src = (p.get("src") or {}).get("original")
        if not src:
            continue
        # Pexels phuc vu anh qua imgix: xin dung be rong can, khong tai ban goc.
        out.append({
            "url": f"{src}?auto=compress&cs=tinysrgb&w={DL_WIDTH}",
            "width": w, "height": h,
            "page": p.get("url", ""),
            "credit": p.get("photographer", "") or "Pexels",
            "title": (p.get("alt") or keyword)[:120],
            "api": "pexels-photo",
        })
    return out


def _pixabay_photos(key, keyword, per_page=50):
    """Pixabay anh — chi lay fullHDURL.

    largeImageURL cua Pixabay bi chan o 1280px du anh goc 6000px: phong len
    1920x1080 la mem thay ro. Key khong co quyen fullHD thi coi nhu Pixabay
    khong co anh dung duoc, de Pexels lo.
    """
    q = urllib.parse.quote(keyword)
    api = (f"https://pixabay.com/api/?key={key}&q={q}&image_type=photo"
           f"&orientation=horizontal&per_page={per_page}&safesearch=true"
           f"&min_width={MIN_SRC_W}&order=popular")
    data = json.loads(ST.api_get("pixabay", api).decode("utf-8"))
    out = []
    for hit in data.get("hits", []):
        url = hit.get("fullHDURL")
        if not url:
            continue
        w, h = hit.get("imageWidth") or 0, hit.get("imageHeight") or 0
        if h and (w / h) < MIN_AR:
            continue
        out.append({
            "url": url, "width": w, "height": h,
            "page": hit.get("pageURL", ""),
            "credit": hit.get("user", "") or "Pixabay",
            "title": (hit.get("tags") or keyword)[:120],
            "api": "pixabay-photo",
        })
    return out


def _unsplash_photos(key, keyword, per_page=30):
    """Unsplash — anh chat luong cao nhat trong ba nguon, nhung co RANG BUOC.

    Dieu khoan API bat buoc: (1) ghi ten tac gia + link Unsplash, (2) goi
    endpoint `links.download_location` moi lan thuc su tai anh de Unsplash dem
    luot. Ca hai deu duoc lam o day/ghi vao photo-credits.json — bo la vi pham
    dieu khoan, khong phai chuyen "cho cho dep".
    """
    q = urllib.parse.quote(keyword)
    api = (f"https://api.unsplash.com/search/photos?query={q}"
           f"&per_page={per_page}&orientation=landscape&content_filter=high")
    hdr = {"Authorization": "Client-ID " + key,
           "Accept-Version": "v1"}
    data = json.loads(ST.api_get("unsplash", api, headers=hdr).decode("utf-8"))
    out = []
    for p in data.get("results", []):
        w, h = p.get("width") or 0, p.get("height") or 0
        if w < MIN_SRC_W or not h or (w / h) < MIN_AR:
            continue
        raw = (p.get("urls") or {}).get("raw")
        if not raw:
            continue
        user = p.get("user") or {}
        out.append({
            # raw URL cua Unsplash cung la imgix: xin dung be rong can dung.
            "url": f"{raw}&w={DL_WIDTH}&fm=jpg&q=85",
            "width": w, "height": h,
            "page": (p.get("links") or {}).get("html", ""),
            "credit": user.get("name") or user.get("username") or "Unsplash",
            "title": (p.get("alt_description") or keyword)[:120],
            "api": "unsplash-photo",
            "dl_ping": (p.get("links") or {}).get("download_location"),
            "_key": key,
        })
    return out


def _unsplash_ping(hit):
    """Bao cho Unsplash biet anh da duoc tai (dieu khoan bat buoc)."""
    if hit.get("api") != "unsplash-photo" or not hit.get("dl_ping"):
        return
    try:
        _get(hit["dl_ping"],
             headers={"Authorization": "Client-ID " + hit["_key"],
                      "Accept-Version": "v1"}, timeout=15, tries=1)
    except Exception as e:
        _p(f"  (bo qua) khong ping duoc download Unsplash: {e}")


# Tu bo tro: co mat trong hau het truy van, khong noi len anh co dung chu de khong.
_FILLER = {"the", "a", "an", "of", "and", "in", "on", "at", "with", "for",
           "ancient", "old", "traditional", "historical", "history",
           "scene", "view", "close", "up", "photo", "image", "shot",
           "illustration", "painting", "portrait", "artifact", "style"}

# Dau hieu THOI NAY. Do ta tim canh lich su nen day la co do: anh sac net den
# may cung hong. Do loc nay bat duoc ca hai kieu truot thuong gap: doi cosplay
# chup truoc toa nha kinh, va anh nha tu hien dai (ao cam, cong tay) tra ve cho
# truy van "prison interrogation".
_MODERN = {
    "cosplay", "costume", "model", "posing", "poses", "selfie", "makeup",
    "fashion", "studio", "wedding", "tourist", "tourists",
    "smartphone", "phone", "iphone", "laptop", "computer", "camera", "tv",
    "car", "cars", "bus", "truck", "bicycle", "motorbike", "traffic", "road",
    "neon", "skyscraper", "skyline", "office", "elevator", "escalator",
    "supermarket", "cafe", "restaurant", "hotel", "airport", "train",
    "jumpsuit", "handcuffed", "handcuffs", "police", "officer", "prison",
    "jail", "jeans", "tshirt", "sneakers", "plastic", "modern", "contemporary",
    "business", "businessman", "meeting", "desk", "chair", "glasses",
}

# Danh tu CANH hop voi video ke su phuong Dong. Trung mot tu o day la tin hieu
# duong du de giu anh lai, ke ca khi mo ta khong nhac tu khoa nao cua ta.
_SCENE = {
    "temple", "pagoda", "palace", "shrine", "monastery", "tomb", "mausoleum",
    "stele", "tablet", "courtyard", "gate", "wall", "rampart", "fortress",
    "ruins", "statue", "buddha", "dragon", "lantern", "silk", "scroll",
    "calligraphy", "brush", "ink", "incense", "candle", "fire", "smoke",
    "mountain", "mountains", "mist", "misty", "fog", "cloud", "clouds",
    "bamboo", "forest", "river", "lake", "waterfall", "desert", "dune",
    "snow", "rain", "dusk", "dawn", "sunrise", "sunset", "moon", "stone",
    "rock", "roof", "tile", "wood", "wooden", "forbidden", "grotto", "cave",
    "armor", "sword", "horse", "battlefield", "banner", "throne",
}

# Vung dia ly: anh dung chu de nhung SAI NUOC con te hon anh chung chung —
# khan gia Viet nhin ra ngay lang Azerbaijan khong phai lang Trung Hoa.
_REGIONS = {
    "china": {"china", "chinese", "beijing", "xian", "shaanxi", "shanghai",
              "guilin", "huangshan", "yangtze", "hutong", "tang", "han", "qin",
              "ming", "qing", "song", "zhou", "confucian", "taoist", "hanfu",
              "forbidden", "zhangjiajie", "guangxi", "yunnan", "sichuan"},
    "vietnam": {"vietnam", "vietnamese", "hanoi", "hue", "saigon", "halong"},
    "japan": {"japan", "japanese", "kyoto", "tokyo", "shinto", "torii",
              "samurai", "kimono", "osaka", "fuji"},
    "korea": {"korea", "korean", "seoul", "hanbok", "joseon"},
    "india": {"india", "indian", "delhi", "hindu", "taj", "rajasthan"},
    "thai": {"thailand", "thai", "bangkok", "ayutthaya"},
    "west": {"paris", "france", "french", "rome", "italy", "italian", "greek",
             "greece", "spain", "london", "england", "german", "russia",
             "azerbaijan", "turkey", "egypt", "mexico", "peru"},
}


def _regions_of(text):
    import re
    t = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    return {name for name, toks in _REGIONS.items() if t & toks}


def _rel_score(keyword, title):
    """Cham diem anh co dung canh minh can khong. < 1 la loai.

    Pexels/Unsplash luon tra ve MOT CAI GI DO cho moi truy van — duoi danh sach
    la anh chang lien quan. Diem gom ba phan:
      +2  moi tu dac trung cua keyword xuat hien trong mo ta
      +1  moi danh tu canh hop bo (den long, bia da, nui suong...)
      -1  (loai han) co dau hieu thoi nay, hoac sai vung dia ly
    """
    import re
    t = set(re.findall(r"[a-z0-9]+", (title or "").lower()))
    if t & _MODERN:
        return -1
    kr, tr = _regions_of(keyword), _regions_of(title)
    if kr and tr and not (kr & tr):
        return -1                       # keyword noi Trung Hoa, anh chup Azerbaijan
    k = {w for w in re.findall(r"[a-z0-9]+", (keyword or "").lower())
         if w not in _FILLER}
    return 2 * len(k & t) + len(t & _SCENE)


def _loc(keyword, hits, log=_p):
    """Loc lien quan. Mot anh SAI chu de hai hon la thieu anh: cell thieu hinh
    thi con nguon khac (wiki) hoac card do vao, con anh sai thi len song.
    PHOTO_STRICT=0 de tat khi lam kenh khong ke chuyen lich su."""
    if os.environ.get("PHOTO_STRICT", "1") == "0":
        return hits
    keep = []
    for h in hits:
        s = _rel_score(keyword, h["title"])
        if s < 0:                     # thoi nay / sai vung -> loai han
            continue
        # Mo ta cua Unsplash thuong coc lon ("brown concrete building") nen
        # cham diem theo chu se giet ca anh dung. Nhung chinh API da xep
        # hang theo do lien quan roi: TOP_TRUST ket qua dau duoc tin, phia
        # duoi moi phai tu chung minh bang tu khoa.
        if s >= 1 or h["rank"] < TOP_TRUST:
            keep.append((h, s))
    keep.sort(key=lambda p: (-p[1], p[0]["rank"]))
    return [h for h, _s in keep]


def search_photos(keyword, log=_p, want=0):
    """Gom ket qua cac nguon theo thu tu do dep: Unsplash -> Pexels -> Pixabay.

    want > 0: du `want` anh qua loc thi DUNG, khong goi nguon sau. Ban cu goi
    ca ba nguon cho moi keyword: 171 keyword = 513 request trong khi quota
    Unsplash demo 50/gio, Pexels 200/gio (chia voi video) -> 429 hang loat.
    """
    pk, px = ST._keys()
    us = ST._key("UNSPLASH_ACCESS_KEY")
    hits, kept = [], []
    for ten, key, ham in (("unsplash", us, _unsplash_photos),
                          ("pexels", px, _pexels_photos),
                          ("pixabay", pk, _pixabay_photos)):
        # nguon bi breaker tat (401/403/het quota) -> khong ton them request
        if not key or not ST.api_alive(ten):
            continue
        try:
            got = ham(key, keyword)
        except ST.ApiDown:
            continue
        except Exception as e:
            log(f"  WARN {ten} '{keyword}': {e}")
            continue
        # rank = thu hang do CHINH API xep, tinh rieng tung nguon.
        for i, h in enumerate(got):
            h["rank"] = i
        hits += got
        kept = _loc(keyword, hits, log)
        if want and len(kept) >= want:
            break
    if hits and not kept:
        log(f"  (loc) {len(hits)} anh deu khong khop '{keyword}'")
    return kept


def fetch_for_keyword(root, keyword, per=4, force=False, credits=None,
                      seen_urls=None):
    """Tao THEM `per` shot Ken Burns cho keyword (vao cac idx con trong).

    per do fetch_all tinh = phan con thieu theo thoi luong cell (ST.kw_demand),
    khong con la con so co dinh moi keyword.
    seen_urls (set dung chung ca lan chay): mot tam anh chi duoc dung mot lan
    trong ca video, du hai keyword khac nhau cung tra ve no.
    """
    need = []
    for i in range(ST.MAX_IDX):
        if len(need) >= per:
            break
        path, _h = ST._cache_path(root, "photo", keyword, i)
        if os.path.exists(path) and not force:
            continue
        need.append((i, path))
    if not need:
        _p(f"  ok (da co) {keyword}")
        return 0

    hits = search_photos(keyword, want=len(need) + 2)
    if not hits:
        _p(f"  MISS khong co anh: {keyword}")
        return 0

    tmpdir = os.path.join(root, "build", "tmp", "photo")
    os.makedirs(tmpdir, exist_ok=True)
    if seen_urls is None:
        seen_urls = set()
    made, hit_i = 0, 0
    for idx, out_path in need:
        img = h = None
        while hit_i < len(hits):
            h = hits[hit_i]
            hit_i += 1
            if h["url"] in seen_urls:
                continue
            try:
                # tai song song co gioi han THEO NGUON (semaphore cua breaker)
                with ST._RT[h["api"].split("-")[0]].sem:
                    data = _get(h["url"], timeout=60)
            except Exception as e:
                _p(f"  skip tai loi ({e}) {h['title'][:40]}")
                continue
            if len(data) < 40_000:        # anh loi / qua nho
                continue
            ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
            img = os.path.join(
                tmpdir, hashlib.md5(h["url"].encode()).hexdigest()[:10] + ext)
            with open(img, "wb") as f:
                f.write(data)
            seen_urls.add(h["url"])
            _unsplash_ping(h)
            break
        if not img:
            break
        if WI._ken_burns(img, out_path, idx):
            made += 1
            if credits is not None:
                credits.append({
                    "keyword": keyword, "file": os.path.basename(out_path),
                    "title": h["title"], "credit": h["credit"],
                    "source": h["api"], "license": LICENSES[h["api"]],
                    "page": h["page"],
                })
    _p(f"  +{made} shot  {keyword}")
    return made


def fetch_all(root, per=4, force=False, workers=4):
    """Tai anh cho cell type=stock trong config.json — CHI phan con thieu.

    So anh moi keyword = ST.kw_demand (tong giay cac cell dung keyword /
    SHOT_SEC + 1, tru file da co o moi kho, ke ca anh tu lieu ent vua tai o
    buoc wiki). `per` gio la TRAN moi keyword, khong con la dinh muc.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    pk, px = ST._keys()
    if not px and not pk and not ST._key("UNSPLASH_ACCESS_KEY"):
        raise RuntimeError("thieu PEXELS_API_KEY / PIXABAY_API_KEY / "
                           "UNSPLASH_ACCESS_KEY trong tool/.env")
    t0 = time.monotonic()
    with open(os.path.join(root, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    need = {k: n for k, n in ST.kw_demand(root, cfg, cap=per).items() if n > 0}
    print(f"photo: {len(need)} keyword con thieu, can {sum(need.values())} anh "
          f"(tran {per}/keyword), {workers} luong")
    credits, seen_urls, total = [], set(), 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_for_keyword, root, kw, n, force, credits,
                          seen_urls): kw for kw, n in need.items()}
        for fu in as_completed(futs):
            try:
                total += fu.result()
            except Exception as e:
                _p(f"  ERR {futs[fu]}: {e}")
    ST.breaker_report()
    print(f"photo: tao {total} shot trong {time.monotonic() - t0:.0f}s. "
          f"Credit -> {ghi_credits(root, credits)}")
    ST.enforce_cache_limit(root, protect=ST.files_of_config(root, cfg))
    return total


def ghi_credits(root, credits):
    """Noi credit moi vao build/photo-credits.json (sources.py doc file nay).

    Unsplash bat buoc ghi ten tac gia, nen buoc nay khong phai tuy chon —
    duong chay mot-keyword cung phai goi, khong duoc nuot credit.
    """
    cpath = os.path.join(root, "build", "photo-credits.json")
    os.makedirs(os.path.dirname(cpath), exist_ok=True)
    old = []
    if os.path.exists(cpath):
        try:
            with open(cpath, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = []
    with open(cpath, "w", encoding="utf-8") as f:
        json.dump(old + credits, f, ensure_ascii=False, indent=1)
    return cpath


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--per", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--keyword", default=None)
    a = ap.parse_args()
    if a.keyword:
        root = os.path.abspath(a.root)
        credits = []
        fetch_for_keyword(root, a.keyword, per=a.per, force=a.force,
                          credits=credits)
        ghi_credits(root, credits)
    else:
        fetch_all(os.path.abspath(a.root), per=a.per, force=a.force)


if __name__ == "__main__":
    main()
