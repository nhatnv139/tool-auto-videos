"""wiki_images.py — nguon hinh cho video LICH SU (khong can API key).

Kenh ke su khong dung stock footage cong nghe; no dung tranh co, hien vat,
ban do, anh tu lieu. Module nay lay anh PUBLIC DOMAIN / CC tu Wikimedia Commons
roi bien moi anh thanh mot shot Ken Burns 1920x1080 (pan + zoom cham).

File ghi vao kho "wiki" ma stock.stock_files() quet:
    assets/stock/<md5("wiki|<keyword>|<idx>")[:12]>.mp4        (keyword canh)
    assets/stock/<md5("wiki|ent:<thuc the>|<idx>")[:12]>.mp4   (marker ent=)
Ban cu ghi nho kho "pixabay" -> trung hash voi video Pixabay that.

Dung:
    python tool/run.py --case videos/<topic> wiki          # tai cho moi keyword
    python tool/wiki_images.py videos/<topic> --per 8      # goi truc tiep
    python tool/wiki_images.py videos/<topic> --ent "Qianlong Emperor" --per 6
"""
import hashlib
import io
import json
import os
import random
import re
import subprocess
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import stock as ST  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia YEU CAU User-Agent mo ta ro + dia chi lien he. UA chung chung bi
# rate-limit rat gat (429 ngay tu request thu vai). Doc:
# https://meta.wikimedia.org/wiki/User-Agent_policy
UA = os.environ.get(
    "WIKI_UA",
    "ai-frontier-kit/1.0 (history documentary research; linhnln@pila.vn) "
    "python-urllib/3.11")

FPS = 24
W, H = 1920, 1080
SHOT_DUR = 9.0          # moi shot du dai cho segment 6s cua render + du dao
MIN_WIDTH = 900

# License chap nhan duoc (Commons luon free, nhung loai ra thu can attribution
# phuc tap / non-free logo lot luoi).
_BAD_LIC = ("fair use", "non-free", "no license")


import threading
import time

# Wikimedia tra 429 rat nhanh neu ban ban nhieu request song song. Mot khoa
# toan cuc + khoang cach toi thieu giua hai request giu tong tan suat duoi
# nguong, du chay bao nhieu luong.
_RATE_LOCK = threading.Lock()
_MIN_GAP = 0.35          # giay giua hai request bat ky
_last_req = [0.0]


