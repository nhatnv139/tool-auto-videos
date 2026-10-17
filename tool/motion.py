"""
motion.py — chuyen dong MUOT (subpixel) cho anh tinh + the so kieu "long".

Vi sao co file nay: ffmpeg zoompan lam tron x/y (va kich thuoc khung cat) ve
PIXEL NGUYEN moi frame. Voi zoom/pan cham (Ken Burns 9s di 1.02 -> 1.16) buoc
that moi frame chi 0.3-0.6 px, nen hinh dung yen 1-2 frame roi nhay 1 px —
mat nguoi xem thay "giat/rung". O day dung cv2.warpAffine voi toa do THUC
(noi suy bicubic) nen moi frame dich dung phan le cua pixel, roi pipe frame
tho sang ffmpeg encode.

Ba loai:
  kenburns(img, out, ...)      anh tinh -> shot pan/zoom (wiki_images, stock_photo)
  zoom_png(png, out, ...)      card cu (PNG da ve san) zoom nhe khong giat
  card_long(spec) / bg_long    the so kieu kenh Long: nen toi gradient chuyen
                               dong + luoi + hat troi, so to xanh neon dem tu 0,
                               chu truot len + hien dan, nhan "Nguon: ..."

Chay tu run_render.sh (song song nhu cac lenh ffmpeg khac):
    python tool/motion.py <spec.json>
"""
import json
import math
import os
import re
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FPS = 24
W, H = 1920, 1080
KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_VENC = ["-c:v", "libx264", "-crf", "18", "-preset", "faster",
                "-threads", "4", "-pix_fmt", "yuv420p"]


# ---------------------------------------------------------------- pipe
class Writer:
    """Pipe frame RGB uint8 (H,W,3) sang ffmpeg."""

    def __init__(self, out, fps=FPS, w=W, h=H, venc=None, vf=None):
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
        if vf:
            cmd += ["-vf", vf]
        cmd += list(venc or DEFAULT_VENC) + ["-an", "-movflags", "+faststart", out]
        self.out = out
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                  stderr=subprocess.PIPE)

    def write(self, frame):
        self.p.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())

    def close(self):
        self.p.stdin.close()
        err = self.p.stderr.read().decode("utf-8", "replace")
        rc = self.p.wait()
        if rc != 0 or not os.path.exists(self.out):
            raise RuntimeError(f"ffmpeg loi rc={rc}: {err[-600:]}")
        return self.out


def imread_rgb(path):
    """cv2.imread khong doc duoc duong dan unicode tren Windows -> imdecode."""
    data = np.fromfile(path, dtype=np.uint8)
    im = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if im is None:
        im = np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1]
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def _cover(img, sw, sh):
    """Scale anh phu kin sw x sh roi cat giua (nhu scale=increase,crop)."""
    ih, iw = img.shape[:2]
    k = max(sw / iw, sh / ih)
    nw, nh = max(sw, int(round(iw * k))), max(sh, int(round(ih * k)))
    interp = cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC
    img = cv2.resize(img, (nw, nh), interpolation=interp)
    x0, y0 = (nw - sw) // 2, (nh - sh) // 2
    return img[y0:y0 + sh, x0:x0 + sw]


def _view(src, x0, y0, vw, vh, w=W, h=H, interp=cv2.INTER_CUBIC):
    """Lay cua so THUC (x0,y0,vw,vh) cua src, ra khung w x h (subpixel)."""
    sx, sy = w / vw, h / vh
    m = np.float32([[sx, 0, -x0 * sx], [0, sy, -y0 * sy]])
    return cv2.warpAffine(src, m, (w, h), flags=interp,
                          borderMode=cv2.BORDER_REFLECT)


