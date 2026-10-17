# -*- coding: utf-8 -*-
"""loat_su_viet.py — dung + dang mot loat video su Viet, khong can nguoi ngoi canh.

Moi slug, lan luot:
  1. cho videos/<slug>/.san_sang (danh dau khi script + youtube_meta.json da duyet);
     bai nao san sang truoc thi dung truoc
  2. cho RAM trong >= RAM_GB; thieu thi doi 10 phut roi xem lai
  3. lam-di.cmd --slug <slug>  (runner tu resume neu dut)
  4. ghi OUTBOX/<ngay>-<slug>/youtube.json (hen 20:00 VN, ngay sau lich hen muon nhat)
     + thumbnail.jpg (anh Wikipedia cua thumb_ent, du phong: frame giua video)
  5. dang_youtube.dang() -> hen gio xong thi tu xoa video + build (luat 08/10/2026)

    python auto\\loat_su_viet.py --bat-dau 2026-10-14 slug1 slug2 ...
Chay lai an toan: slug da co youtube_result.json mang id thi bo qua.
"""
import argparse
import ctypes
import datetime as dt
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "auto"))
CHANNEL = "UCwYFCjHoklXeKrFvYMg9Mng"  # Yeu Lich su
RAM_GB = 5.0
FONT = "C:/Windows/Fonts/segoeuib.ttf"


def log(s):
    line = f"[{dt.datetime.now():%m-%d %H:%M}] {s}"
    print(line, flush=True)
    with open(KIT / "auto" / "logs" / "loat_su_viet.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ram_trong_gb():
    class M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = M()
    m.dwLength = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1e9


def cho_ram():
    while (g := ram_trong_gb()) < RAM_GB:
        log(f"  RAM trong {g:.1f} GB < {RAM_GB} -> doi 10 phut")
        time.sleep(600)


def outbox_cua(slug):
    ds = sorted(d for d in (KIT / "OUTBOX").glob(f"*-{slug}") if d.is_dir())
    return ds[-1] if ds else None


def anh_wiki(ent):
    for lang in ("vi", "en"):
        url = (f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
               + urllib.parse.quote(ent.replace(" ", "_")))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "yeulichsu-thumb/1.0"})
            j = json.load(urllib.request.urlopen(req, timeout=30))
            src = (j.get("originalimage") or j.get("thumbnail") or {}).get("source")
            if src and not src.lower().endswith(".svg"):
                req = urllib.request.Request(src, headers={"User-Agent": "yeulichsu-thumb/1.0"})
                return urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:  # noqa: BLE001
            log(f"  wiki {lang}:{ent} loi {e}")
    return None


def frame_video(video, giay=90):
    out = video.parent / "_frame.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(giay), "-i", str(video),
                    "-frames:v", "1", str(out)], check=False)
    if out.exists():
        b = out.read_bytes()
        out.unlink()
        return b
    return None


def _chu_vien(dr, xy, text, font, fill, vien=6):
    dr.text(xy, text, font=font, fill=fill, stroke_width=vien, stroke_fill=(0, 0, 0))


def lam_thumb(meta, anh_bytes, out):
    from PIL import Image, ImageDraw, ImageFont, ImageEnhance
    W, H = 1280, 720
    img = Image.open(io.BytesIO(anh_bytes)).convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x0, y0 = (img.width - W) // 2, max(0, int((img.height - H) * 0.08))  # anh chan dung: giu mat o tren
    img = img.crop((x0, y0, x0 + W, y0 + H))
    img = ImageEnhance.Contrast(img).enhance(1.15)
    # toi dan phia duoi cho chu noi
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(max(0, (y - H * 0.45) / (H * 0.55)) * 200))
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), grad.resize((W, H)))
    dr = ImageDraw.Draw(img)
    badge = meta.get("thumb_badge")
    if badge:
        f = ImageFont.truetype(FONT, 34)
        w = dr.textlength(badge, font=f)
        dr.rounded_rectangle((42, 34, 42 + w + 32, 34 + 54), 10, fill=(178, 28, 28))
        dr.text((58, 38), badge, font=f, fill=(255, 255, 255))
    big = meta.get("thumb_text", "").upper()
    size = 92
    while size > 40:
        fb = ImageFont.truetype(FONT, size)
        if dr.textlength(big, font=fb) <= W - 100:
            break
        size -= 4
    _chu_vien(dr, (50, 515), big, fb, (255, 214, 0), 7)
    sub = meta.get("thumb_sub", "")
    if sub:
        n = 50
        while n > 30 and dr.textlength(sub, font=ImageFont.truetype(FONT, n)) > W - 100:
            n -= 2
        fs = ImageFont.truetype(FONT, n)
        _chu_vien(dr, (54, 620), sub, fs, (255, 255, 255), 4)
    img.save(out, quality=92)


