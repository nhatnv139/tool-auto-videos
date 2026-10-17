"""
script2config.py — Doc script.md sinh config.json.

Dinh dang script.md (nguon su that duy nhat, thu tu = timeline):

    # Tieu de video (bo qua)

    ## Cold open           (bo qua — ten phan)

    [[clip:1]]
    This is the most dangerous bet.       -> VO, tao cell card tu dong
    [[broll:2]]
    And researchers found...              -> VO de len b-roll clip 2
    [[card:"6x more persuasive"|src=arxiv:2603.25326]]   -> card im lang
    [[quote:"They're like sociopaths."|who=Yoshua Bengio|role=Turing Award winner]]
    [[black]]
    It wasn't a test.                     -> VO tren man hinh den
    [[sfx]]
    [[clip-mute:1]]                       -> nhu broll

Marker:
  [[clip:ID]]            clip talking-head, giu tieng goc, khong co VO
  [[broll:ID]]           clip-mute: lay hinh clip ID, tat tieng, VO doc de
  [[clip-mute:ID]]       alias cua broll
  [[stock:"server room ai"]]  stock footage (Pixabay/Pexels), VO doc de
  [[stock:"canh"|ent="Qianlong Emperor"]]  uu tien anh tu lieu THAT cua ent
                         (bai Wikipedia EN + Commons Category), canh la duong lui
  [[wiki:"Qianlong Emperor"]]  = stock voi keyword rong + ent
  [[card:"text"|src=...]]   card im lang (khong VO), text + nguon
  [[quote:"text"|who=..|role=..]]   quote im lang + attribution
  [[black]] / [[hold]] / [[sfx]]     cac cell khac
  [[outro]]

Hang text binh thuong = VO. VO duoc gan vao cell loai "vo-type":
  - sau [[broll:ID]] -> cell clip-mute co vo
  - sau [[black]]    -> cell black co vo
  - sau [[hold]]     -> cell hold co vo
  - sau [[card:...]] im lang -> VO tao cell card moi (co text + vo)
  - con lai          -> cell card moi (nen toi, text = dong dau)

pause_after: them "|pause=1.5" vao bat ky marker hoac cuoi dong VO.
music: them "|music=swell" vao marker.
"""
import json
import os
import re
import sys

VO_TYPES = {"card", "black", "hold", "clip-mute", "stock"}

MARKER_RE = re.compile(r"^\[\[(.+?)\]\]\s*$")
PAUSE_RE = re.compile(r"\|pause=([\d.]+)")
MUSIC_RE = re.compile(r"\|music=(in|out|drop|swell)")
FX_RE = re.compile(r"\|fx=([a-z-]+)")
LOW_RE = re.compile(r"\|low\b")
DUR_RE = re.compile(r"\|dur=([\d.]+)")

# --- chuong: cat (16/10/2026) ------------------------------------------------
# Kieu cu: [[black|pause=2.5]] + "Phan mot. // <cau hoi>" -> 2,5s man den roi
# nguoi doc xuong giong "Phan mot" — nguoi xem goi la "sao chuyen lai chuong 1
# chuong 2 cai gi", mat da ke. Kieu `cat`: marker [[black]] thanh DIEM CHUYEN
# CHUONG (flash + whoosh + nhac day len + tieu de nho tren hinh ke tiep), cau
# "Phan <so>." bi boc khoi loi doc, cau hoi chuong duoc noi vao dau cell hinh
# ngay sau. Script cu khong phai sua.
CHUONG_NGHI = 0.9   # giay lang truoc diem chuyen chuong (kieu cat)
_SO_CHU = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "sáu": 6,
           "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
CHUONG_RE = re.compile(
    r"^\s*\^?\s*(?:phần|chương|hồi)\s+(\d+|cuối|mười\s+\w+|"
    + "|".join(sorted(_SO_CHU, key=len, reverse=True))
    + r")\s*[.:!\-–—]?\s*(?:/{2,4}|\|)?\s*", re.IGNORECASE)