# ---------------------------------------------------------------- ken burns
def kenburns(img_path, out_path, dur, idx=0, center=False, fps=FPS,
             z0=1.02, z1=1.16, venc=None, vf="eq=contrast=1.04:saturation=0.96"):
    """Thay the zoompan cua wiki_images._ken_burns, GIU NGUYEN bo cuc cu:
    nguon 2560x1440, zoom tuyen tinh theo frame 1.02<->1.16 (idx chan zoom vao,
    le zoom ra), 4 huong pan luan phien — chi khac la toa do thuc.

    Nguon 2560x1440 > khung ra: o moi muc zoom van la ha mau (1.15-1.3x) nen
    pre-blur rat nhe de bicubic khong lam lap lanh chi tiet nho.
    """
    SW, SH = 2560, 1440
    src = _cover(imread_rgb(img_path), SW, SH)
    src = cv2.GaussianBlur(src, (0, 0), 0.6)
    if idx % 2 != 0:
        z0, z1 = z1, z0
    n = max(1, int(dur * fps))
    mode = 0 if center else idx % 4
    wr = Writer(out_path, fps, venc=venc or ["-c:v", "libx264", "-preset", "veryfast",
                                             "-crf", "22", "-pix_fmt", "yuv420p"],
                vf=vf)
    try:
        for i in range(n):
            u = i / n
            z = z0 + (z1 - z0) * u
            vw, vh = SW / z, SH / z
            cx, cy = (SW - vw) / 2, (SH - vh) / 2
            if mode == 0:
                x0, y0 = cx, cy
            elif mode == 1:
                x0, y0 = (SW - vw) * u, cy
            elif mode == 2:
                x0, y0 = cx, (SH - vh) * u
            else:
                x0, y0 = (SW - vw) * (1 - u), cy
            wr.write(_view(src, x0, y0, vw, vh))
    finally:
        wr.close()
    return True


def zoom_png(png, out, dur, zoom_to=1.05, fps=FPS, fade=0.0, venc=None):
    """Card cu: PNG tinh zoom 1 -> zoom_to, tam giua, toa do thuc."""
    src = imread_rgb(png)
    if src.shape[1] != W or src.shape[0] != H:
        src = _cover(src, W, H)
    n = max(1, int(round(dur * fps)))
    vf = f"fade=t=in:st=0:d={fade}" if fade else None
    wr = Writer(out, fps, venc=venc, vf=vf)
    try:
        for i in range(n):
            z = 1.0 + (zoom_to - 1.0) * (i / max(1, n - 1))
            vw, vh = W / z, H / z
            wr.write(_view(src, (W - vw) / 2, (H - vh) / 2, vw, vh))
    finally:
        wr.close()
    return out


# ---------------------------------------------------------------- kieu "long"
NEON = (57, 255, 136)        # #39FF88 — so chinh
UP = (57, 255, 136)          # ↑
DOWN = (255, 77, 94)         # ↓ va so am
SIDE = (255, 197, 61)        # → ←
WHITE = (242, 246, 248)
GREY = (168, 182, 194)
BG_A = np.array([8, 14, 26], np.float32)       # xanh den
BG_B = np.array([10, 38, 44], np.float32)      # xanh reu dam
GLOW_A = np.array([20, 120, 80], np.float32)   # vet sang xanh neon
GLOW_B = np.array([24, 70, 140], np.float32)   # vet sang xanh lam


def _font_paths():
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    bold = [os.path.join(win, "segoeuib.ttf"),
            os.path.join(KIT_ROOT, "tool", "fonts", "arialbd.ttf")]
    reg = [os.path.join(win, "segoeui.ttf"),
           os.path.join(KIT_ROOT, "tool", "fonts", "arial.ttf")]
    semi = [os.path.join(win, "seguisb.ttf")] + bold
    pick = lambda xs: next(p for p in xs if os.path.exists(p))  # noqa: E731
    return pick(bold), pick(semi), pick(reg)


