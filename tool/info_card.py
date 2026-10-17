"""
info_card.py — the so kieu INFOGRAPHIC (queue.yml `kieu_the: info`).

Phong cach kenh giai thich kinh te (Long / Vox / Kurzgesagt-lite):
nen xanh navy diu co vet mau troi + cham luoi troi + vong tron troi,
panel kem bo goc bong do mem, so to (Bahnschrift) dem dan, cot mọc len,
mau nhan: vang cam / xanh ngoc / do san ho (so giam).

Nhan dang 4 dang text card (+ du phong cho card cu):
  D1 `Nhan: GIA_TRI`                 -> so lon dem len, nhan phia tren
  D2 `Nhan: A → B`                   -> 2 panel truoc/sau + mui ten + % thay doi
  D3 `Tieu de: a = 1; b = 2; ...`    -> cot ngang moc len theo ti le
  D4 cau chot khong so (<= ~12 tu)   -> trich dan
  du phong: chuoi `A → B → C`, phep tinh `x = y ≈ z` (chip noi tiep),
            `a · b · c` (o so / danh sach), con lai: panel chu.

Vung an toan: noi dung trong y 70..770 (duoi la phu de burn), nhan
"Nguon: ..." goc duoi trai.

    render_info(out, dur, text=None, src="", seed=0, fps=24, venc=None)
text=None -> chi nen (thay [[black]]).
"""
import math
import os
import re
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from motion import FPS, H, W, KIT_ROOT, Writer, _blend, _fmt_num, _view

# ---------------------------------------------------------------- mau
NAVY0 = np.array([15, 25, 47], np.float32)
NAVY1 = np.array([27, 44, 78], np.float32)
CREAM = (250, 246, 238)
CREAM_D = (232, 227, 216)
TRACK = (234, 227, 213)
LINE = (226, 218, 203)
INK = (26, 37, 64)
INK2 = (102, 112, 134)
AMBER = (243, 166, 60)
AMBER_D = (212, 122, 20)
AMBER_L = (253, 235, 205)
TEAL = (28, 168, 148)
TEAL_D = (13, 138, 120)
TEAL_L = (212, 241, 234)
CORAL = (236, 99, 84)
CORAL_D = (214, 70, 58)
CORAL_L = (252, 224, 218)
SKY = (86, 142, 216)
ON_NAVY = (246, 241, 230)
ON_NAVY2 = (178, 190, 212)
SHADOW = (4, 9, 22)

# ---------------------------------------------------------------- font
_WINF = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _fp(*names):
    for n in names:
        p = os.path.join(_WINF, n)
        if os.path.exists(p):
            return p
    for n in ("arialbd.ttf", "arial.ttf"):
        p = os.path.join(KIT_ROOT, "tool", "fonts", n)
        if os.path.exists(p):
            return p
    return None


F_BOLD = _fp("segoeuib.ttf")
F_SEMI = _fp("seguisb.ttf", "segoeuib.ttf")
F_REG = _fp("segoeui.ttf")
F_NUM = _fp("bahnschrift.ttf", "seguibl.ttf", "segoeuib.ttf")
F_QUOTE = _fp("georgiab.ttf", "segoeuib.ttf")
_EMJ = os.path.join(_WINF, "seguiemj.ttf")
F_EMOJI = _EMJ if os.path.exists(_EMJ) else None
_FC = {}


def font(path, size, var=None):
    key = (path, int(size), var)
    if key not in _FC:
        f = ImageFont.truetype(path, max(8, int(size)))
        if var and path and path.lower().endswith("bahnschrift.ttf"):
            try:
                f.set_variation_by_name(var)
            except Exception:
                pass
        _FC[key] = f
    return _FC[key]


def fnum(size):
    return font(F_NUM, size, "Bold")


def fbold(size):
    return font(F_BOLD, size)


def fsemi(size):
    return font(F_SEMI, size)


def freg(size):
    return font(F_REG, size)


_D = ImageDraw.Draw(Image.new("RGB", (4, 4)))


def tl(text, f):
    return _D.textlength(text, font=f)


# ---------------------------------------------------------------- ve co ban
def _ease(p):
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3


def _back(p, k=1.5):
    p = min(1.0, max(0.0, p))
    q = p - 1
    return 1 + (k + 1) * q ** 3 + k * q ** 2


def rr_mask(w, h, r, ss=3):
    """Mat na bo goc khu rang cua (ve x3 roi thu nho)."""
    w, h = max(1, int(round(w))), max(1, int(round(h)))
    r = max(0, min(r, w / 2, h / 2))
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1),
                                        radius=int(r * ss), fill=255)
    return np.asarray(m.resize((w, h), Image.LANCZOS))


def solid(w, h, rgb, r=0, alpha=255):
    """RGBA PIL hinh chu nhat bo goc."""
    a = rr_mask(w, h, r) if r else np.full((int(h), int(w)), 255, np.uint8)
    a = (a.astype(np.float32) * alpha / 255).astype(np.uint8)
    arr = np.zeros(a.shape + (4,), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


def circle(d, rgb, alpha=255):
    return solid(d, d, rgb, r=d / 2, alpha=alpha)


M = 60  # le bong do quanh panel
_OY = 0.0  # dich doc toan bo cuc (make_scene can giua vung an toan)


def panel(w, h, fill=CREAM, r=30, shadow=0.55, blur=22, dy=16, stripe=None,
          stripe_h=12):
    """Panel bo goc + bong do mem. Tra ve PIL RGBA kich thuoc (w+2M, h+2M);
    noi dung ve tai offset (M, M)."""
    w, h = int(round(w)), int(round(h))
    A = np.zeros((h + 2 * M, w + 2 * M), np.float32)
    A[M:M + h, M:M + w] = rr_mask(w, h, r).astype(np.float32) / 255
    sh = np.zeros_like(A)
    sh[M + dy:M + dy + h, M:M + w] = A[M:M + h, M:M + w] * shadow
    sh = cv2.GaussianBlur(sh, (0, 0), blur)
    rgb = np.zeros(A.shape + (3,), np.float32)
    rgb[:] = fill
    if stripe:
        rgb[M:M + stripe_h, :] = stripe
    a3, s3 = A[..., None], sh[..., None]
    out_a = a3 + s3 * (1 - a3)
    col = (rgb * a3 + np.array(SHADOW, np.float32) * s3 * (1 - a3)) / np.maximum(out_a, 1e-4)
    arr = np.dstack([np.clip(col, 0, 255), np.clip(out_a * 255, 0, 255)]).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def paste(base, im, x, y):
    """alpha_composite co cat bien."""
    if isinstance(im, np.ndarray):
        im = Image.fromarray(im, "RGBA")
    x, y = int(round(x)), int(round(y))
    if x < 0 or y < 0 or x + im.width > base.width or y + im.height > base.height:
        tmp = Image.new("RGBA", base.size, (0, 0, 0, 0))
        tmp.paste(im, (x, y))
        base.alpha_composite(tmp)
    else:
        base.alpha_composite(im, dest=(x, y))


def runs_img(runs, pad=8):
    """runs: [(text, font, rgb[, box_w])] tren 1 dong, canh chung baseline.
    box_w: o rong co dinh, chu can phai trong o (so dang dem khong xo lech).
    Tra ve (PIL RGBA, baseline_y)."""
    asc = max(r[1].getmetrics()[0] for r in runs)
    desc = max(r[1].getmetrics()[1] for r in runs)
    widths = [r[3] if len(r) > 3 and r[3] else tl(r[0], r[1]) for r in runs]
    im = Image.new("RGBA", (int(math.ceil(sum(widths))) + 2 * pad,
                            asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad
    for r, wd in zip(runs, widths):
        t, f, c = r[0], r[1], r[2]
        if t.strip():
            xx = x + (wd - tl(t, f) if len(r) > 3 and r[3] else 0)
            d.text((xx, pad + asc), t, font=f, fill=tuple(c) + (255,), anchor="ls")
        x += wd
    return im, pad + asc


def text_img(text, f, rgb, pad=8):
    return runs_img([(text, f, rgb)], pad)[0]


def emoji(ch, size):
    if not F_EMOJI or not ch:
        return None
    try:
        f = font(F_EMOJI, size)
        im = Image.new("RGBA", (int(size * 1.6), int(size * 1.6)), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((size * 0.2, size * 0.2), ch, font=f, embedded_color=True)
        bb = im.getbbox()
        if not bb:
            return None
        im = im.crop(bb)
        k = size / max(im.width, im.height)
        return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))),
                         Image.LANCZOS)
    except Exception:
        return None