def tach_chuong(text):
    """'Phần một. // Vì sao ...?' -> ('1', 'Vì sao ...?'). Khong khop -> (None, text)."""
    m = CHUONG_RE.match(text or "")
    if not m:
        return None, text
    w = m.group(1).lower()
    if w.isdigit():
        so = w
    elif w == "cuối":
        so = "cuối"
    elif w.startswith("mười") and w != "mười":
        tail = w.split()[-1]
        so = str(10 + {"một": 1, "mốt": 1, "lăm": 5, "tư": 4}.get(tail, _SO_CHU.get(tail, 0)))
    else:
        so = str(_SO_CHU.get(w, w))
    rest = text[m.end():].strip()
    return so, rest


class ParseError(Exception):
    pass


# map clip id -> (speaker, role) doc tu clip-manifest.json (nap o build)
_CLIP_ATTR = {}


def _load_clip_attr(video_root):
    """Doc clip-manifest.json -> {clip_id: "speaker — role"}."""
    global _CLIP_ATTR
    import json as _json
    path = os.path.join(video_root, "clip-manifest.json")
    _CLIP_ATTR = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                for c in _json.load(f):
                    who = c.get("speaker", "")
                    role = c.get("role", "")
                    at = who + (f" - {role}" if role else "")
                    if at:
                        _CLIP_ATTR[c["id"]] = at
        except Exception:
            pass


def _set_attribution(cell, clip_id):
    """Gan src = 'speaker - role' vao cell (de render_clip hien chú thích)."""
    at = _CLIP_ATTR.get(clip_id)
    if at:
        cell["src"] = at.replace("—", "-").replace("–", "-")


def _parse_card(text):
    """Parse 'text'|src=... -> (quote, src)"""
    parts = [p.strip() for p in text.split("|")]
    body = parts[0].strip('"').strip()
    kv = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k.strip()] = v.strip().strip('"')
    return body, kv


def _parse_stock(clean):
    """'stock:"canh"|ent="Qianlong Emperor"' -> ("canh", "Qianlong Emperor").

    `ent` = ten bai Wikipedia tieng Anh / Commons category cua nhan vat, dia
    danh, su kien, hien vat ma canh nay noi toi. Co ent -> hinh lay tu lieu
    THAT cua thuc the do truoc (wiki_images.fetch_entity), keyword canh chi con
    la duong lui. Bi danh: 'wiki:"Qianlong Emperor"' = stock keyword rong + ent.
    Marker cu [[stock:"kw"]] (khong ent) giu nguyen nghia.
    """
    kind, rest = clean.split(":", 1)
    body, kv = _parse_card(rest)
    ent = (kv.get("ent") or "").strip().strip('"').strip()
    if kind == "wiki":
        return "", (ent or body)
    return body, ent


def _strip_opts(marker):
    """Bo cac tuy chon |pause, |music, |fx, |low ra khoi marker."""
    pause = 0.0
    music = None
    fx = None
    low = False
    dur = None
    m = PAUSE_RE.search(marker)
    if m:
        pause = float(m.group(1))
    m = MUSIC_RE.search(marker)
    if m:
        music = m.group(1)
    m = FX_RE.search(marker)
    if m:
        fx = m.group(1)
    if LOW_RE.search(marker):
        low = True
    m = DUR_RE.search(marker)
    if m:
        dur = float(m.group(1))
    clean = PAUSE_RE.sub("", marker)
    clean = MUSIC_RE.sub("", clean)
    clean = FX_RE.sub("", clean)
    clean = LOW_RE.sub("", clean)
    clean = DUR_RE.sub("", clean)
    return clean, {"pause_after": pause, "music": music, "fx": fx,
                   "low": low, "dur": dur}