class BgLong:
    """Nen chuyen dong: gradient cheo troi + 2 vet sang Lissajous + luoi troi
    cheo + hat sang bay len + vignette. Ve gradient o 1/4 do phan giai roi
    phong len (muot, re); luoi/hat ve o do phan giai that, toa do thuc."""

    def __init__(self, seed=0, dim=1.0):
        self.rng = np.random.default_rng(seed)
        self.dim = dim
        self.sw, self.sh = W // 4, H // 4
        yy, xx = np.mgrid[0:self.sh, 0:self.sw].astype(np.float32)
        self.xx, self.yy = xx / self.sw, yy / self.sh
        # vignette (uint8, nhan bang cv2.multiply scale 1/255)
        vy, vx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((vx - W / 2) / (W / 2)) ** 2 + ((vy - H / 2) / (H / 2)) ** 2)
        v = np.clip(1.08 - 0.42 * r ** 1.6, 0.45, 1.0) * 255
        self.vig = cv2.merge([v.astype(np.uint8)] * 3)
        # luoi: anh mau lon hon khung 1 o, dich bang warpAffine (subpixel)
        self.cell = 96
        gw, gh = W + 2 * self.cell, H + 2 * self.cell
        g = np.zeros((gh, gw), np.uint8)
        for x in range(0, gw, self.cell):
            cv2.line(g, (x, 0), (x, gh), 255, 1, cv2.LINE_AA)
        for y in range(0, gh, self.cell):
            cv2.line(g, (0, y), (gw, y), 255, 1, cv2.LINE_AA)
        k = 0.06 * dim
        self.grid = cv2.merge([(g * (k * c)).astype(np.uint8)
                               for c in (0.55, 1.0, 0.85)])
        # hat
        n = 80
        self.px = self.rng.uniform(0, W, n)
        self.py = self.rng.uniform(0, H, n)
        self.vy = self.rng.uniform(10, 38, n)          # px/s bay len
        self.vx = self.rng.uniform(-6, 6, n)
        self.pr = self.rng.uniform(1.2, 3.6, n)
        self.pa = self.rng.uniform(0.25, 0.9, n) * 0.55 * dim
        self.ph = self.rng.uniform(0, 2 * np.pi, n)
        self.phase = self.rng.uniform(0, 2 * np.pi)

    def frame(self, t):
        """Tra ve uint8 (H,W,3). Phan nang (W x H) chi dung ham cv2."""
        ph = self.phase
        s = 0.5 + 0.5 * np.sin(2.2 * (self.xx * 0.8 + self.yy * 0.6) + 0.35 * t + ph)
        small = BG_A + (BG_B - BG_A) * s[..., None]
        for k, (col, amp) in enumerate(((GLOW_A, 0.55), (GLOW_B, 0.45))):
            cx = 0.5 + 0.32 * math.sin(0.11 * t * (1 + k * 0.4) + ph + k * 2.1)
            cy = 0.5 + 0.28 * math.cos(0.09 * t * (1 + k * 0.3) + ph * 1.3 + k)
            d2 = ((self.xx - cx) * 1.78) ** 2 + (self.yy - cy) ** 2
            small += col * (amp * np.exp(-d2 / 0.09))[..., None]
        # phong len o float roi moi ve uint8: tranh soc mau (banding) o gradient
        img = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
        img = img.astype(np.uint8)
        # luoi troi cheo ~14 px/s
        off = (t * 14.0) % self.cell
        m = np.float32([[1, 0, -self.cell + off], [0, 1, -self.cell + off * 0.6]])
        img = cv2.add(img, cv2.warpAffine(self.grid, m, (W, H),
                                          flags=cv2.INTER_LINEAR))
        # hat sang (shift=4 -> toa do 1/16 px)
        lay = np.zeros((H, W, 3), np.uint8)
        x = (self.px + self.vx * t) % W
        y = (self.py - self.vy * t) % H
        tw = 0.6 + 0.4 * np.sin(1.7 * t + self.ph)
        for i in range(len(x)):
            a = 255 * self.pa[i] * tw[i]
            cv2.circle(lay, (int(x[i] * 16), int(y[i] * 16)), int(self.pr[i] * 16),
                       (0.45 * a, a, 0.7 * a), -1, cv2.LINE_AA, shift=4)
        img = cv2.add(img, cv2.GaussianBlur(lay, (0, 0), 1.2))
        return cv2.multiply(img, self.vig, scale=1 / 255.0)