def _throttle():
    with _RATE_LOCK:
        wait = _MIN_GAP - (time.monotonic() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.monotonic()


def _get(url, timeout=30, tries=4):
    """GET co throttle + backoff cho 429. Wikimedia chan gat nhung tha nhanh."""
    last = None
    for attempt in range(tries):
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):
                time.sleep(2.0 * (2 ** attempt))   # 2s, 4s, 8s, 16s
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def _p(msg):
    """print an toan tren console cp1252 (ten file Commons co dau la)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def _query_variants(keyword):
    """Commons AND tat ca tu khoa -> cum dai 5-6 tu thuong tra ve 0-2 ket qua.

    Sinh cac bien the RONG DAN: nguyen cum -> bo dan tu cuoi -> con loi noi bat.
    Tu dac trung (ten rieng, trieu dai) duoc giu lai lau nhat.
    """
    words = keyword.split()
    outs = [keyword]
    for n in (4, 3, 2):
        if len(words) > n:
            v = " ".join(words[:n])
            if v not in outs:
                outs.append(v)
    # loi noi bat: bo cac tu bo tro chung chung
    filler = {"ancient", "old", "china", "chinese", "painting", "portrait",
              "illustration", "artifact", "statue", "scene", "traditional"}
    core = [w for w in words if w.lower() not in filler]
    if 1 <= len(core) <= 3:
        v = " ".join(core)
        if v not in outs:
            outs.append(v)
    return outs


def search_commons(keyword, limit=30, want=0):
    """Tra ve list dict {title, url, width, height, license, credit}.

    Neu cum tu day du cho qua it anh, tu dong noi rong truy van cho den khi du
    `want` ket qua (hoac het bien the).
    """
    seen, out = set(), []
    for qi, variant in enumerate(_query_variants(keyword)):
        for h in _search_one(variant, limit):
            if h["title"] in seen:
                continue
            seen.add(h["title"])
            h["query"] = variant
            h["_qi"] = qi
            out.append(h)
        if want and len(out) >= want:
            break
        if qi == 0 and not want:
            break
    # Xep theo do khop TEN FILE, khong theo thu tu relevance cua Commons.
    # Commons xep "1960 Puyi and Snow.jpg" len truoc "PuYi 1909.jpg" cho truy
    # van "Puyi 1909" — dung cho tim kiem chung, sai cho video lich su, noi
    # dung nam/chu de trong ten file moi la thu quyet dinh canh co dung hay khong.
    out.sort(key=lambda h: (-_title_score(h["title"], keyword), h["_qi"]))
    return out


def _title_score(title, keyword):
    """Dem tu khoa dac trung xuat hien trong ten file (khong ke tu bo tro)."""
    filler = {"file", "jpg", "png", "tif", "the", "of", "a", "an", "and",
              "ancient", "old", "china", "chinese", "painting", "portrait",
              "illustration", "artifact", "statue", "scene", "traditional"}
    t = re.findall(r"[a-z0-9]+", title.lower())
    tset = set(t) - filler
    score = 0
    for w in re.findall(r"[a-z0-9]+", keyword.lower()):
        if w in filler:
            continue
        if w in tset:
            score += 2 if w.isdigit() else 1      # nam/so la tin hieu manh nhat
    return score


def _search_one(keyword, limit=30):
    q = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f'filetype:bitmap {keyword}', "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1920",
    }
    try:
        raw = _get(API + "?" + urllib.parse.urlencode(q))
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception as e:
        _p(f"  WARN search '{keyword}': {e}")
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        mime = ii.get("mime", "")
        if not mime.startswith("image/"):
            continue
        if mime in ("image/svg+xml", "image/gif"):
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if w < MIN_WIDTH or h < 600:
            continue
        ar = w / float(h or 1)
        if ar < 0.62 or ar > 3.2:          # loai anh qua doc / panorama qua dai
            continue
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName", {}).get("value") or "").lower()
        if any(b in lic for b in _BAD_LIC):
            continue
        url = ii.get("thumburl") or ii.get("url")
        if not url:
            continue
        out.append({
            "title": p.get("title", ""),
            "url": url,
            "width": w, "height": h,
            "license": meta.get("LicenseShortName", {}).get("value") or "?",
            "credit": _strip(meta.get("Artist", {}).get("value") or ""),
        })
    return out


def _strip(s):
    import re
    s = re.sub(r"<[^>]+>", " ", s or "")
    return " ".join(s.split())[:120]


def _ken_burns(img_path, out_path, idx, dur=SHOT_DUR, center=False):
    """1 anh tinh -> 1 shot 1920x1080 co pan/zoom cham. Huong doi theo idx.

    center=True: chi zoom giua (anh da duoc _prep_image dung khung san).
    """
    zoom_in = (idx % 2 == 0)
    z0, z1 = (1.02, 1.16) if zoom_in else (1.16, 1.02)
    n_fr = max(1, int(dur * FPS))
    # Zoom tinh theo SO FRAME (on), khong cong don tu `zoom`: zoompan khoi tao
    # zoom = 1 o frame dau, nen ban cu "max(zoom-step, 1.02)" cho zoom-out ra
    # 1.02 ngay frame 1 va dung yen ca 9 giay — mot nua so shot (idx le) la anh
    # chet. Bieu thuc tuyen tinh theo on cho ca hai chieu chay dung 1.02 <-> 1.16.
    zexpr = f"{z0}+({z1 - z0:.4f})*on/{n_fr}"
    # pan: 4 huong luan phien de cac shot lien tiep khong giong nhau
    pans = [
        ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),                    # center
        ("(iw-iw/zoom)*on/({n})".format(n=int(dur * FPS)), "ih/2-(ih/zoom/2)"),
        ("iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/({n})".format(n=int(dur * FPS))),
        ("(iw-iw/zoom)*(1-on/({n}))".format(n=int(dur * FPS)),
         "ih/2-(ih/zoom/2)"),
    ]
    px, py = pans[0] if center else pans[idx % len(pans)]
    # Scale nguon vua du dau zoom toi da (~1.16) roi moi zoompan: zoompan phai
    # lam viec tren TUNG frame, nen cho no khung 4K la tu ban minh — 9s x 24fps
    # = 216 lan lanczos 4K. 2560x1440 cho cung do net o dich 1080p.
    SW, SH = 2560, 1440
    vf = (
        f"scale={SW}:{SH}:force_original_aspect_ratio=increase:flags=bicubic,"
        f"crop={SW}:{SH},setsar=1,"
        f"zoompan=z='{zexpr}':x='{px}':y='{py}':d=1:fps={FPS}:s={W}x{H},"
        # grade nhe cho dong bo voi cinema look cua render.py
        f"eq=contrast=1.04:saturation=0.96,format=yuv420p"
    )
    cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS),
           "-i", img_path, "-t", f"{dur:.2f}", "-vf", vf,
           # Do 01/10 tren 44 shot tu lieu: ultrafast crf20 ra 26-42 MB cho 9s
           # (ultrafast tat gan het cong cu nen, anh zoom cham thanh bitrate
           # ~30 Mbps). veryfast crf22 cung shot: 1,5 MB, render con encode lai
           # crf14 nen khong ai thay khac biet.
           "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_path):
        _p(f"  ERR ffmpeg: {r.stderr.strip()[:200]}")
        return False
    return True


# ---------------------------------------------------------------------------
# ANH TU LIEU THAT CUA MOT THUC THE (marker ent=).
#
# Do 01/10 tren script Can Long: 171 marker kieu "ancient Chinese old man window
# light" dua vao full-text search Commons tra ve anh ngau nhien, KHONG mot anh
# nao la chan dung Can Long du Commons co hang tram (Category:Qianlong Emperor,
# tranh Giuseppe Castiglione...). Full-text search tim chu trong ten file/mo
# ta; con thu minh can la "anh CUA thuc the nay" — cai do nam o (1) anh trong
# chinh bai Wikipedia ve no, (2) Commons Category cua no. Tra thang hai noi do.
# ---------------------------------------------------------------------------

WP_API = "https://{lang}.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
ENT_LANGS = ("vi", "zh")      # ngoai EN: bai VI/ZH thuong co tranh khac
ENT_MAX = 16                  # tran so shot moi thuc the
ENT_MIN_LONG, ENT_MIN_SHORT = 800, 500   # duoi 800px phong len 1080p la vo

# Ten file rac: icon/logo/co/huy hieu/ban do dinh vi/chu ky... Loc bang ten
# TRUOC khi goi imageinfo de khong ton request.
_JUNK = re.compile(
    r"(logo|icon|flag[ _]of|coat[ _]of[ _]arms|emblem|locator|location[ _]map|"
    r"signature|pictogram|symbol|wikisource|wiktionary|wikiquote|commons-|"
    r"disambig|question[ _]book|ambox|padlock|nuvola|crystal[ _]clear|"
    r"edit-clear|red[ _]pencil|placeholder|blank|stub|button|arrow|"
    r"speaker[ _]icon|audio|sound|\.svg$|\.gif$|\.ogg$|\.webm$|\.pdf$|\.djvu$|"
    # anh dau de cua ban mau {{Lich su Viet Nam}} / {{History of ...}} tren
    # Wikipedia VI: trien do + chu "Lich su Viet" — lot vao ent Duong Dinh
    # Nghe 03/10/2026 (2/3 shot la logo).
    r"template[ _]heading|for[ _]template|lichsu|lich[ _]?su[ _]?viet|"
    r"history[ _]of[ _]vietnam\"|navbox|banner|header|wordmark|"
    # anh pho gan toa do (Panoramio/Mapillary) lot vao ent nhan vat vi TEN
    # DUONG trung ten nguoi: "Ngô Quyền, Lê Bình, Cái Răng, Cần Thơ" la cho
    # noi Can Tho, khong phai Ngo Quyen (03/10/2026).
    r"panoramio|mapillary|street[ _]view)",
    re.I)

_ENT_FILLER = {"the", "of", "a", "an", "and", "emperor", "empress", "king",
               "queen", "dynasty", "palace", "embassy", "war", "battle",
               "category", "file", "jpg", "png", "tif", "tiff", "jpeg"}


def _jget(api, params):
    q = dict(params, format="json", formatversion="2")
    raw = _get(api + "?" + urllib.parse.urlencode(q))
    return json.loads(raw.decode("utf-8", "replace"))


def _page_images(lang, title):
    """Bai Wikipedia -> (dict thong tin, list 'File:...')."""
    try:
        d = _jget(WP_API.format(lang=lang), {
            "action": "query", "titles": title, "redirects": 1,
            "prop": "pageimages|pageprops|langlinks|images",
            "piprop": "name", "ppprop": "wikibase_item",
            "lllimit": "max", "imlimit": "max"})
    except Exception as e:
        _p(f"  WARN wiki {lang} '{title}': {e}")
        return None, []
    pages = (d.get("query") or {}).get("pages") or []
    if not pages or pages[0].get("missing") or pages[0].get("invalid"):
        return None, []
    p = pages[0]
    imgs = [i["title"] for i in p.get("images") or []]
    info = {
        "title": p.get("title"),
        "lead": ("File:" + p["pageimage"]) if p.get("pageimage") else None,
        "qid": (p.get("pageprops") or {}).get("wikibase_item"),
        "ll": {l.get("lang"): l.get("title") for l in p.get("langlinks") or []},
    }
    return info, imgs


def _wikidata(qid):
    """-> (list anh P18, commons category P373)."""
    if not qid:
        return [], None
    try:
        d = _jget(WD_API, {"action": "wbgetentities", "ids": qid,
                           "props": "claims"})
    except Exception as e:
        _p(f"  WARN wikidata {qid}: {e}")
        return [], None
    cl = ((d.get("entities") or {}).get(qid) or {}).get("claims") or {}

    def vals(pid):
        out = []
        for c in cl.get(pid) or []:
            v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(v, str):
                out.append(v)
        return out
    p18 = ["File:" + v for v in vals("P18")]
    p373 = vals("P373")
    return p18, (p373[0] if p373 else None)


def _cat_members(cat, cmtype, limit):
    try:
        d = _jget(API, {"action": "query", "list": "categorymembers",
                        "cmtitle": "Category:" + cat, "cmtype": cmtype,
                        "cmlimit": str(limit)})
    except Exception as e:
        _p(f"  WARN category '{cat}': {e}")
        return []
    return [m["title"] for m in (d.get("query") or {}).get("categorymembers") or []]


def _imageinfo(titles):
    """Commons imageinfo theo lo 50 ten. File chi co tren enwiki (fair use,
    khong nam tren Commons) tra ve missing -> tu roi, khong dung."""
    out = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        try:
            d = _jget(API, {"action": "query", "titles": "|".join(batch),
                            "prop": "imageinfo",
                            "iiprop": "url|size|mime|extmetadata",
                            "iiurlwidth": "1920"})
        except Exception as e:
            _p(f"  WARN imageinfo: {e}")
            continue
        for p in (d.get("query") or {}).get("pages") or []:
            if p.get("missing") and not p.get("imageinfo"):
                continue
            ii = (p.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            if mime not in ("image/jpeg", "image/png", "image/tiff", "image/webp"):
                continue
            w, h = ii.get("width", 0), ii.get("height", 0)
            if max(w, h) < ENT_MIN_LONG or min(w, h) < ENT_MIN_SHORT:
                continue
            ar = w / float(h or 1)
            if ar < 0.35 or ar > 4.0:
                continue
            meta = ii.get("extmetadata") or {}
            lic = (meta.get("LicenseShortName", {}).get("value") or "")
            if any(b in lic.lower() for b in _BAD_LIC):
                continue
            url = ii.get("thumburl") or ii.get("url")
            if not url:
                continue
            out[p.get("title")] = {
                "title": p.get("title"), "url": url, "width": w, "height": h,
                "license": lic or "?",
                "credit": _strip(meta.get("Artist", {}).get("value") or ""),
            }
    return out


def entity_candidates(ent):
    """Moi anh tu lieu tim duoc cho ent, da xep hang. -> (list hit, thong ke).

    Diem: anh dai dien (P18 / pageimage) 100 | Commons Category 30 | bai EN 28
    | bai VI/ZH 24 | subcategory 1 tang 18 | +8 neu ten file chua tu dac trung
    cua ent (vd "qianlong") | +6 moi nguon khac cung chua anh do.
    """
    score, src = {}, {}

    def add(title, pts, tag):
        if not title or _JUNK.search(title):
            return
        t = title if title.startswith("File:") else "File:" + title
        if t in score:
            score[t] = max(score[t], pts) + 6
        else:
            score[t] = pts
        src.setdefault(t, set()).add(tag)

    stats = {}
    cat = None
    if ent.lower().startswith("category:"):
        cat = ent.split(":", 1)[1].strip()
    else:
        info, imgs = _page_images("en", ent)
        if info:
            p18, p373 = _wikidata(info["qid"])
            for f in p18:
                add(f, 100, "p18")
            add(info["lead"], 100, "lead")
            for f in imgs:
                add(f, 28, "en")
            stats["en"] = len(imgs)
            for lang in ENT_LANGS:
                t = info["ll"].get(lang)
                if not t:
                    continue
                _i, li = _page_images(lang, t)
                for f in li:
                    add(f, 24, lang)
                stats[lang] = len(li)
            cat = p373 or info["title"]
        else:
            cat = ent
    files = _cat_members(cat, "file", 200)
    for f in files:
        add(f, 30, "cat")
    stats["cat"] = len(files)
    n_sub = 0
    for sc in _cat_members(cat, "subcat", 30)[:8]:
        sf = _cat_members(sc.split(":", 1)[1], "file", 60)
        n_sub += len(sf)
        for f in sf:
            add(f, 18, "sub")
    stats["sub"] = n_sub
    stats["category"] = cat

    toks = {w for w in re.findall(r"[a-z0-9]+", ent.lower())
            if w not in _ENT_FILLER and len(w) > 2}
    for t in list(score):
        tt = set(re.findall(r"[a-z0-9]+", t.lower()))
        if toks & tt:
            score[t] += 8
    ranked = sorted(score, key=lambda t: -score[t])
    stats["candidates"] = len(ranked)
    return [(t, score[t], sorted(src[t])) for t in ranked], stats


def _prep_image(img, variant, tmpdir):
    """Dung khung 16:9 cho anh tu lieu truoc Ken Burns. -> (duong dan, center).

    Chan dung/tranh treo doc (ti le < 1.3) ma crop giua ra 16:9 thi mat ngay
    mat — mat nam o 1/3 tren. Nen:
      variant 0: ca buc tranh dat giua, nen la chinh no phong to + lam mo toi
                 (kieu phim tai lieu) -> khong mat mot chi tiet nao.
      variant 1: cat dai 16:9 sat phia tren (8% tu dinh) -> can mat/nua nguoi.
    Anh ngang: tra nguyen, variant doi huong pan (xem fetch_entity).
    """
    try:
        from PIL import Image, ImageFilter, ImageEnhance
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(img).convert("RGB")
    except Exception:
        return img, False
    w, h = im.size
    if w / float(h) >= 1.3:
        return img, False
    CW, CH = 2560, 1440
    base = os.path.splitext(img)[0]
    if variant % 2 == 0:
        sc = max(CW / w, CH / h)
        bg = im.resize((int(w * sc) + 1, int(h * sc) + 1), Image.BILINEAR)
        l, t = (bg.width - CW) // 2, (bg.height - CH) // 2
        bg = bg.crop((l, t, l + CW, t + CH)).filter(ImageFilter.GaussianBlur(36))
        bg = ImageEnhance.Brightness(bg).enhance(0.45)
        fh = int(CH * 0.94)
        fw = int(w * fh / h)
        fg = im.resize((fw, fh), Image.LANCZOS)
        bg.paste(fg, ((CW - fw) // 2, (CH - fh) // 2))
        out = base + ".fit.jpg"
        bg.save(out, quality=92)
        return out, True
    ch = int(w * 9 / 16)
    y0 = min(int(h * 0.08), max(0, h - ch))
    crop = im.crop((0, y0, w, y0 + ch))
    out = base + ".top.jpg"
    crop.save(out, quality=92)
    return out, False


def _used_titles(root):
    """Ten file Commons da thanh shot trong case nay (doc wiki-credits.json)."""
    p = os.path.join(root, "build", "wiki-credits.json")
    try:
        with open(p, encoding="utf-8") as f:
            return {(c.get("keyword"), c.get("file")): c.get("title")
                    for c in json.load(f)}
    except Exception:
        return {}


def fetch_entity(root, ent, n, credits=None, used=None, used_lock=None):
    """Tao toi da n shot tu anh tu lieu THAT cua ent -> kho "wiki", khoa
    "ent:<ent>". Anh khac nhau truoc; thieu anh thi moi lam crop thu hai cua
    cung buc (chan dung nhan vat chinh duoc phep lap, nhung khac khung).

    used: set ten file Commons dung chung giua cac ent trong mot lan chay —
    mot buc tranh chi thuoc mot ent (Macartney vua o bai Can Long vua o bai
    Macartney Embassy).
    Tra ve (so shot moi, so anh tu lieu that dung duoc).
    """
    key = ST.ent_key(ent)
    have = ST.stock_files(root, key)
    n = min(n, ENT_MAX)
    if len(have) >= n:
        _p(f"  ok (da co {len(have)}) ent={ent}")
        return 0, len(have)
    cands, stats = entity_candidates(ent)
    done_titles = {t for (k, _f), t in _used_titles(root).items() if k == key}
    info = _imageinfo([t for t, _s, _src in cands[:max(60, n * 5)]])
    hits = [dict(info[t], score=s, src=src) for t, s, src in cands if t in info]
    _p(f"  ent={ent}: {len(hits)} anh tu lieu dung duoc / {stats['candidates']} "
       f"ung vien (EN {stats.get('en', 0)}, VI {stats.get('vi', 0)}, "
       f"ZH {stats.get('zh', 0)}, Category:{stats.get('category')} "
       f"{stats.get('cat', 0)} + sub {stats.get('sub', 0)})")
    if not hits:
        return 0, 0
    tmpdir = os.path.join(root, "build", "tmp", "wiki")
    os.makedirs(tmpdir, exist_ok=True)
    used_lock = used_lock or threading.Lock()
    # ke hoach: moi anh variant 0, roi (neu thieu) variant 1 cua cac anh dau
    plan = [(h, 0) for h in hits] + [(h, 1) for h in hits]
    made, idx = 0, 0
    got_imgs = {}
    for h, var in plan:
        if len(have) + made >= n:
            break
        if var == 0:
            with used_lock:
                if h["title"] in done_titles:
                    continue
                if used is not None:
                    if h["title"] in used:
                        continue
                    used.add(h["title"])
        elif h["title"] not in got_imgs:
            continue
        img = got_imgs.get(h["title"])
        if not img:
            try:
                data = _get(h["url"], timeout=60)
            except Exception as e:
                _p(f"  skip tai loi ({e}) {h['title'][:50]}")
                continue
            if len(data) < 30_000:
                continue
            ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
            img = os.path.join(tmpdir, hashlib.md5(
                h["url"].encode()).hexdigest()[:10] + ext)
            with open(img, "wb") as f:
                f.write(data)
            got_imgs[h["title"]] = img
        src_img, center = _prep_image(img, var, tmpdir)
        out_path = None
        while idx < ST.MAX_IDX:
            p_, _h = ST._cache_path(root, "wiki", key, idx)
            idx += 1
            if not os.path.exists(p_):
                out_path = p_
                break
        if not out_path:
            break
        # huong zoom/pan doi theo variant: crop thu hai cua anh ngang = pan khac
        if _ken_burns(src_img, out_path, idx - 1 + var, center=center):
            made += 1
            if credits is not None:
                credits.append({
                    "keyword": key, "ent": ent, "file": os.path.basename(out_path),
                    "title": h["title"], "license": h["license"],
                    "credit": h["credit"], "variant": var,
                    "page": "https://commons.wikimedia.org/wiki/"
                            + urllib.parse.quote(h["title"].replace(" ", "_")),
                })
    _p(f"  +{made} shot  ent={ent} ({len(got_imgs)} anh khac nhau)")
    return made, len(hits)


def keywords_from_config(root):
    """Doc config.json -> list keyword cua moi cell type=stock (giu thu tu)."""
    cfg_path = os.path.join(root, "config.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    seen, out = set(), []
    for c in cfg.get("cells", []):
        if c.get("type") != "stock":
            continue
        k = c.get("stock") or c.get("keyword") or ""
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def fetch_for_keyword(root, keyword, per=6, force=False, credits=None):
    """Tai toi da `per` anh Commons cho keyword CANH (khong ent) -> kho "wiki".

    Full-text search Commons voi cau chung chung tra ve anh ngau nhien, nen
    chi giu anh co it nhat 1 tu dac trung cua keyword trong TEN FILE
    (_title_score >= 1). Thieu thi thoi — photo/stock lap cho trong.
    """
    need = []
    for i in range(ST.MAX_IDX):
        if len(need) >= per:
            break
        path, _h = ST._cache_path(root, "wiki", keyword, i)
        if os.path.exists(path) and not force:
            continue
        need.append((i, path))
    if not need:
        _p(f"  ok (da co) {keyword}")
        return 0

    hits = search_commons(keyword, limit=max(30, per * 5), want=per * 4)
    hits = [h for h in hits if _title_score(h["title"], keyword) >= 1]
    if not hits:
        _p(f"  MISS khong co anh khop ten: {keyword}")
        return 0

    tmpdir = os.path.join(root, "build", "tmp", "wiki")
    os.makedirs(tmpdir, exist_ok=True)
    made, used_titles = 0, set()
    hit_i = 0
    for idx, out_path in need:
        img = h = None
        while hit_i < len(hits):
            h = hits[hit_i]
            hit_i += 1
            if h["title"] in used_titles:
                continue
            try:
                data = _get(h["url"], timeout=45)
            except Exception as e:
                _p(f"  skip tai loi ({e}) {h['title'][:50]}")
                continue
            if len(data) < 30_000:      # anh qua nho / loi
                continue
            ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
            img = os.path.join(tmpdir, hashlib.md5(
                h["url"].encode()).hexdigest()[:10] + ext)
            with open(img, "wb") as f:
                f.write(data)
            used_titles.add(h["title"])
            break
        if not img:
            break
        src_img, center = _prep_image(img, 0, tmpdir)
        if _ken_burns(src_img, out_path, idx, center=center):
            made += 1
            if credits is not None:
                credits.append({
                    "keyword": keyword, "file": os.path.basename(out_path),
                    "title": h["title"], "license": h["license"],
                    "credit": h["credit"],
                    "page": "https://commons.wikimedia.org/wiki/"
                            + urllib.parse.quote(h["title"].replace(" ", "_")),
                })
    _p(f"  +{made} shot  {keyword}")
    return made


def _ghi_credits(root, credits):
    cpath = os.path.join(root, "build", "wiki-credits.json")
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


def fetch_all(root, per=6, force=False, workers=3, ent_only=False):
    """Hai viec, deu chi tai PHAN CON THIEU theo thoi luong cell:

    1. Moi `ent` (marker ent=): anh tu lieu that — bai Wikipedia + Commons
       Category. So shot = tong giay cac cell cua ent / SHOT_SEC + 1.
    2. Keyword canh (cell khong ent, hoac ent con thieu anh): full-text search
       nhu cu, tran `per`. ent_only=True bo buoc nay (dung khi queue.yml khong
       chon wiki nhung script co ent — xem auto/steps.step_images).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    t0 = time.monotonic()
    with open(os.path.join(root, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    credits, total = [], 0
    ents = ST.ent_demand(root, cfg)
    found = {}
    if ents:
        print(f"wiki: {len(ents)} thuc the (ent), {workers} luong")
        used, lock = set(), threading.Lock()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(fetch_entity, root, e,
                              ST.n_files_for(sec), credits, used, lock): e
                    for e, (sec, _ids) in sorted(ents.items(),
                                                 key=lambda kv: -kv[1][0])}
            for fu in as_completed(futs):
                try:
                    made, n_real = fu.result()
                    total += made
                    found[futs[fu]] = n_real
                except Exception as e:
                    _p(f"  ERR ent={futs[fu]}: {e}")
        # Log theo CELL: nguoi dung soat script theo cell, khong theo ent.
        for c in ST.stock_cells(cfg):
            e = ST.cell_ent(c)
            if not e:
                continue
            n_have = len(ST.stock_files(root, ST.ent_key(e)))
            _p(f"  cell {c.get('id'):>3} ent={e}: {found.get(e, 0)} anh tu lieu "
               f"that, {n_have} shot trong kho"
               + ("" if n_have else "  <- THIEU, se roi ve keyword canh"))
    if not ent_only:
        need = {k: min(n, per) for k, n in
                ST.kw_demand(root, cfg, cap=per).items() if n > 0}
        print(f"wiki: {len(need)} keyword canh con thieu hinh, tran {per}/keyword")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(fetch_for_keyword, root, kw, n, force, credits): kw
                    for kw, n in need.items()}
            for fu in as_completed(futs):
                try:
                    total += fu.result()
                except Exception as e:
                    _p(f"  ERR {futs[fu]}: {e}")
    cpath = _ghi_credits(root, credits)
    print(f"wiki: tao {total} shot trong {time.monotonic() - t0:.0f}s. "
          f"Credit -> {cpath}")
    ST.enforce_cache_limit(root, protect=ST.files_of_config(root, cfg))
    return total


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--per", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--keyword", default=None)
    ap.add_argument("--ent", default=None, help="chi tai anh tu lieu cho 1 ent")
    ap.add_argument("--ent-only", action="store_true")
    a = ap.parse_args()
    if a.ent:
        cr = []
        fetch_entity(a.root, a.ent, a.per, credits=cr)
        _ghi_credits(a.root, cr)
    elif a.keyword:
        cr = []
        fetch_for_keyword(a.root, a.keyword, per=a.per, force=a.force,
                          credits=cr)
        _ghi_credits(a.root, cr)
    else:
        fetch_all(a.root, per=a.per, force=a.force, ent_only=a.ent_only)


if __name__ == "__main__":
    main()