def parse_script(path, chuong=None):
    cells = []
    vo_buf = []
    pending = None       # marker dang cho VO de gan vao
    pending_sfx = []     # sfx cho cell ke tiep (khong tao cell rieng)
    chuong_cat = str(chuong or "").strip().lower() == "cat"
    chap = {"n": 0, "cho": None}   # chuong dang cho gan vao cell hinh ke tiep

    def _gan_chuong(cell):
        """chuong: cat — gan diem chuyen chuong vao cell sap them."""
        c = chap["cho"]
        if c is None:
            return
        chap["cho"] = None
        if cell["type"] not in VO_TYPES or cell["type"] == "card" and not cell.get("vo"):
            # khong co hinh de de cau hoi len (clip co tieng, quote...) -> giu
            # mot cell den ngan mang cau hoi nhu cu, chi bo "Phan mot".
            if c["vo"]:
                cells.append({"type": "black", "vo": c["vo"], "music": "swell",
                              "pause_after": 0.3, "chuong": c["meta"]})
            return
        if c["vo"]:
            cell["vo"] = (c["vo"].rstrip() + " // " + (cell.get("vo") or "")).strip()
            if cell.get("cap"):
                cell["cap"] = cell["vo"]
        cell["chuong"] = c["meta"]
        cell["music"] = "swell"

    def _mo_chuong(vo_text, tieu_de=None):
        chap["n"] += 1
        so, rest = tach_chuong(vo_text or "")
        so = so or str(chap["n"])
        from tts import strip_marks
        if tieu_de is None:
            tieu_de = strip_marks(rest).strip()
        else:
            tieu_de = strip_marks(tieu_de).strip()
        # Mot nhip ngan truoc diem chuyen chuong cho whoosh + nhac day len
        # (<= ~1s, thay cho 2,5-3s man den/the im lang). Cell truoc da ket bang
        # /// hoac //// thi da co san khoang lang, khong cong them.
        if cells:
            last = cells[-1]
            if not (last.get("vo") or "").rstrip().endswith("///"):
                last["pause_after"] = max(float(last.get("pause_after") or 0.0),
                                          CHUONG_NGHI)
        chap["cho"] = {"vo": rest.strip(),
                       "meta": {"so": so, "tieu_de": tieu_de}}
        print(f"  chuong {so}: cat (khong man den)"
              + (f" — '{tieu_de[:50]}'" if tieu_de else ""))

    def add_cell(cell):
        """Gan pending_sfx vao cell roi append."""
        if chuong_cat:
            _gan_chuong(cell)
        if pending_sfx:
            cell["sfx"] = pending_sfx[0]["name"]
            cell["sfx_at"] = pending_sfx[0].get("at", 0.0)
            cell["sfx_dur"] = pending_sfx[0].get("dur")
            if pending_sfx[0].get("vol"):
                cell["sfx_vol"] = pending_sfx[0]["vol"]
            del pending_sfx[0]
        cells.append(cell)

    def flush_pending_silent():
        """[[black]]/[[hold]] khong co VO theo sau VAN la mot nhip co chu dich.

        Ban cu de no treo cho VO; gap ngay tieu de chuong (dong '#') thi marker
        bi ghi de va mat hut, khong mot canh bao. Do la ly do 7 diem ngat chuong
        5 giay cua script cay-da khong he ton tai trong video dung ra.
        """
        nonlocal pending
        if pending is None:
            return
        if chuong_cat and pending["type"] == "black":
            pending = None
            _mo_chuong("")
            return
        extra = dict(pending["extra"])
        dur = extra.pop("pause_after", 0.0) or 0.0
        if dur > 0:
            add_cell({"type": pending["type"], **extra,
                      "dur": float(dur), "pause_after": 0.0})
            print(f"  nhip im lang {dur:.1f}s ({pending['type']}) — ngat chuong")
        pending = None

    def flush_vo():
        nonlocal vo_buf, pending
        if not vo_buf:
            return
        text = " ".join(vo_buf).strip()
        vo_buf = []
        if pending is None:
            # tao cell card moi, text = dong dau lam caption
            add_cell({"type": "card", "vo": text, "cap": text,
                      "pause_after": 0.15})
        elif chuong_cat and pending["type"] == "black":
            pending = None
            _mo_chuong(text)
        else:
            # gan vo vao cell pending (clip-mute/black/hold/card)
            extra = dict(pending["extra"])
            if not extra.get("pause_after"):
                extra["pause_after"] = 0.15
            add_cell({"type": pending["type"], **extra, "vo": text})
            # pending da tieu thu: dong VO sau do phai tao cell card moi,
            # khong dung lai marker cu
            pending = None

    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    heading = None          # dong '## ...' ngay truoc (tieu de chuong kieu v3)
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("##"):
                heading = line.lstrip("#").strip()
            continue
        m = MARKER_RE.match(line)
        if m:
            flush_vo()
            flush_pending_silent()   # marker moi -> marker cu khong con cho VO
            marker = m.group(1)
            clean, opts = _strip_opts(marker)
            if clean.startswith("clip:"):
                cid = int(clean.split(":", 1)[1].split("|")[0])
                cell = {"type": "clip", "clip": cid,
                        "dur": None, "music": opts["music"] or "in",
                        "pause_after": opts["pause_after"],
                        "fx": opts["fx"]}
                _set_attribution(cell, cid)
                add_cell(cell)
            elif clean.startswith(("broll:", "clip-mute:")):
                cid = int(clean.split(":", 1)[1].split("|")[0])
                extra = {"clip": cid, "music": opts["music"] or "in",
                         "pause_after": opts["pause_after"],
                         "fx": opts["fx"], "low": opts["low"]}
                _set_attribution(extra, cid)
                pending = {"type": "clip-mute", "consumed": False, "extra": extra}
            elif clean.startswith(("stock:", "wiki:")):
                kw, ent = _parse_stock(clean)
                extra = {"stock": kw, "music": opts["music"] or "in",
                         "pause_after": opts["pause_after"], "fx": opts["fx"]}
                if ent:
                    extra["ent"] = ent
                pending = {"type": "stock", "consumed": False, "extra": extra}
            elif (chuong_cat and clean.startswith("card:")
                  and not _parse_card(clean[len("card:"):])[1].get("vo")
                  and not _parse_card(clean[len("card:"):])[1].get("src")
                  and (opts["music"] == "swell" or heading)):
                # Kieu v3: '## <cau hoi>' + [[card:"<cau hoi>"|music=swell]] =
                # the tieu de im lang 3s. Kieu cat: khong dung the, tieu de nho
                # de len hinh ke tiep + chuyen canh chuong.
                body, _kv = _parse_card(clean[len("card:"):])
                _mo_chuong("", tieu_de=body or heading or "")
            elif clean.startswith("card:"):
                body, kv = _parse_card(clean[len("card:"):])
                cell = {"type": "card", "text": body, "src": kv.get("src", ""),
                        "dur": float(kv.get("dur", 3.0)),
                        "music": opts["music"] or "out",
                        "pause_after": opts["pause_after"]}
                if kv.get("vo"):
                    cell["vo"] = kv["vo"].strip('"')
                    cell["cap"] = cell["vo"]
                add_cell(cell)
            elif clean.startswith("quote:"):
                body, kv = _parse_card(clean[len("quote:"):])
                pause = opts["pause_after"] or 0.8
                add_cell({"type": "quote", "text": body,
                          "who": kv.get("who", ""), "role": kv.get("role", ""),
                          "dur": float(kv.get("dur", 4.5)),
                          "music": opts["music"] or "in",
                          "pause_after": pause})
            elif clean == "black":
                pending = {"type": "black", "consumed": False,
                           "extra": {"music": opts["music"] or "drop",
                                     "pause_after": opts["pause_after"],
                                     "fx": opts["fx"]}}
            elif clean == "hold":
                pending = {"type": "hold", "consumed": False,
                           "extra": {"music": opts["music"] or "in",
                                     "pause_after": opts["pause_after"],
                                     "fx": opts["fx"]}}
            elif clean == "sfx":
                # noise hit tu sinh, de len cell ke tiep
                pending_sfx.append({"name": None, "at": 0.0,
                                    "dur": opts["dur"]})
            elif clean.startswith("sfx:"):
                name = clean[len("sfx:"):].strip()
                pending_sfx.append({"name": name, "at": 0.0,
                                    "dur": opts["dur"]})
            elif clean == "outro":
                add_cell({"type": "outro", "dur": 12.0,
                          "music": opts["music"] or "in"})
            else:
                raise ParseError(f"marker khong hieu: {marker}")
            heading = None
            continue
        # dong text thuong -> VO
        vo_buf.append(line)
    flush_vo()
    flush_pending_silent()
    if chuong_cat and chap["cho"] is not None and chap["cho"]["vo"]:
        cells.append({"type": "black", "vo": chap["cho"]["vo"], "music": "swell",
                      "pause_after": 0.3, "chuong": chap["cho"]["meta"]})
    if pending_sfx:
        # sfx treo cuoi script: bo qua (khong co cell de gan)
        print(f"  WARN {len(pending_sfx)} sfx treo cuoi script (khong co cell ke) — bo qua")
    return cells