def _ease(p):
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3


_NUM = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")


def _tok_color(word):
    if any(a in word for a in "↑"):
        return UP
    if any(a in word for a in "↓"):
        return DOWN
    if word.strip() in ("→", "←", "->", ">", "<", "·"):
        return SIDE
    if re.search(r"\d", word):
        return DOWN if word.lstrip("(~").startswith(("-", "−")) else NEON
    return WHITE


def split_card_text(text):
    """'Nhan: gia tri · phu 1 · phu 2' -> (label, main, subs).
    Ngoac don cuoi cua main dua xuong dong phu."""
    text = " ".join(text.replace("\n", " ").split())
    parts = [p.strip() for p in re.split(r"\s+·\s+|\s+\|\s+", text) if p.strip()]
    head, subs = parts[0], parts[1:]
    label, main = "", head
    m = re.match(r"^(.{2,60}?):\s+(.+)$", head)
    if m:
        label, main = m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(.*\S)\s+(\(.+\))$", main)
    if m and re.search(r"\d", m.group(1)):
        main, subs = m.group(1), [m.group(2)] + subs
    return label, main, subs


def _count_target(main):
    """Neu main co DUNG MOT so (khong phai ngay thang) -> (start, end, value,
    decimals, grouped). Khong thi None."""
    nums = list(_NUM.finditer(main))
    if len(nums) != 1:
        return None
    m = nums[0]
    a, b = m.start(), m.end()
    if (a > 0 and main[a - 1] in "/–-" and main[a - 1] != "-") or \
            (b < len(main) and main[b] == "/" and b + 1 < len(main)
             and main[b + 1].isdigit()):
        return None
    s = m.group(0)
    grouped = "." in s
    ip, _, fp = s.replace(".", "").partition(",")
    val = float(ip + ("." + fp if fp else ""))
    if val <= 0:
        return None
    return a, b, val, len(fp), grouped


def _fmt_num(v, dec, grouped):
    s = f"{v:.{dec}f}"
    ip, _, fp = s.partition(".")
    if grouped:
        ip = f"{int(ip):,}".replace(",", ".")
    return ip + ("," + fp if fp else "")


def _segments(text):
    """Chia main thanh [(chu, mau)] theo tu (giu dau cach)."""
    out = []
    for w in re.split(r"(\s+)", text):
        if not w:
            continue
        out.append((w, WHITE if w.isspace() else _tok_color(w)))
    return out


