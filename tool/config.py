"""
config.py — Config chuan cho 1 video (video-driven, khong hardcode).

Moi video = 1 thu muc: videos/<topic>/config.json.
Toan bo pipeline (script2config -> render -> tts -> music -> assemble)
doc file nay.

Schema:
{
  "name": "test-60s",
  "out": "build/final/video-1.mp4",
  "fps": 24, "w": 1920, "h": 1080,
  "style": {"ink": "#14110F", "paper": "#F2EDE4", "amber": "#E0A82E",
            "font_reg": "tool/fonts/arial.ttf", "font_bold": "tool/fonts/arialbd.ttf"},
  "music": {"file": "assets/music/bed.wav", "level": 0.16, "fade_in": 1.5, "fade_out": 3.0},
  "caption": {"on": true, "font": "tool/fonts/arialbd.ttf", "size": 44,
              "color": "#FFFFFF", "y": 940},
  "cells": [ ... ]
}

Cell:
  id        so cell (thu tu theo script)
  type      clip | clip-mute | card | quote | hold | black | sfx | outro
  dur       do dai tieu de (giay) — bat buoc neu khong co vo
  vo        text de TTS doc (cell clip-mute/card/quote thong thuong co vo)
  pause_after  im lang chen sau VO (giay) — "let it land" beat
  music     in | out | drop | swell — cach nhac nen
  src       attribution / nguon hien len hinh (vi du "Yoshua Bengio — Turing Award")

Loai clip:
  clip        talking-head, giu tieng goc
  clip-mute   b-roll: lay hinh clip nguon, tat tieng, VO doc de
  card        text tren nen toi (so lieu, claim)
  quote       quote lon + attribution
  hold        dung yen khung cuoi shot truoc
  black       man hinh den (cat den cho beat)
  sfx         hieu ung hit (audio + video den)
  outro       danh sach video lien quan / link nguon

Timeline: cell_start[i] = tong(cell_dur) truoc no; cell_dur = vo_dur +
pause_after neu co VO, nguoc lai dung 'dur'.
"""
import json
import os

CELL_TYPES = {"clip", "clip-mute", "card", "quote", "hold", "black", "sfx", "outro",
              "stock"}
MUSIC_MODES = {"in", "out", "drop", "swell"}


class ConfigError(Exception):
    pass


def load(case_root, cfg_path="config.json"):
    path = os.path.join(case_root, cfg_path)
    if not os.path.exists(path):
        raise ConfigError(f"thieu {path} — chay script2config truoc")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    validate(data)
    return data


def validate(d):
    for k in ("name", "out", "cells"):
        if k not in d:
            raise ConfigError(f"thieu '{k}' trong config")
    if not isinstance(d["cells"], list) or not d["cells"]:
        raise ConfigError("'cells' phai la danh sach khong trong")
    seen = set()
    for i, c in enumerate(d["cells"]):
        if "id" not in c:
            raise ConfigError(f"cells[{i}] thieu 'id'")
        if c["id"] in seen:
            raise ConfigError(f"trung cell id {c['id']}")
        seen.add(c["id"])
        t = c.get("type")
        if t not in CELL_TYPES:
            raise ConfigError(f"cell {c['id']}: type '{t}' khong hop le ({sorted(CELL_TYPES)})")
        if "dur" not in c and "vo" not in c:
            raise ConfigError(f"cell {c['id']}: can 'dur' hoac 'vo'")
        if c.get("music") and c["music"] not in MUSIC_MODES:
            raise ConfigError(f"cell {c['id']}: music '{c['music']}' sai ({sorted(MUSIC_MODES)})")


def resolve(root, rel):
    """Ghep duong dan tuong doi (trong config) vao case root."""
    return os.path.join(root, rel) if not os.path.isabs(rel) else rel


def iter_cells(d):
    for c in d["cells"]:
        yield c


def style_of(d):
    s = d.get("style", {})
    return {
        "ink": s.get("ink", "#14110F"),
        "paper": s.get("paper", "#F2EDE4"),
        "amber": s.get("amber", "#E0A82E"),
        "font_reg": s.get("font_reg", "tool/fonts/arial.ttf"),
        "font_bold": s.get("font_bold", "tool/fonts/arialbd.ttf"),
    }


def caption_of(d):
    c = d.get("caption") or {"on": False}
    return {
        "on": c.get("on", False),
        "font": c.get("font", "tool/fonts/arialbd.ttf"),
        "size": c.get("size", 44),
        "color": c.get("color", "#FFFFFF"),
        "y": c.get("y", 940),
    }