def icon_badge(ch, d, bg=AMBER_L, alpha=255):
    e = emoji(ch, int(d * 0.58))
    if e is None:
        return None
    c = circle(d, bg, alpha)
    paste(c, e, (d - e.width) / 2, (d - e.height) / 2)
    return c


def arrow_shape(w, h, rgb, ss=4):
    """Mui ten phai (than + dau) khu rang cua."""
    im = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(im)
    th = h * ss * 0.26
    hx = w * ss * 0.52
    cy = h * ss / 2
    d.rounded_rectangle((0, cy - th / 2, hx + th, cy + th / 2), radius=int(th / 2), fill=255)
    d.polygon([(hx - th * 0.2, 0), (w * ss, cy), (hx - th * 0.2, h * ss)], fill=255)
    a = np.asarray(im.resize((w, h), Image.LANCZOS))
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


def tri(d, up, rgb, ss=4):
    im = Image.new("L", (d * ss, d * ss), 0)
    s = d * ss
    pts = [(s * .5, s * .12), (s * .95, s * .88), (s * .05, s * .88)] if up else \
          [(s * .05, s * .12), (s * .95, s * .12), (s * .5, s * .88)]
    ImageDraw.Draw(im).polygon(pts, fill=255)
    a = np.asarray(im.resize((d, d), Image.LANCZOS))
    arr = np.zeros((d, d, 4), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a
    return Image.fromarray(arr, "RGBA")


# ---------------------------------------------------------------- so
NUM_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
ARROWS = "→←↑↓"


def parse_num(s):
    """'1.234,5' -> (1234.5, decimals, grouped)."""
    grouped = "." in s
    ip, _, fp = s.replace(".", "").partition(",")
    return float(ip + ("." + fp if fp else "")), len(fp), grouped


def _yearish(numstr):
    v, dec, g = parse_num(numstr)
    return dec == 0 and not g and 1900 <= v <= 2100


def count_str(tok, frac, start=0.0, dec_min=0):
    """Thay so dau tien trong tok bang gia tri dang dem (start -> gia tri)."""
    m = NUM_RE.search(tok)
    if not m or frac >= 1.0:
        return tok
    v, dec, g = parse_num(m.group(0))
    if _yearish(m.group(0)) or v <= 0:
        return tok
    cur = start + (v - start) * frac
    return tok[:m.start()] + _fmt_num(cur, max(dec, dec_min), g) + tok[m.end():]


def countable(tok):
    m = NUM_RE.search(tok or "")
    return bool(m) and not _yearish(m.group(0)) and parse_num(m.group(0))[0] > 0


def hero_split(s):
    """'GDP +9,95%' -> ('GDP', '+', '9,95%', ''); 'Dầu Brent > 105 USD/thùng'
    -> ('Dầu Brent', '>', '105', 'USD/thùng')."""
    m = NUM_RE.search(s)
    if not m:
        return None
    a, b = m.span()
    while a > 0 and s[a - 1] in "+-−~≈≥≤><":
        a -= 1
    sym = s[a:m.start()]
    pre = s[:a]
    if not sym:
        mm = re.search(r"(?:^|\s)([~≈≥≤><])\s*$", pre)
        if mm:
            sym, pre = mm.group(1), pre[:mm.start(1)]
    while b < len(s) and s[b] in "%đ":
        b += 1
    return pre.strip(), sym.replace("−", "-"), s[m.start():b], s[b:].strip()


def tone(ctx, sym=""):
    """Mau theo chieu: giam -> san ho, tang -> ngoc, con lai vang cam."""
    if sym == "-" or re.search(r"giảm|mất|lỗ|sụt|↓", ctx, re.I):
        return CORAL_D
    if sym == "+" or re.search(r"tăng|↑", ctx, re.I):
        return TEAL_D
    return AMBER_D


def num_runs(sym, num, size, color, box=None):
    """Run cho so to: ki hieu Bahnschrift neu co, khong thi Segoe."""
    out = []
    if sym and box and sym in "+-~><":      # dau dinh lien so dang dem
        return [(sym + num, fnum(size), color, box + tl(sym, fnum(size)))]
    if sym:
        fs = fnum(size) if sym in "+-~><" else fbold(int(size * 0.9))
        out.append((sym, fs, color))
    out.append((num, fnum(size), color, box))
    return out


# ---------------------------------------------------------------- chu giau
def _wcol(w, base, num_col):
    if any(a in w for a in ARROWS) or w in ("=", "≈", "×", "·"):
        return AMBER_D if base == INK else AMBER
    if re.search(r"\d", w):
        return num_col
    return base


def rich_lines(text, f, max_w, max_lines=3):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tl(t, f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines if len(lines) <= max_lines else None


def balance(text, f, max_w, n):
    """Thu hep be rong toi khi so dong doi -> cac dong dai deu nhau."""
    best = rich_lines(text, f, max_w, n)
    if n < 2:
        return best
    w = max_w
    while w > 200:
        w -= 16
        ls = rich_lines(text, f, w, n)
        if not ls or len(ls) != n:
            break
        best = ls
    return best


def fit_rich(text, maker, max_w, hi, lo, max_lines=3, step=4):
    """Co chu lon nhat de text vua max_lines dong."""
    s = hi
    while s >= lo:
        ls = rich_lines(text, maker(s), max_w, max_lines)
        if ls:
            return balance(text, maker(s), max_w, len(ls)), maker(s), s
        s -= step
    f = maker(lo)
    return rich_lines(text, f, max_w, 99)[:max_lines], f, lo


def rich_img(line, f, base=INK, num_col=AMBER_D, fnum_=None):
    runs = []
    for i, w in enumerate(line.split()):
        if i:
            runs.append((" ", f, base))
        col = _wcol(w, base, num_col)
        runs.append((w, fnum_ if (fnum_ and re.search(r"\d", w)) else f, col))
    return runs_img(runs)[0]


def stack(imgs, gap=0, align="left"):
    """Xep doc cac PIL RGBA."""
    imgs = [i for i in imgs if i is not None]
    w = max(i.width for i in imgs)
    h = sum(i.height for i in imgs) + gap * (len(imgs) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = 0
    for i in imgs:
        x = 0 if align == "left" else (w - i.width) / 2 if align == "center" else w - i.width
        paste(out, i, x, y)
        y += i.height + gap
    return out


# ---------------------------------------------------------------- icon
ICONS = [
    (r"vàng|sjc", "🪙"), (r"xăng|dầu|brent|ron9", "⛽"),
    (r"thuê|trọ|nhà ở|căn hộ|bất động sản", "🏠"), (r"thuế", "🧾"),
    (r"lương|thu nhập|giảm trừ", "💵"),
    (r"lãi|vay|ngân hàng|fed|tín dụng|trái phiếu", "🏦"),
    (r"chứng khoán|cổ phiếu|nasdaq|ftse|vn-index|bong bóng", "📊"),
    (r"xuất khẩu|fdi|hàng việt|thương mại|áo giá", "🚢"),
    (r"doanh nghiệp|tập đoàn|microsoft|google", "🏢"),
    (r"cpi|giá|chi tiêu|lạm phát|tiêu dùng|mua", "🛒"),
    (r"gdp|tăng trưởng|kinh tế|imf|usd/người", "📈"),
    (r"tỉnh|huyện|chính quyền|bộ máy|nghị định|nghị quyết", "🏛"),
    (r"mục tiêu|2030|2045", "🎯"), (r"giảm|khủng hoảng|sụt", "📉"),
    (r"tiền|usd|đồng|tỷ|triệu|\dđ", "💰"),
]


def pick_icon(text, default="📊"):
    t = text.lower()
    for pat, ch in ICONS:
        if re.search(pat, t):
            return ch
    return default


# ---------------------------------------------------------------- phan tich
def _norm(text):
    t = " ".join((text or "").replace("\n", " ").split())
    return t.replace("->", "→").replace("=>", "→")


def parse_bars(t):
    if "=" not in t:
        return None
    title, body = "", t
    ci, ei = t.find(":"), t.find("=")
    if 0 < ci < ei:
        title, body = t[:ci].strip(), t[ci + 1:].strip()
    parts = [p.strip() for p in re.split(r"\s*;\s*", body) if p.strip()]
    if not 2 <= len(parts) <= 6:
        return None
    items = []
    for p in parts:
        if p.count("=") != 1:
            return None
        n, v = [x.strip() for x in p.split("=")]
        m = NUM_RE.search(v)
        if not n or not m:
            return None
        items.append((n, v, parse_num(m.group(0))[0]))
    return title, items


def _colon(s):
    m = re.match(r"^(.{2,60}?):\s+(.+)$", s)
    return (m.group(1).strip(), m.group(2).strip()) if m else ("", s)


def classify(text):
    """-> (kind, data). kind: bars, quote, d2, d1, chain, tiles, list, generic."""
    t = _norm(text)
    b = parse_bars(t)
    if b:
        return "bars", {"title": b[0], "items": b[1]}
    parts = [p.strip() for p in re.split(r"\s+·\s+|\s+\|\s+", t) if p.strip()]
    head, subs = parts[0], parts[1:]
    label, main = _colon(head)
    m = re.match(r"^(.*\S)\s+\((.+)\)$", main)
    if m and re.search(r"\d", m.group(1)):
        main, subs = m.group(1), [m.group(2)] + subs
    has_d = bool(re.search(r"\d", t))
    if not has_d and ":" not in t and len(t.split()) <= 14 and not subs:
        return "quote", {"text": t}
    narr = main.count("→")
    if narr == 1 and len(subs) <= 1 and not (subs and _colon(subs[0])[0]):
        A, B = [x.strip() for x in main.split("→")]
        if A and B and re.search(r"\d", A + B) and len(A) <= 32 and len(B) <= 40:
            return "d2", {"label": label, "a": A, "b": B,
                          "cap": subs[0] if subs else ""}
    if not subs and (narr >= 2 or main.count("=") + main.count("≈") >= 1):
        chips = [c.strip() for c in re.split(r"\s*[→=≈]\s*", main)]
        seps = re.findall(r"[→=≈]", main)
        if all(chips) and 2 <= len(chips) <= 7:
            return "chain", {"label": label, "chips": chips, "seps": seps}
    if narr == 0 and len(subs) <= 1 and "=" not in main and "≈" not in main \
            and len(main) <= 48:
        hs = hero_split(main)
        nums = NUM_RE.findall(main)
        if hs and (len(nums) == 1 or (not hs[0] and not hs[1]
                                       and not _yearish(hs[2].rstrip("%đ"))
                                       and not re.match(r"[–\-/]", hs[3] or " "))):
            return "d1", {"label": label, "hero": hs, "cap": subs[0] if subs else "",
                          "ctx": t}
    if len(subs) >= 2 or (subs and any(_colon(s)[0] for s in subs)):
        sub_col = any(_colon(s)[0] for s in subs)
        if label and not sub_col:
            title, items = label, [main] + subs
        elif not label and sub_col and len(subs) >= 2:
            title, items = head, subs
        else:
            title, items = "", [head] + subs
        cells = []
        for it in items:
            if any(a in it for a in "→←"):
                cells = None
                break
            for sep in ("≈", "=", ":"):
                if sep in it:
                    c, v = it.rsplit(sep, 1)
                    cells.append((c.strip(), v.strip()))
                    break
            else:
                hs = hero_split(it)
                if not hs:
                    cells = None
                    break
                cells.append((hs[0], it[len(hs[0]):].strip() if hs[0] else it))
        if cells and 2 <= len(cells) <= 3 and all(len(v) <= 34 for _, v in cells):
            return "tiles", {"title": title, "cells": cells}
        return "list", {"title": title, "items": items}
    return "generic", {"label": label, "main": main, "subs": subs}


# ---------------------------------------------------------------- scene
class Sprite:
    """Phan tu ve len khung. img: PIL RGBA (tinh) hoac fn(t)->(PIL,x,y)
    (dong, toi t_end). Vao bang fade + truot len + phong to nhe."""

    def __init__(self, img=None, x=0, y=0, t0=0.0, dur=0.6, dy=34, s0=1.0,
                 fn=None, t_end=0.0):
        self.img = np.asarray(img) if img is not None else None
        self.x, self.y = x, y
        self.t0, self.dur, self.dy, self.s0 = t0, dur, dy, s0
        self.fn, self.t_end = fn, t_end
        self.oy = _OY

    @property
    def end(self):
        return max(self.t0 + self.dur, self.t_end)

    def state(self, t):
        p = (t - self.t0) / self.dur
        if p <= 0:
            return None
        if self.fn:
            im, x, y = self.fn(min(t, self.t_end) if self.t_end else t)
            img = np.asarray(im)
        else:
            img, x, y = self.img, self.x, self.y
        alpha = _ease(p * 1.4)
        if p < 1:
            if self.s0 != 1.0:
                s = self.s0 + (1 - self.s0) * _back(p)
                h, w = img.shape[:2]
                nw, nh = max(1, int(w * s)), max(1, int(h * s))
                img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
                x, y = x + (w - nw) / 2, y + (h - nh) / 2
            y = y + (1 - _ease(p)) * self.dy
        return img, x, y + self.oy, alpha


class Scene:
    def __init__(self):
        self.items, self.live, self._cache = [], [], None

    def add(self, sp):
        self.items.append(sp)
        return sp

    @property
    def t_static(self):
        return max([s.end for s in self.items] + [0]) + 0.02

    def _bake(self):
        C = np.zeros((H, W, 3), np.float32)
        A = np.zeros((H, W, 1), np.float32)
        for sp in self.items:
            st = sp.state(self.t_static + 10)
            if not st:
                continue
            img, x, y, _ = st
            h, w = img.shape[:2]
            x, y = int(round(x)), int(round(y))
            x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
            if x1 <= x0 or y1 <= y0:
                continue
            sub = img[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
            a = sub[..., 3:4] / 255.0
            C[y0:y1, x0:x1] = C[y0:y1, x0:x1] * (1 - a) + sub[..., :3] * a
            A[y0:y1, x0:x1] = A[y0:y1, x0:x1] * (1 - a) + a
        pm = np.clip(C + 0.5, 0, 255).astype(np.uint8)
        inv = np.clip((1 - A) * 255 + 0.5, 0, 255).astype(np.uint8)
        return pm, cv2.merge([inv[..., 0]] * 3)

    def draw(self, frame, t):
        if t >= self.t_static:
            if self._cache is None:
                self._cache = self._bake()
            pm, inv = self._cache
            frame[:] = cv2.add(cv2.multiply(frame, inv, scale=1 / 255.0), pm)
        else:
            for sp in self.items:
                st = sp.state(t)
                if st:
                    _blend(frame, st[0], st[1], st[2], st[3])
        for fn in self.live:
            fn(frame, t)


def float_live(img, x, y, t0, amp=7.0, period=3.4, phase=0.0, dur=0.7, s0=0.6):
    """Sprite nho troi len xuong (subpixel) suot card — chuyen dong nhe."""
    arr = np.asarray(img)
    y = y + _OY
    pad = int(amp) + 4
    arr = cv2.copyMakeBorder(arr, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    h, w = arr.shape[:2]

    def fn(frame, t):
        p = (t - t0) / dur
        if p <= 0:
            return
        s = s0 + (1 - s0) * _back(p) if p < 1 else 1.0
        oy = amp * math.sin(2 * math.pi * (t - t0) / period + phase)
        m = np.float32([[s, 0, (1 - s) * w / 2], [0, s, (1 - s) * h / 2 + oy]])
        im = cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        _blend(frame, im, x - pad, y - pad, _ease(p * 1.5))
    return fn


# ---------------------------------------------------------------- nen
class BgInfo:
    """Navy diu: gradient + 3 vet mau troi cham (ngoc / vang / lam) o 1/8
    do phan giai, hat nhieu tinh chong soc mau, luoi cham troi cheo, vong
    tron mo troi, vignette nhe."""

    def __init__(self, seed=0):
        rng = np.random.default_rng(seed + 7)
        self.sw, self.sh = W // 8, H // 8
        yy, xx = np.mgrid[0:self.sh, 0:self.sw].astype(np.float32)
        self.xx, self.yy = xx / self.sw, yy / self.sh
        g = np.clip(0.55 * self.xx + 0.45 * self.yy, 0, 1)[..., None]
        self.base = NAVY0 + (NAVY1 - NAVY0) * g
        self.blobs = [(np.array(c, np.float32), a, rng.uniform(0, 6.28), rng.uniform(.6, 1.2))
                      for c, a in (((22, 92, 98), .55), ((92, 64, 30), .32),
                                   ((40, 62, 128), .50))]
        self.grain = rng.normal(0, 1.4, (H, W, 1)).astype(np.float32)
        vy, vx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((vx - W / 2) / (W / 2)) ** 2 + ((vy - H / 2) / (H / 2)) ** 2)
        v = np.clip(1.06 - 0.30 * r ** 1.8, 0.6, 1.0) * 255
        self.vig = cv2.merge([v.astype(np.uint8)] * 3)
        self.cell = 48
        gw, gh = W + 2 * self.cell, H + 2 * self.cell
        dots = np.zeros((gh * 4 // 4, gw), np.uint8)
        for yy_ in range(self.cell // 2, gh, self.cell):
            for xx_ in range(self.cell // 2, gw, self.cell):
                cv2.circle(dots, (xx_ * 16, yy_ * 16), int(1.7 * 16), 255, -1,
                           cv2.LINE_AA, shift=4)
        k = 0.085
        self.dots = cv2.merge([(dots * (k * c / 255.0)).astype(np.uint8)
                               for c in ON_NAVY])
        n = 5
        self.rings = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(90, 330),
                       rng.uniform(-9, 9), rng.uniform(-6, 6), rng.uniform(.035, .07),
                       int(rng.integers(0, 2))) for _ in range(n)]
        self.ph = rng.uniform(0, 6.28)

    def frame(self, t):
        small = self.base.copy()
        for k, (col, amp, ph, sp) in enumerate(self.blobs):
            cx = 0.5 + 0.36 * math.sin(0.10 * sp * t + ph + k * 2.1)
            cy = 0.5 + 0.30 * math.cos(0.08 * sp * t + ph * 1.3 + k)
            d2 = ((self.xx - cx) * 1.78) ** 2 + (self.yy - cy) ** 2
            small += col * (amp * np.exp(-d2 / 0.12))[..., None]
        img = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
        img = np.clip(img + self.grain, 0, 255).astype(np.uint8)
        c = self.cell
        ox, oy = (t * 7.0) % c, (t * 4.0) % c
        m = np.float32([[1, 0, -c + ox], [0, 1, -c + oy]])
        img = cv2.add(img, cv2.warpAffine(self.dots, m, (W, H), flags=cv2.INTER_LINEAR))
        lay = np.zeros((H, W, 3), np.uint8)
        for (x, y, r, vx, vy, a, filled) in self.rings:
            px = (x + vx * t) % (W + 600) - 300
            py = (y + vy * t) % (H + 600) - 300
            col = tuple(int(255 * a * cc / 255) for cc in ON_NAVY)
            if filled:
                cv2.circle(lay, (int(px * 16), int(py * 16)), int(r * 16),
                           tuple(int(v * 0.35) for v in col), -1, cv2.LINE_AA, shift=4)
            cv2.circle(lay, (int(px * 16), int(py * 16)), int(r * 16), col, 2,
                       cv2.LINE_AA, shift=4)
        img = cv2.add(img, lay)
        return cv2.multiply(img, self.vig, scale=1 / 255.0)


# ---------------------------------------------------------------- bo cuc chung
Y_TOP, Y_BOT = 70, 770          # vung an toan (duoi la phu de)


def title_sprite(text, ch=None, y=None, t0=0.05, size=58):
    """Tieu de tren nen navy: icon + chu kem + gach vang."""
    f, s = fsemi(size), size
    while tl(text, f) > 1500 and s > 38:
        s -= 4
        f = fsemi(s)
    lines = rich_lines(text, f, 1500, 2) or [text]
    imgs = [rich_img(ln, f, ON_NAVY, AMBER) for ln in lines]
    txt = stack(imgs, -6, "center")
    ic = icon_badge(ch, int(s * 1.45), bg=(255, 255, 255), alpha=34) if ch else None
    gap = 22
    w = txt.width + ((ic.width + gap) if ic else 0)
    hh = max(txt.height, ic.height if ic else 0)
    im = Image.new("RGBA", (int(w), int(hh + 26)), (0, 0, 0, 0))
    x = 0
    if ic:
        paste(im, ic, 0, (hh - ic.height) / 2)
        x = ic.width + gap
    paste(im, txt, x, (hh - txt.height) / 2)
    paste(im, solid(84, 7, AMBER, r=3), x + (txt.width - 84) / 2, hh + 12)
    return im


def src_sprite(src, t0=0.7):
    txt = "Nguồn: " + src.strip()
    f = freg(27)
    while tl(txt, f) > W * 0.55 and len(txt) > 20:
        txt = txt[:-2].rstrip() + "…" if not txt.endswith("…") else txt[:-3].rstrip() + "…"
    ti = text_img(txt, f, (206, 214, 228), pad=4)
    im = solid(ti.width + 50, ti.height + 18, (9, 16, 32), r=(ti.height + 18) / 2, alpha=190)
    paste(im, circle(10, AMBER), 18, (im.height - 10) / 2)
    paste(im, ti, 36, 9)
    return Sprite(im, 44, H - im.height - 38, t0=t0, dur=0.6, dy=12)


def center_block(h):
    return max(Y_TOP, int((Y_TOP + Y_BOT - h) / 2))


# ---------------------------------------------------------------- D1
def hero_runs(pre, sym, num, post, color, size, cur=None, box=None):
    small = int(size * 0.34)
    runs = []
    if pre:
        runs.append((pre + " ", fsemi(small), INK))
    runs += num_runs(sym, cur or num, size, color, box)
    if post:
        sep = "" if post.startswith("/") else " "
        runs.append((sep + post, fsemi(small), INK2))
    return runs


def build_d1(sc, d):
    label, (pre, sym, num, post), cap = d["label"], d["hero"], d["cap"]
    if not label and pre:
        label, pre = pre, ""
    color = tone(d["ctx"], sym)
    ch = pick_icon(d["ctx"])
    max_w = 1180
    size = 230
    while size > 120:
        im, _ = runs_img(hero_runs(pre, sym, num, post, color, size))
        if im.width <= max_w:
            break
        size -= 8
    post_below = False
    im, _ = runs_img(hero_runs(pre, sym, num, post, color, size))
    if im.width > max_w:
        post_below = True
    hr_post = "" if post_below else post
    final_hero, _ = runs_img(hero_runs(pre, sym, num, hr_post, color, size))
    num_box = tl(num, fnum(size))
    # cot chu ben trai
    lab = None
    if label:
        lf = fsemi(54)
        ls = rich_lines(label, lf, max_w - 120, 2) or [label]
        lab = stack([rich_img(x, lf, INK2, INK2) for x in ls], -8)
    blocks_h = []
    under = []
    if post_below:
        f2 = fsemi(52)
        for ln in (rich_lines(post, f2, max_w, 2) or [post]):
            under.append(rich_img(ln, f2, INK2, INK2))
    if cap:
        f3 = freg(42)
        for ln in (rich_lines(cap, f3, max_w, 2) or [cap]):
            under.append(rich_img(ln, f3, INK2, AMBER_D))
    ic = emoji(ch, 190)
    pad_x, pad_y = 84, 60
    col_w = max([final_hero.width] + [u.width for u in under] + [lab.width if lab else 0])
    pw = col_w + 2 * pad_x + (250 if ic else 0)
    pw = max(pw, 1060)
    lab_h = (lab.height + 34) if lab else 0
    hero_top_trim = int(size * 0.10)        # bahnschrift co khoang tren rong
    ph = pad_y + lab_h + final_hero.height - hero_top_trim + \
        sum(u.height + 6 for u in under) + (14 if under else 0) + pad_y - 10
    px = (W - pw) / 2
    py = center_block(ph)
    P = panel(pw, ph, stripe=None)
    paste(P, solid(10, ph - 2 * pad_y + 20, color if color != AMBER_D else AMBER, r=5),
          M + 38, M + pad_y - 10)
    y = M + pad_y
    if lab:
        y += lab.height + 34
        paste(P, solid(min(lab.width, 220), 4, LINE, r=2), M + pad_x, y - 22)
    hero_y = py + (y - M) - hero_top_trim
    y += final_hero.height - hero_top_trim + 14
    under_imgs = []
    for u in under:
        under_imgs.append((u, px + pad_x, py + (y - M)))
        y += u.height + 6
    sc.add(Sprite(P, px - M, py - M, t0=0.0, dur=0.6, dy=40, s0=0.94))
    if lab:
        sc.add(Sprite(lab, px + pad_x, py + pad_y, t0=0.18, dur=0.5, dy=18))
    cnt = countable(num)
    T0, TC = 0.3, 1.05

    def hero_fn(t):
        frac = _ease((t - T0) / TC) if cnt else 1.0
        cur = count_str(num, frac) if frac < 1 else num
        im, _ = runs_img(hero_runs(pre, sym, num, hr_post, color, size, cur=cur,
                                   box=num_box))
        return im, px + pad_x - 8, hero_y
    sc.add(Sprite(None, 0, 0, t0=T0, dur=0.5, dy=26, fn=hero_fn, t_end=T0 + TC))
    for i, (u, ux, uy) in enumerate(under_imgs):
        sc.add(Sprite(u, ux, uy, t0=0.55 + 0.12 * i, dur=0.5, dy=16))
    if ic:
        badge = circle(250, AMBER_L)
        paste(badge, ic, (250 - ic.width) / 2, (250 - ic.height) / 2)
        sc.live.append(float_live(badge, px + pw - pad_x - 230, py + (ph - 250) / 2,
                                  t0=0.35, amp=8))


# ---------------------------------------------------------------- D2
def _side(s):
    """'2,5 triệu' -> (sym, num, unit) ; khong co so -> (None, None, s)."""
    hs = hero_split(s)
    if not hs:
        return None
    pre, sym, num, post = hs
    return pre, sym, num, post


def build_d2(sc, d):
    label, A, B, cap = d["label"], d["a"], d["b"], d["cap"]
    sa, sb = _side(A), _side(B)
    va = parse_num(NUM_RE.search(A).group(0))[0] if sa else None
    vb = parse_num(NUM_RE.search(B).group(0))[0] if sb else None
    if sb and sb[1] == "-":
        vb = -vb
    if sa and sa[1] == "-":
        va = -va
    up = None
    if va is not None and vb is not None and va != vb:
        up = vb > va
    col = TEAL_D if up else CORAL_D if up is False else AMBER_D
    col_l = TEAL if up else CORAL if up is False else AMBER
    # % thay doi
    badge_txt = None
    if va is not None and vb is not None and va > 0 and up is not None:
        if "%" in A and "%" in B:
            dv = abs(vb - va)
            badge_txt = _fmt_num(dv, 0 if dv >= 10 or dv == int(dv) else 1, False) + " điểm %"
        elif ("%" in A) == ("%" in B):
            pct = abs(vb - va) / va * 100
            badge_txt = _fmt_num(pct, 0 if pct >= 10 else 1, False) + "%"
    ch = pick_icon(label + " " + A + " " + B)
    top = Y_TOP + 10
    if label:
        T = title_sprite(label, ch)
        sc.add(Sprite(T, (W - T.width) / 2, top, t0=0.0, dur=0.5, dy=20))
        top += T.height + 44
    pw, ph, gap = 640, 330, 190
    if cap:
        ph = 300
    x1 = (W - 2 * pw - gap) / 2
    x2 = x1 + pw + gap
    avail = Y_BOT - top - (80 if cap else 0)
    py = top + max(0, (avail - ph) / 2) if not label else top

    def side_img(s, sp, numcol, unitcol, cur=None, box=None):
        if sp is None:
            ls, f, _ = fit_rich(s, fbold, pw - 90, 72, 44, 3)
            return stack([rich_img(x, f, numcol, numcol) for x in ls], -6, "center")
        pre, sym, num, post = sp
        size = 150
        while size > 70:
            w = sum(tl(r[0], r[1]) for r in num_runs(sym, num, size, numcol))
            if w <= pw - 90:
                break
            size -= 6
        nim, _ = runs_img(num_runs(sym, cur or num, size, numcol, box))
        extra = " ".join(x for x in (pre, post) if x)
        if extra:
            ls, f, _ = fit_rich(extra, fsemi, pw - 90, 50, 32, 2)
            u = stack([rich_img(x, f, unitcol, unitcol) for x in ls], -6, "center")
            return stack([nim, u], -int(size * 0.12), "center")
        return nim

    def head(txt, c):
        f = fbold(30)
        spaced = " ".join(txt)
        return text_img(spaced, f, c, pad=2)

    PL = panel(pw, ph, fill=CREAM_D)
    paste(PL, head("TRƯỚC", INK2), M + 44, M + 34)
    PR = panel(pw, ph, fill=CREAM, stripe=col_l, stripe_h=12)
    paste(PR, head("SAU", col), M + 44, M + 40)
    body_top = 88
    L = side_img(A, sa, INK2, INK2)
    lx = x1 + (pw - L.width) / 2
    ly = py + body_top + (ph - body_top - 28 - L.height) / 2
    sc.add(Sprite(PL, x1 - M, py - M, t0=0.05, dur=0.6, dy=36, s0=0.95))
    sc.add(Sprite(L, lx, ly, t0=0.2, dur=0.5, dy=18))
    sc.add(Sprite(PR, x2 - M, py - M, t0=0.4, dur=0.6, dy=36, s0=0.95))
    R_final = side_img(B, sb, col, INK2)
    rx = x2 + (pw - R_final.width) / 2
    ry = py + body_top + (ph - body_top - 28 - R_final.height) / 2
    T0, TC = 0.6, 1.0
    can_count = sa is not None and sb is not None and countable(B)
    st = abs(va) if can_count else 0.0
    dec_a = parse_num(NUM_RE.search(A).group(0))[1] if sa else 0

    def r_fn(t):
        frac = _ease((t - T0) / TC) if can_count else 1.0
        if frac >= 1:
            return R_final, rx, ry
        size_box = None
        cur = count_str(sb[2], frac, start=st, dec_min=dec_a)
        im = side_img(B, sb, col, INK2, cur=cur, box=size_box)
        return im, x2 + (pw - im.width) / 2, ry
    sc.add(Sprite(None, 0, 0, t0=T0, dur=0.5, dy=18, fn=r_fn, t_end=T0 + TC))
    # mui ten giua (song: dich nhe qua lai)
    d_ = 128
    arr = circle(d_, AMBER)
    paste(arr, arrow_shape(70, 50, INK), (d_ - 70) / 2 + 3, (d_ - 50) / 2)
    ax, ay = x1 + pw + (gap - d_) / 2, py + (ph - d_) / 2 + 10 + _OY
    a_np = np.asarray(arr)
    pad = 16
    a_np = cv2.copyMakeBorder(a_np, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)

    def arrow_live(frame, t, t0=0.35):
        p = (t - t0) / 0.6
        if p <= 0:
            return
        s = 0.3 + 0.7 * _back(p) if p < 1 else 1.0
        ox = (1 - _ease(p)) * -50 + 6 * math.sin(2 * math.pi * (t - t0) / 1.8)
        h, w = a_np.shape[:2]
        m = np.float32([[s, 0, (1 - s) * w / 2 + ox], [0, s, (1 - s) * h / 2]])
        im = cv2.warpAffine(a_np, m, (w, h), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        _blend(frame, im, ax - pad, ay - pad, _ease(p * 1.5))
    sc.live.append(arrow_live)
    if badge_txt:
        f = fbold(40)
        ti = text_img(badge_txt, f, (255, 255, 255), pad=2)
        bh = ti.height + 22
        tw = 30
        b = solid(ti.width + tw + 64, bh, col_l, r=bh / 2)
        paste(b, tri(tw, up, (255, 255, 255)), 26, (bh - tw) / 2)
        paste(b, ti, 26 + tw + 12, 11)
        sh = panel(b.width, b.height, fill=col_l, r=bh / 2, shadow=0.45, blur=10, dy=6)
        paste(sh, b, M, M)
        sc.add(Sprite(sh, x2 + pw - b.width + 26 - M, py - bh / 2 - M,
                      t0=T0 + TC - 0.15, dur=0.45, dy=0, s0=0.4))
    if cap:
        f = fsemi(44)
        ls = rich_lines(cap, f, 1400, 2) or [cap]
        ci = stack([rich_img(x, f, ON_NAVY2, AMBER) for x in ls], -6, "center")
        sc.add(Sprite(ci, (W - ci.width) / 2, py + ph + 40, t0=1.0, dur=0.5, dy=14))


# ---------------------------------------------------------------- D3
def build_bars(sc, d):
    title, items = d["title"], d["items"][:6]
    n = len(items)
    ch = pick_icon(title + " " + " ".join(i[0] for i in items))
    top = Y_TOP + 10
    if title:
        T = title_sprite(title, ch)
        sc.add(Sprite(T, (W - T.width) / 2, top, t0=0.0, dur=0.5, dy=20))
        top += T.height + 40
    avail = Y_BOT - top
    row_h = min(112, int((avail - 100) / n))
    pw = 1520
    pad_x, pad_y = 64, 46
    ph = n * row_h + 2 * pad_y
    nf_size = min(48, int(row_h * 0.46))
    nf = fsemi(nf_size)
    names = []
    for nm, _, _ in items:
        s = nf_size
        while tl(nm, fsemi(s)) > 470 and s > 28:
            s -= 2
        names.append(text_img(nm, fsemi(s), INK, pad=4))
    name_w = max(i.width for i in names)
    vsz = min(60, int(row_h * 0.56))

    def val_runs(v, cur=None):
        hs = hero_split(v)
        pre, sym, num, post = hs
        runs = num_runs(sym, cur or num, vsz, INK, tl(num, fnum(vsz)) if cur else None)
        if post:
            runs.append(((" " if not post.startswith("/") else "") + post,
                         fsemi(int(vsz * 0.6)), INK2))
        return runs
    val_w = max(runs_img(val_runs(v))[0].width for _, v, _ in items)
    track_x = pad_x + name_w + 36
    track_w = pw - pad_x - track_x - val_w - 28
    vmax = max(abs(v) for *_, v in items) or 1
    py = top + max(0, (avail - ph) / 2) if not title else top
    px = (W - pw) / 2
    P = panel(pw, ph)
    bh = int(row_h * 0.46)
    imax = max(range(n), key=lambda i: items[i][2])
    for i in range(n):
        cy = pad_y + i * row_h + row_h / 2
        paste(P, names[i], M + pad_x + name_w - names[i].width, M + cy - names[i].height / 2)
        paste(P, solid(track_w, bh, TRACK, r=bh / 2), M + track_x, M + cy - bh / 2)
        if i:
            paste(P, solid(pw - 2 * pad_x, 2, LINE), M + pad_x, M + pad_y + i * row_h)
    sc.add(Sprite(P, px - M, py - M, t0=0.08, dur=0.6, dy=40, s0=0.95))
    for i, (nm, v, val) in enumerate(items):
        cy = py + pad_y + i * row_h + row_h / 2
        full = max(bh, track_w * abs(val) / vmax)
        col = AMBER if i == imax else TEAL
        T0, TC = 0.35 + 0.1 * i, 1.0

        def bar_fn(t, full=full, col=col, cy=cy, T0=T0, TC=TC, v=v):
            p = _ease((t - T0) / TC)
            w = max(bh, full * p)
            bar = solid(w, bh, col, r=bh / 2)
            frac = p
            vi, base = runs_img(val_runs(v, count_str(v_num(v), frac) if frac < 1 else None))
            im = Image.new("RGBA", (int(w + 22 + vi.width), max(bh, vi.height)), (0, 0, 0, 0))
            paste(im, bar, 0, (im.height - bh) / 2)
            paste(im, vi, w + 14, (im.height - vi.height) / 2 + 2)
            return im, px + track_x, cy - im.height / 2
        sc.add(Sprite(None, 0, 0, t0=T0, dur=0.3, dy=0, fn=bar_fn, t_end=T0 + TC))


def v_num(v):
    hs = hero_split(v)
    return hs[2] if hs else v


# ---------------------------------------------------------------- D4
def build_quote(sc, d):
    text = d["text"].strip().strip('"“”')
    one = next((z for z in range(124, 83, -4) if tl(text, fbold(z)) <= 1320), None)
    if one:
        ls, f, s = [text], fbold(one), one
    else:
        ls, f, s = fit_rich(text, fbold, 1300, 110, 60, 3)
    imgs = [text_img(x, f, INK, pad=6) for x in ls]
    lh = int(s * 1.28)
    tw = max(i.width for i in imgs)
    pw = max(1000, tw + 340)
    ph = len(ls) * lh + 170
    px, py = (W - pw) / 2, center_block(ph)
    P = panel(pw, ph)
    sc.add(Sprite(P, px - M, py - M, t0=0.0, dur=0.6, dy=40, s0=0.94))
    qf = font(F_QUOTE, 300)
    q = text_img("“", qf, AMBER, pad=0)
    q = q.crop(q.getbbox())
    sc.live.append(float_live(q, px + 50, py - q.height * 0.45, t0=0.15, amp=5,
                              period=4.0))
    y0 = py + 85
    # gach vang highlight sau 2-3 tu cuoi cua dong cuoi
    last = ls[-1]
    words = last.split()
    k = min(len(words), 3 if len(words) >= 5 else 2)
    tail = " ".join(words[-k:])
    lw = imgs[-1].width
    tx = (W - lw) / 2 + 6 + tl(last, f) - tl(tail, f)
    hw = tl(tail, f) + 16
    hy = y0 + (len(ls) - 1) * lh + int(s * 0.62)
    hhh = int(s * 0.42)
    HT0, HTC = 0.75, 0.6

    def hl_fn(t):
        p = _ease((t - HT0) / HTC)
        return solid(max(hhh, hw * p), hhh, (250, 212, 146), r=8), tx - 8, hy
    sc.add(Sprite(None, 0, 0, t0=HT0, dur=0.15, dy=0, fn=hl_fn, t_end=HT0 + HTC))
    for i, im in enumerate(imgs):
        sc.add(Sprite(im, (W - im.width) / 2, y0 + i * lh, t0=0.2 + 0.14 * i,
                      dur=0.55, dy=24))
    q2 = text_img("”", qf, (240, 226, 200), pad=0)
    q2 = q2.crop(q2.getbbox())
    q2 = q2.resize((q2.width * 2 // 3, q2.height * 2 // 3), Image.LANCZOS)
    sc.add(Sprite(q2, px + pw - q2.width - 46, py + ph - q2.height - 30, t0=0.5,
                  dur=0.6, dy=0, s0=0.5))


# ---------------------------------------------------------------- chain
def build_chain(sc, d):
    label, chips, seps = d["label"], d["chips"], d["seps"]
    ch = pick_icon(label + " " + " ".join(chips))
    top = Y_TOP + 10
    if label:
        T = title_sprite(label, ch)
        sc.add(Sprite(T, (W - T.width) / 2, top, t0=0.0, dur=0.5, dy=20))
        top += T.height + 50
    sep_d, gap = 64, 18
    max_row = 1720

    def sep_img(sep):
        s_im = circle(sep_d, AMBER)
        if sep == "→":
            paste(s_im, arrow_shape(34, 26, INK), (sep_d - 34) / 2 + 2, (sep_d - 26) / 2)
        else:
            gi = text_img(sep, fbold(46), INK, pad=0)
            gi = gi.crop(gi.getbbox())
            paste(s_im, gi, (sep_d - gi.width) / 2, (sep_d - gi.height) / 2)
        return s_im

    def chip_imgs(size):
        out = []
        for i, c in enumerate(chips):
            last = i == len(chips) - 1
            f = fbold(size)
            ls = rich_lines(c, f, 760, 2) or [c]
            t = stack([rich_img(x, f, INK, INK) for x in ls], -int(size * .25), "center")
            cw, chh = t.width + 2 * int(size * .62), t.height + int(size * .55)
            fill = AMBER if last else CREAM
            P = panel(cw, chh, fill=fill, r=min(28, chh / 2), shadow=0.5, blur=14, dy=10)
            paste(P, t, M + (cw - t.width) / 2, M + (chh - t.height) / 2)
            out.append((P, cw, chh))
        return out

    def rows_for(cs, allow2=True):
        total = sum(c[1] for c in cs) + (len(cs) - 1) * (sep_d + 2 * gap)
        if total <= max_row:
            return [list(range(len(cs)))]
        if not allow2:
            return None
        best = None
        for k in range(1, len(cs)):
            a = sum(c[1] for c in cs[:k]) + (k - 1) * (sep_d + 2 * gap)
            b = sum(c[1] for c in cs[k:]) + (len(cs) - k) * (sep_d + 2 * gap)
            if max(a, b) <= max_row and (best is None or max(a, b) < best[0]):
                best = (max(a, b), k)
        return [list(range(best[1])), list(range(best[1], len(cs)))] if best else None

    size0 = 76 if len(chips) <= 3 else 64
    rows = None
    for size in range(size0, 47, -4):          # uu tien 1 dong
        cs = chip_imgs(size)
        rows = rows_for(cs, allow2=False)
        if rows:
            break
    if not rows:
        for size in range(size0, 33, -4):
            cs = chip_imgs(size)
            rows = rows_for(cs)
            if rows:
                break
    if not rows:
        rows = [list(range(len(cs)))]
    row_h = max(c[2] for c in cs)
    vgap = 70
    total_h = len(rows) * row_h + (len(rows) - 1) * vgap
    y = top + max(0, (Y_BOT - top - total_h) / 2 - 10)
    k = 0
    for r, idxs in enumerate(rows):
        lead = r > 0
        rw = sum(cs[i][1] for i in idxs) + (len(idxs) - 1 + lead) * (sep_d + 2 * gap)
        x = (W - rw) / 2
        for j, i in enumerate(idxs):
            if j == 0 and lead:
                s_im = sep_img(seps[i - 1] if i - 1 < len(seps) else "→")
                sc.add(Sprite(s_im, x, y + (row_h - sep_d) / 2, t0=0.08 + 0.16 * k,
                              dur=0.4, dy=0, s0=0.3))
                x += sep_d + 2 * gap
            P, cw, chh = cs[i]
            cy = y + (row_h - chh) / 2
            t0 = 0.08 + 0.16 * k
            sc.add(Sprite(P, x - M, cy - M, t0=t0, dur=0.5, dy=26, s0=0.9))
            x += cw
            if i < len(chips) - 1:
                sx = x + gap if j < len(idxs) - 1 else None
                s_im = sep_img(seps[i] if i < len(seps) else "→")
                if sx is not None:
                    sc.add(Sprite(s_im, sx, y + (row_h - sep_d) / 2, t0=t0 + 0.1,
                                  dur=0.4, dy=0, s0=0.3))
                    x = sx + sep_d + gap
            k += 1
        y += row_h + vgap


# ---------------------------------------------------------------- tiles
def build_tiles(sc, d):
    title, cells = d["title"], d["cells"]
    n = len(cells)
    ch = pick_icon(title + " " + " ".join(c + " " + v for c, v in cells))
    top = Y_TOP + 10
    if title:
        T = title_sprite(title, ch)
        sc.add(Sprite(T, (W - T.width) / 2, top, t0=0.0, dur=0.5, dy=20))
        top += T.height + 48
    gap = 48
    tw = min(560, (1680 - gap * (n - 1)) / n)
    th = 330
    accents = [AMBER, TEAL, SKY]
    x0 = (W - (n * tw + (n - 1) * gap)) / 2
    y = top + max(0, (Y_BOT - top - th) / 2 - 10)
    for i, (cap, val) in enumerate(cells):
        acc = accents[i % 3]
        P = panel(tw, th, stripe=acc, stripe_h=12)
        cap_im = None
        if cap:
            ls, f, _ = fit_rich(cap, fsemi, tw - 80, 42, 30, 2)
            cap_im = stack([rich_img(x, f, INK2, INK2) for x in ls], -6)
            paste(P, cap_im, M + 40, M + 44)
        hs = hero_split(val) if not any(a in val for a in ARROWS) else None
        x = x0 + i * (tw + gap)
        sc.add(Sprite(P, x - M, y - M, t0=0.06 + 0.14 * i, dur=0.6, dy=36, s0=0.95))
        cap_h = (cap_im.height + 10) if cap_im else 0
        col = tone(cap + " " + val, hs[1] if hs else "")
        col = INK if col == AMBER_D else col
        if hs:
            pre, sym, num, post = hs
            size = 120
            while size > 56:
                w = sum(tl(r[0], r[1]) for r in num_runs(sym, num, size, col))
                if w <= tw - 80:
                    break
                size -= 6
            unit = " ".join(z for z in (pre, post) if z)
            uim = None
            if unit:
                ls, f, _ = fit_rich(unit, fsemi, tw - 80, 44, 28, 2)
                uim = stack([rich_img(z, f, INK2, INK2) for z in ls], -6)
            nb = tl(num, fnum(size))
            T0, TC = 0.35 + 0.14 * i, 1.0
            body_y = y + 44 + cap_h
            free = th - 44 - cap_h - 40
            nh = runs_img(num_runs(sym, num, size, col))[0].height
            blk = nh - int(size * .12) + ((uim.height) if uim else 0)
            ny = body_y + max(0, (free - blk) / 2)

            def fn(t, sym=sym, num=num, size=size, col=col, nb=nb, x=x, ny=ny, T0=T0, TC=TC):
                frac = _ease((t - T0) / TC) if countable(num) else 1.0
                im, _ = runs_img(num_runs(sym, count_str(num, frac), size, col, nb))
                return im, x + 32, ny
            sc.add(Sprite(None, 0, 0, t0=T0, dur=0.5, dy=20, fn=fn, t_end=T0 + TC))
            if uim:
                sc.add(Sprite(uim, x + 40, ny + nh - int(size * .12), t0=T0 + 0.2,
                              dur=0.5, dy=14))
        else:
            ls, f, _ = fit_rich(val, fbold, tw - 80, 64, 36, 3)
            vim = stack([rich_img(z, f, INK, AMBER_D) for z in ls], -6)
            sc.add(Sprite(vim, x + 40, y + 44 + cap_h + 20, t0=0.35 + 0.14 * i,
                          dur=0.5, dy=18))


# ---------------------------------------------------------------- list
def build_list(sc, d):
    title, items = d["title"], d["items"][:5]
    ch = pick_icon(title + " " + " ".join(items))
    top = Y_TOP + 10
    if title:
        T = title_sprite(title, ch)
        sc.add(Sprite(T, (W - T.width) / 2, top, t0=0.0, dur=0.5, dy=20))
        top += T.height + 44
    n = len(items)
    pw, pad_x, pad_y = 1500, 60, 40
    row_h = min(120, int((Y_BOT - top - 2 * pad_y - 20) / n))
    size = min(52, int(row_h * 0.44))
    tx = pad_x + 90
    rows = []
    for it in items:
        c, v = _colon(it)
        s = size
        while True:
            fc, fv = fsemi(s), fbold(s)
            runs = []
            if c:
                runs.append((c + "  ", fc, INK2))
            for j, w in enumerate(v.split()):
                if j:
                    runs.append((" ", fv, INK))
                runs.append((w, fv, _wcol(w, INK, AMBER_D)))
            im, _ = runs_img(runs)
            if im.width <= pw - tx - pad_x or s <= 28:
                break
            s -= 2
        rows.append(im)
    ph = n * row_h + 2 * pad_y
    px = (W - pw) / 2
    py = top + max(0, (Y_BOT - top - ph) / 2 - 10) if not title else top
    P = panel(pw, ph)
    for i in range(1, n):
        paste(P, solid(pw - 2 * pad_x, 2, LINE), M + pad_x, M + pad_y + i * row_h)
    sc.add(Sprite(P, px - M, py - M, t0=0.05, dur=0.6, dy=40, s0=0.95))
    acc = [AMBER, TEAL, SKY, CORAL, AMBER]
    for i, im in enumerate(rows):
        cy = py + pad_y + i * row_h + row_h / 2
        b = circle(56, acc[i])
        num = text_img(str(i + 1), fbold(30), (255, 255, 255), pad=0)
        num = num.crop(num.getbbox())
        paste(b, num, (56 - num.width) / 2, (56 - num.height) / 2)
        t0 = 0.3 + 0.16 * i
        sc.add(Sprite(b, px + pad_x, cy - 28, t0=t0, dur=0.4, dy=0, s0=0.3))
        sc.add(Sprite(im, px + tx, cy - im.height / 2, t0=t0 + 0.06, dur=0.5, dy=16))


# ---------------------------------------------------------------- generic
def build_generic(sc, d):
    label, main, subs = d["label"], d["main"], d["subs"][:2]
    ch = pick_icon(label + " " + main)
    max_w = 1300
    ls, f, s = fit_rich(main, fbold, max_w, 96, 52, 3)
    mains = [rich_img(x, f, INK, AMBER_D) for x in ls]
    lab = None
    if label:
        lf = fsemi(48)
        lab = stack([rich_img(x, lf, INK2, INK2)
                     for x in (rich_lines(label, lf, max_w - 120, 2) or [label])], -6)
    subs_im = []
    for sub in subs:
        sf = freg(42)
        for x in (rich_lines(sub, sf, max_w, 2) or [sub]):
            subs_im.append(rich_img(x, sf, INK2, AMBER_D))
    lh = int(s * 1.22)
    pad_x, pad_y = 84, 58
    ic = emoji(ch, 150)
    col_w = max([m.width for m in mains] + [u.width for u in subs_im] +
                [lab.width if lab else 0])
    pw = max(1000, col_w + 2 * pad_x + (220 if ic else 0))
    ph = pad_y + ((lab.height + 30) if lab else 0) + len(mains) * lh + \
        sum(u.height + 4 for u in subs_im) + (16 if subs_im else 0) + pad_y
    px, py = (W - pw) / 2, center_block(ph)
    P = panel(pw, ph)
    paste(P, solid(10, ph - 2 * pad_y + 20, AMBER, r=5), M + 38, M + pad_y - 10)
    sc.add(Sprite(P, px - M, py - M, t0=0.0, dur=0.6, dy=40, s0=0.94))
    y = py + pad_y
    if lab:
        sc.add(Sprite(lab, px + pad_x, y, t0=0.15, dur=0.5, dy=16))
        y += lab.height + 30
    for i, m in enumerate(mains):
        sc.add(Sprite(m, px + pad_x - 4, y + i * lh - int(s * 0.06), t0=0.28 + 0.12 * i,
                      dur=0.55, dy=22))
    y += len(mains) * lh + 16
    for i, u in enumerate(subs_im):
        sc.add(Sprite(u, px + pad_x, y, t0=0.6 + 0.1 * i, dur=0.5, dy=14))
        y += u.height + 4
    if ic:
        badge = circle(210, AMBER_L)
        paste(badge, ic, (210 - ic.width) / 2, (210 - ic.height) / 2)
        sc.live.append(float_live(badge, px + pw - pad_x - 190, py + (ph - 210) / 2,
                                  t0=0.35, amp=7))


BUILD = {"d1": build_d1, "d2": build_d2, "bars": build_bars, "quote": build_quote,
         "chain": build_chain, "tiles": build_tiles, "list": build_list,
         "generic": build_generic}


def _bbox_y(sc):
    ys = []
    for sp in sc.items:
        st = sp.state(1e6)
        if st:
            img, x, y, _ = st
            a = img[..., 3]
            rows = np.where(a.max(1) > 40)[0]
            if len(rows):
                ys += [y + rows[0], y + rows[-1]]
    return (min(ys), max(ys)) if ys else None


def make_scene(text, src=""):
    global _OY
    kind, data = classify(text)
    try:
        _OY = 0.0
        sc = Scene()
        BUILD[kind](sc, data)
        bb = _bbox_y(sc)
        if bb:
            shift = (Y_TOP + Y_BOT) / 2 - 10 - (bb[0] + bb[1]) / 2
            shift = max(Y_TOP - bb[0], min(Y_BOT - bb[1], shift))
            if abs(shift) > 2:
                _OY = shift
                sc = Scene()
                BUILD[kind](sc, data)
        _OY = 0.0
    except Exception as e:  # du phong cuoi: khong bao gio vo card
        print(f"info_card: {kind} loi ({e!r}) -> generic")
        _OY = 0.0
        sc = Scene()
        kind = "generic"
        lab, main = _colon(_norm(text))
        build_generic(sc, {"label": lab, "main": main, "subs": []})
    if src and src.strip():
        sc.add(src_sprite(src))
    sc.kind = kind
    return sc


def render_info(out, dur, text=None, src="", seed=0, fps=FPS, venc=None,
                zoom=None, log_time=False):
    t_start = time.time()
    bg = BgInfo(seed=seed)
    sc = make_scene(text, src) if text else None
    n = max(1, int(round(dur * fps)))
    zmax = zoom if zoom is not None else min(1.035, 1.0 + 0.0025 * dur + 0.008)
    wr = Writer(out, fps, venc=venc)
    try:
        for i in range(n):
            t = i / fps
            fr = bg.frame(t)
            if sc:
                sc.draw(fr, t)
            z = 1.0 + (zmax - 1.0) * _ease_io(i / max(1, n - 1))
            if z > 1.0005:
                vw, vh = W / z, H / z
                fr = _view(fr, (W - vw) / 2, (H - vh) / 2, vw, vh,
                           interp=cv2.INTER_LINEAR)
            wr.write(fr)
    finally:
        wr.close()
    if log_time:
        print(f"render_info {os.path.basename(out)} {dur:.1f}s "
              f"[{getattr(sc, 'kind', 'bg')}] -> {time.time() - t_start:.1f}s")
    return out


def _ease_io(p):
    return 0.5 - 0.5 * math.cos(math.pi * min(1.0, max(0.0, p)))


def still(text, src, t, seed=0):
    """Mot khung tai t (de xem thu)."""
    bg = BgInfo(seed=seed)
    sc = make_scene(text, src) if text else None
    fr = bg.frame(t)
    if sc:
        sc.draw(fr, t)
    return fr, getattr(sc, "kind", "bg")