def build(video_root, chuong=None, chuyen_canh=None):
    """chuong: None/'den' = kieu cu | 'cat' = chuyen chuong khong man den.
    chuyen_canh: None = cat thang (cu) | 'nhe' = chuyen canh co chu dich (xem
    assemble.chon_chuyen_canh). Ca hai ghi vao cfg["dung"] de render/assemble
    doc — config cu khong co khoa nay nen chay y nhu truoc."""
    _load_clip_attr(video_root)
    script = os.path.join(video_root, "script", "script.md")
    if not os.path.exists(script):
        raise ParseError(f"thieu {script}")
    cells = parse_script(script, chuong=chuong)
    if not cells:
        raise ParseError("script.md khong co noi dung")

    cells_out = []
    idx = 0
    for c in cells:
        idx += 1
        cell = {"id": idx, "type": c["type"]}
        for k, v in c.items():
            if k == "type":
                continue
            cell[k] = v
        if cell["type"] == "clip" and cell.get("dur") is None:
            # dur se duoc do tu clip thuc te trong assemble
            cell["dur"] = None
        if "vo" in cell and "cap" not in cell:
            cell["cap"] = cell["vo"]
        # Ky tu ngat nghi ('//', '///', '|', '^', '*') la lenh nhip cho TTS,
        # khong phai chu. Giu nguyen trong "vo" (plan_units can chung), nhung
        # boc khoi "cap" ngay tu day de config sach — assemble van boc mot lan
        # nua, nhung moi duong khac doc "cap" thi khong phai nho.
        if cell.get("cap"):
            from tts import strip_marks
            cell["cap"] = strip_marks(cell["cap"])
        cells_out.append(cell)

    cfg = {
        "name": os.path.basename(video_root),
        "out": "build/final/video-1.mp4",
        "fps": 24, "w": 1920, "h": 1080,
        "style": {"ink": "#14110F", "paper": "#F2EDE4", "amber": "#E0A82E",
                  "font_reg": "tool/fonts/arial.ttf",
                  "font_bold": "tool/fonts/arialbd.ttf"},
        "music": {"file": "assets/music/bed.wav", "level": 0.16,
                  "fade_in": 1.5, "fade_out": 3.0},
        "caption": {"on": True, "font": "tool/fonts/arialbd.ttf",
                    "size": 46, "color": "#FFFFFF", "y": 920},
        "cells": cells_out,
    }
    dung = {}
    if str(chuong or "").strip().lower() == "cat":
        dung["chuong"] = "cat"
    if chuyen_canh and str(chuyen_canh).strip().lower() not in ("", "off", "cat-thang"):
        dung["chuyen_canh"] = str(chuyen_canh).strip().lower()
    if dung:
        cfg["dung"] = dung
    out = os.path.join(video_root, "config.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    n_vo = len([c for c in cells_out if c.get("vo")])
    n_clip = len([c for c in cells_out if c["type"] in ("clip", "clip-mute")])
    print(f"OK: {len(cells_out)} cell (VO: {n_vo}, clip: {n_clip}) -> config.json")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default="videos/test-60s")
    ap.add_argument("--chuong", default=None)
    ap.add_argument("--chuyen-canh", default=None, dest="chuyen_canh")
    a = ap.parse_args()
    build(a.root, chuong=a.chuong, chuyen_canh=a.chuyen_canh)