def ngay_trong_ke_tiep(tu_ngay):
    """Ngay sau lich hen muon nhat da co tren kenh (khong de lo trong lich)."""
    muon = tu_ngay - dt.timedelta(days=1)
    for r in (KIT / "OUTBOX").glob("*/youtube_result.json"):
        try:
            p = json.loads(r.read_text(encoding="utf-8")).get("publish_at")
            if p:
                muon = max(muon, (dt.datetime.fromisoformat(p.replace("Z", "+00:00"))
                                  + dt.timedelta(hours=7)).date())
        except (OSError, ValueError):
            pass
    return max(muon + dt.timedelta(days=1), dt.date.today() + dt.timedelta(days=1))


def chuan_bi_outbox(slug, ngay):
    case = KIT / "videos" / slug
    meta = json.loads((case / "youtube_meta.json").read_text(encoding="utf-8"))
    ob = outbox_cua(slug)
    if not ob or not (ob / "video.mp4").exists():
        raise RuntimeError(f"{slug}: khong thay OUTBOX/video.mp4")
    yt = {"title": meta["title"][:100],
          "publish_at": f"{ngay.isoformat()}T20:00:00+07:00",
          "channel": CHANNEL,
          "description": meta["description"],
          "tags": meta.get("tags", [])}
    (ob / "youtube.json").write_text(json.dumps(yt, ensure_ascii=False, indent=2), encoding="utf-8")
    if not (ob / "thumbnail.jpg").exists():
        b = anh_wiki(meta["thumb_ent"]) if meta.get("thumb_ent") else None
        b = b or frame_video(ob / "video.mp4")
        lam_thumb(meta, b, ob / "thumbnail.jpg")
    return ob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bat-dau", default=None, help="ngay som nhat duoc len song, YYYY-MM-DD")
    ap.add_argument("slugs", nargs="+")
    a = ap.parse_args()
    d0 = dt.date.fromisoformat(a.bat_dau) if a.bat_dau else dt.date.today()
    import dang_youtube
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    con = list(a.slugs)
    import don_dep
    while con:
        # quet: bai da dang ma video/build con sot (vd file bi khoa luc dang) -> xoa
        for x in a.slugs:
            n, _ = don_dep.xoa_da_dang(str(KIT / "videos" / x), that=True, im=True)
            if n:
                log(f"{x}: xoa sot {n / 1e9:.2f} GB")
        # bai nao da duoc duyet (co file .san_sang) thi dung truoc
        san = [x for x in con if (KIT / "videos" / x / ".san_sang").exists()]
        if not san:
            log(f"cho duyet: {', '.join(con)}")
            time.sleep(300)
            continue
        slug = san[0]
        con.remove(slug)
        ob = outbox_cua(slug)
        if ob and (ob / "youtube_result.json").exists():
            log(f"{slug}: da dang roi, bo qua")
            continue
        cho_ram()
        log(f"{slug}: bat dau dung")
        rc = subprocess.call(["cmd", "/c", str(KIT / "lam-di.cmd"), "--slug", slug],
                             cwd=str(KIT), env=env)
        if rc != 0:
            log(f"{slug}: runner hong (ma {rc}) — bo qua, xem auto/logs")
            continue
        try:
            ngay = ngay_trong_ke_tiep(d0)
            ob = chuan_bi_outbox(slug, ngay)
            dang_youtube.dang_chac(ob)
            log(f"{slug}: da dang, hen {ngay} 20:00")
        except Exception as e:  # noqa: BLE001
            log(f"{slug}: LOI dang {str(e)[:300]}")
    log("XONG LOAT")


if __name__ == "__main__":
    main()