def _fit(draw, text, path, max_w, hi, lo):
    size = hi
    while size > lo:
        f = ImageFont.truetype(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f, size
        size -= 4
    return ImageFont.truetype(path, lo), lo


def _wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _wrap2(draw, text, path, max_w, hi=150, lo=72):
    """Chia 2 dong can nhau. Khong ngat giua hai tu chu thuong lien nhau (giu
    cum "bi toa bac"), uu tien ngat truoc mui ten. Ha co chu toi khi vua.
    Tra ve (lines, font, size)."""
    words = text.split()
    plain = lambda w: not re.search(r"[\d→←↑↓·]", w)  # noqa: E731
    size = hi
    while True:
        fnt = ImageFont.truetype(path, size)
        best, best_cost = None, None
        for i in range(1, len(words)):
            if plain(words[i - 1]) and plain(words[i]) and size > lo:
                continue
            a, b = " ".join(words[:i]), " ".join(words[i:])
            wa, wb = draw.textlength(a, font=fnt), draw.textlength(b, font=fnt)
            if max(wa, wb) > max_w and size > lo:
                continue
            cost = max(wa, wb) * (0.92 if words[i] in "→←↑↓·–-" else 1.0)
            if best_cost is None or cost < best_cost:
                best, best_cost = [a, b], cost
        if best or size <= lo:
            return (best or _wrap(draw, text, fnt, max_w)[:2]), fnt, size
        size -= 6


def _rgba_layer(w, h):
    return Image.new("RGBA", (max(1, int(w)), max(1, int(h))), (0, 0, 0, 0))


def _blend(frame, layer, x, y, alpha=1.0):
    """frame uint8 HxWx3; layer np uint8 hxwx4 (RGBA). Dat goc tai (x,y).
    Chi doi ROI sang float (frame day du giu uint8 cho nhanh)."""
    if alpha <= 0.003:
        return
    h, w = layer.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = layer[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = sub[..., 3:4] * (alpha / 255.0)
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    roi = roi * (1 - a) + sub[..., :3] * a
    frame[y0:y1, x0:x1] = np.clip(roi + 0.5, 0, 255).astype(np.uint8)


def _add(frame, rgb, x, y, k=1.0):
    """Cong sang (glow) — rgb float32 hxwx3."""
    h, w = rgb.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    roi = frame[y0:y1, x0:x1].astype(np.float32) + rgb[y0 - y:y1 - y, x0 - x:x1 - x] * k
    frame[y0:y1, x0:x1] = np.clip(roi, 0, 255).astype(np.uint8)


def _glow(layer_np, sigma=16):
    """Quang sang mau theo chinh layer (premultiplied, blur o 1/4)."""
    a = layer_np[..., 3:4].astype(np.float32) / 255.0
    rgb = layer_np[..., :3].astype(np.float32)
    # chu trang chi sang nhe; chu mau (so neon, mui ten) moi toa sang manh
    sat = (rgb.max(-1, keepdims=True) - rgb.min(-1, keepdims=True)) / 255.0
    pm = rgb * a * (0.3 + 0.7 * sat)
    h, w = pm.shape[:2]
    pad = int(sigma * 3)
    pm = cv2.copyMakeBorder(pm, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    sm = cv2.resize(pm, ((w + 2 * pad) // 4 or 1, (h + 2 * pad) // 4 or 1),
                    interpolation=cv2.INTER_AREA)
    sm = cv2.GaussianBlur(sm, (0, 0), sigma / 4)
    return cv2.resize(sm, (w + 2 * pad, h + 2 * pad),
                      interpolation=cv2.INTER_LINEAR), pad


class CardLong:
    def __init__(self, text, src="", seed=0):
        self.f_bold, self.f_semi, self.f_reg = _font_paths()
        self.label, self.main, self.subs = split_card_text(text)
        self.src = src.strip()
        d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        self.d = d
        max_w = W * 0.84
        # main: 1 dong neu duoc (co chu toi thieu 96px), khong thi 2 dong
        self.f_main, self.s_main = _fit(d, self.main, self.f_bold, max_w, 200, 96)
        self.main_lines = [self.main]
        if d.textlength(self.main, font=self.f_main) > max_w:
            self.main_lines, self.f_main, self.s_main = _wrap2(
                d, self.main, self.f_bold, max_w)
        self.count = _count_target(self.main) if len(self.main_lines) == 1 else None
        self.f_label = (_fit(d, self.label, self.f_semi, max_w, 60, 36)[0]
                        if self.label else None)
        self.f_sub = ImageFont.truetype(self.f_semi, 50)
        self.sub_lines = []
        for s in self.subs[:3]:
            f, _ = _fit(d, s, self.f_semi, max_w, 50, 34)
            self.sub_lines.append((s, f))
        self.f_src = ImageFont.truetype(self.f_reg, 30)
        self._layout()
        self._static = {}

    # ---- layout: khoi giua, tranh vung phu de (y > ~790)
    def _layout(self):
        d = self.d
        gap = 26
        items = []
        if self.label:
            asc, desc = self.f_label.getmetrics()
            items.append(("label", asc + desc + 8))
        asc, desc = self.f_main.getmetrics()
        self.main_lh = int((asc + desc) * 1.02)
        items.append(("main", self.main_lh * len(self.main_lines)))
        items.append(("bar", 14))
        for s, f in self.sub_lines:
            a, b = f.getmetrics()
            items.append(("sub", a + b + 6))
        total = sum(h for _, h in items) + gap * (len(items) - 1)
        top = max(70, (790 - total) // 2 + 20)
        self.pos = []
        y = top
        for k, h in items:
            self.pos.append((k, y, h))
            y += h + gap

    def _draw_segments(self, text, fnt, color_override=None):
        tw = self.d.textlength(text, font=fnt)
        asc, desc = fnt.getmetrics()
        im = _rgba_layer(tw + 8, asc + desc + 8)
        dd = ImageDraw.Draw(im)
        x = 4
        for w, col in _segments(text):
            if not w.isspace():
                dd.text((x, 4), w, font=fnt, fill=(*(color_override or col), 255))
            x += self.d.textlength(w, font=fnt)
        return np.asarray(im)

    def _main_layer(self, line, frac):
        """Dong so chinh; frac<1 -> so dem dang chay (can phai giu mep phai)."""
        if self.count is None or frac >= 1.0:
            key = ("main", line)
            if key not in self._static:
                self._static[key] = self._draw_segments(line, self.f_main)
            return self._static[key]
        a, b, val, dec, grouped = self.count
        fnt = self.f_main
        tw = self.d.textlength(line, font=fnt)
        asc, desc = fnt.getmetrics()
        im = _rgba_layer(tw + 8, asc + desc + 8)
        dd = ImageDraw.Draw(im)
        # vi tri CUOI cua so -> ve so dang dem can phai tai mep phai do
        pre_txt, post_txt = line[:a], line[b:]
        num_x1 = 4 + self.d.textlength(line[:b], font=fnt)
        cur = _fmt_num(val * frac, dec, grouped)
        cw = self.d.textlength(cur, font=fnt)
        word_pre = re.split(r"\s", pre_txt)[-1]      # vd "+", "~" dinh lien so
        col = _tok_color(word_pre + line[a:b])
        dd.text((num_x1 - cw, 4), cur, font=fnt, fill=(*col, 255))
        if word_pre:
            pw = self.d.textlength(word_pre, font=fnt)
            dd.text((num_x1 - cw - pw, 4), word_pre, font=fnt, fill=(*col, 255))
        # phan truoc (tru tien to dinh lien) va sau giu nguyen cho
        head = pre_txt[:len(pre_txt) - len(word_pre)]
        x = 4
        for w, c in _segments(head):
            if not w.isspace():
                dd.text((x, 4), w, font=fnt, fill=(*c, 255))
            x += self.d.textlength(w, font=fnt)
        x = num_x1
        for w, c in _segments(post_txt):
            if not w.isspace():
                c2 = col if (x == num_x1 and not re.search(r"\d", w)) else c
                dd.text((x, 4), w, font=fnt, fill=(*c2, 255))
            x += self.d.textlength(w, font=fnt)
        return np.asarray(im)

    def draw(self, frame, t):
        """Ve chu len frame (uint8, sua tai cho). t giay tu dau card."""
        def anim(t0, dur=0.55, dy=46):
            p = _ease((t - t0) / dur)
            return p, (1 - p) * dy

        T_LABEL, T_MAIN, T_BAR, T_SUB, T_SRC = 0.08, 0.22, 0.45, 0.6, 0.9
        COUNT = 1.15
        for k, y, h in self.pos:
            if k == "label":
                key = ("label",)
                if key not in self._static:
                    self._static[key] = self._draw_segments(
                        self.label, self.f_label, color_override=GREY)
                L = self._static[key]
                p, dy = anim(T_LABEL)
                _blend(frame, L, (W - L.shape[1]) / 2, y + dy, p)
            elif k == "main":
                p, dy = anim(T_MAIN, 0.6, 60)
                frac = _ease((t - T_MAIN) / COUNT) if self.count else 1.0
                for i, line in enumerate(self.main_lines):
                    L = self._main_layer(line, frac)
                    x = (W - L.shape[1]) / 2
                    yy = y + i * self.main_lh + dy
                    if p > 0.01:
                        gkey = ("glow", line)
                        if frac < 1.0 or gkey not in self._static:
                            g = _glow(L)
                            if frac >= 1.0:
                                self._static[gkey] = g
                        else:
                            g = self._static[gkey]
                        gl, pad = g
                        pulse = 0.55 + 0.12 * math.sin(2.2 * t)
                        _add(frame, gl, x - pad, yy - pad, pulse * p)
                    _blend(frame, L, x, yy, p)
            elif k == "bar":
                p = _ease((t - T_BAR) / 0.7)
                if p > 0:
                    bw = int(260 * p)
                    x0 = (W - bw) // 2
                    frame[y + 4:y + 10, x0:x0 + bw] = np.array(NEON, np.uint8)
        # dong phu (ve rieng de biet thu tu xuat hien)
        subs_pos = [(y, h) for k, y, h in self.pos if k == "sub"]
        for j, ((s, f), (y, h)) in enumerate(zip(self.sub_lines, subs_pos)):
            key = ("sub", j)
            if key not in self._static:
                self._static[key] = self._draw_segments(s, f)
                # chu thuong cua dong phu: xam sang thay vi trang
                arr = self._static[key].copy()
                wmask = np.all(arr[..., :3] == np.array(WHITE, np.uint8), -1)
                arr[wmask, :3] = np.array((205, 215, 224), np.uint8)
                self._static[key] = arr
            L = self._static[key]
            p, dy = anim(T_SUB + 0.15 * j)
            _blend(frame, L, (W - L.shape[1]) / 2, y + dy, p)
        if self.src:
            key = ("src",)
            if key not in self._static:
                txt = "Nguồn: " + self.src
                fnt = self.f_src
                while self.d.textlength(txt, font=fnt) > W * 0.6 and len(txt) > 20:
                    txt = txt[:-2]
                tw = self.d.textlength(txt, font=fnt)
                a, b = fnt.getmetrics()
                im = _rgba_layer(tw + 36, a + b + 18)
                dd = ImageDraw.Draw(im)
                dd.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=10,
                                     fill=(6, 12, 20, 170))
                dd.rectangle((0, 6, 4, im.height - 7), fill=(*NEON, 255))
                dd.text((20, 8), txt, font=fnt, fill=(*GREY, 255))
                self._static[key] = np.asarray(im)
            L = self._static[key]
            p = _ease((t - T_SRC) / 0.6)
            _blend(frame, L, 48, H - L.shape[0] - 40, p)


def render_long(out, dur, text=None, src="", seed=0, fps=FPS, venc=None,
                zoom=None, log_time=False):
    """text=None -> chi nen (thay [[black]]). Zoom cham toan khung suot card."""
    import time
    t_start = time.time()
    bg = BgLong(seed=seed, dim=1.0 if text else 0.9)
    card = CardLong(text, src, seed) if text else None
    n = max(1, int(round(dur * fps)))
    zmax = zoom if zoom is not None else min(1.06, 1.0 + 0.004 * dur + 0.01)
    wr = Writer(out, fps, venc=venc)
    try:
        for i in range(n):
            t = i / fps
            fr = bg.frame(t)
            if card:
                card.draw(fr, t)
            z = 1.0 + (zmax - 1.0) * (i / max(1, n - 1))
            if z > 1.0005:
                vw, vh = W / z, H / z
                fr = _view(fr, (W - vw) / 2, (H - vh) / 2, vw, vh)
            wr.write(fr)
    finally:
        wr.close()
    if log_time:
        print(f"render_long {os.path.basename(out)} {dur:.1f}s -> "
              f"{time.time() - t_start:.1f}s")
    return out


def main(argv):
    spec = json.load(open(argv[1], encoding="utf-8"))
    kind = spec.pop("kind")
    if kind == "zoom_png":
        zoom_png(**spec)
    elif kind == "long":
        render_long(**spec)
    elif kind == "info":
        from info_card import render_info
        render_info(**spec)
    elif kind == "kenburns":
        kenburns(**spec)
    else:
        raise SystemExit(f"motion: kind la {kind}")


if __name__ == "__main__":
    main(sys.argv)
