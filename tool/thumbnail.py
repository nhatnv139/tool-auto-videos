"""
thumbnail.py — Sinh thumb YouTube 1280x720 kieu CAMERA QUAN SAT (CCTV).

Concept: frame nhu camera ghi hinh robot AI dang hoat dong — cold grade,
scanlines, timestamp "REC", vignette — cam giac 'AI being watched'.
Text chinh 'IT KNOWS' (amber) + tag nho 'SURVEILLANCE FOOTAGE'.

Dung PIL (khong can ffmpeg cho text), frame goc lay tu --src (mp4 stock)
hoac --png. Default: robot hand touch human (camera angle tot).
"""
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMB_W, THUMB_H = 1280, 720

INK = (20, 17, 15)          # #14110F
AMBER = (224, 168, 46)      # #E0A82E
PAPER = (242, 237, 228)     # #F2EDE4
COLD = (176, 196, 215)      # xanh lanh (CCTV)
COLD_DIM = (120, 138, 158)


def _font(name, size):
    p = os.path.join(KIT_ROOT, "tool", "fonts", name)
    if not os.path.exists(p):
        raise SystemExit(f"thieu font {p}")
    return ImageFont.truetype(p, size)


def _grab_frame(src, t, root):
    """Lay frame tai giay t tu mp4 (cover 1280x720) ve temp PNG."""
    import hashlib
    tmp = os.path.join(root, "build", "tmp")
    os.makedirs(tmp, exist_ok=True)
    png = os.path.join(tmp, f"thumb-{hashlib.md5(f'{src}{t}'.encode()).hexdigest()[:8]}.png")
    if not os.path.exists(png):
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", src,
             "-frames:v", "1", "-vf",
             "scale=1280:720:force_original_aspect_ratio=increase,"
             "crop=1280:720,setsar=1", png],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(png):
            raise SystemExit(f"grab frame loi: {r.stderr[-400:]}")
    return png


def _cctv_grade(img):
    """Cold grade + tang contrast + scanlines + vignette — cam giac camera quan sat."""
    a = np.asarray(img).astype(np.float32)
    # cold grade: dua ve xanh-lanh, giam bao hoa
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    a[..., 0] = r * 0.82 + g * 0.12 + b * 0.10
    a[..., 1] = r * 0.10 + g * 0.92 + b * 0.14
    a[..., 2] = r * 0.10 + g * 0.18 + b * 0.96
    # contrast
    a = (a - 128) * 1.18 + 128
    a = np.clip(a, 0, 255)
    # scanlines ngang mo (nhe)
    yy = np.arange(THUMB_H)
    scan = (np.sin(yy * 0.9) * 0.5 + 0.5) * 7
    a -= scan[:, None, None].astype(np.float32)
    a = np.clip(a, 0, 255).astype(np.uint8)
    img = Image.fromarray(a, "RGB")
    # vignette nhe — chi goc
    yy, xx = np.mgrid[0:THUMB_H, 0:THUMB_W]
    cx, cy = THUMB_W / 2, THUMB_H / 2
    d = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    vig = np.clip(1.0 - (d - 0.72) * 0.9, 0.0, 1.0)
    vig = vig[..., None] * np.ones((1, 1, 3))
    base = np.asarray(img).astype(np.float32)
    base *= vig
    base = np.clip(base, 0, 255).astype(np.uint8)
    return Image.fromarray(base, "RGB")


def render(root, src=None, frame_t=0.0, text_main="IT KNOWS",
           text_sub="WHEN THE CAMERA IS ON"):
    if src and os.path.exists(src):
        png = _grab_frame(src, frame_t, root)
    else:
        png = None
    if png:
        img = Image.open(png).convert("RGB").resize((THUMB_W, THUMB_H))
        img = _cctv_grade(img)
    else:
        # fallback: nen toi doi khi khong co frame
        img = Image.new("RGB", (THUMB_W, THUMB_H), INK)
    d = ImageDraw.Draw(img)

    # tag nho tren cung — 'SURVEILLANCE FOOTAGE' + cham REC do
    tagf = _font("arial.ttf", 26)
    tag = "SURVEILLANCE FOOTAGE"
    d.text((28, 22), tag, font=tagf, fill=COLD)
    d.ellipse([30, 34, 30 + 14, 34 + 14], fill=(214, 69, 62))
    d.text((52, 27), "REC", font=tagf, fill=(214, 69, 62))

    # timestamp goc phai tren — kieu dong ho camera
    ts = "2026-08-10  11:41:07"
    d.text((THUMB_W - 28 - d.textlength(ts, font=tagf), 24), ts,
           font=tagf, fill=COLD_DIM)

    # phan den phia duoi de text noi (gradient tu duoi len, che vua du)
    yy = np.linspace(0, 1, THUMB_H)[:, None]
    alpha = np.clip((yy - 0.70) / 0.25, 0.0, 0.85)
    overlay = Image.new("RGB", (THUMB_W, THUMB_H), INK)
    mask = Image.fromarray(np.tile(alpha, (1, THUMB_W)).astype(np.uint8), "L")
    img = Image.composite(overlay, img, mask)
    d = ImageDraw.Draw(img)

    # text chinh — mac dinh 'IT KNOWS', co the truyen khac
    big = _font("arialbd.ttf", 150)
    txt = text_main
    w = d.textlength(txt, font=big)
    x = (THUMB_W - w) / 2
    y = THUMB_H - 250
    d.text((x + 4, y + 5), txt, font=big, fill=(0, 0, 0))
    d.text((x, y), txt, font=big, fill=AMBER)

    # subtext nho hon — hoan thanh cau (khong lap text chinh)
    sub = text_sub
    subf = _font("arialbd.ttf", 40)
    w2 = d.textlength(sub, font=subf)
    sy = y + 168
    d.text(((THUMB_W - w2) / 2 + 2, sy + 2), sub, font=subf, fill=(0, 0, 0))
    d.text(((THUMB_W - w2) / 2, sy), sub, font=subf, fill=PAPER)

    out_dir = os.path.join(root, "assets")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "thumb.png")
    img.save(out)
    print(f"thumb -> {out}")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--src", default=None, help="mp4 stock de lay frame (default: robot)")
    ap.add_argument("--t", type=float, default=0.0, help="giay lay frame")
    ap.add_argument("--text", default="IT KNOWS", help="text chinh (mac dinh 'IT KNOWS')")
    ap.add_argument("--sub", default="WHEN THE CAMERA IS ON", help="text phu")
    args = ap.parse_args()

    root = os.path.abspath(args.case)
    if args.src:
        src = os.path.abspath(args.src)
    else:
        import hashlib
        stock = os.path.join(os.path.dirname(os.path.dirname(root)), "assets", "stock")
        cand = os.path.join(stock, hashlib.md5(
            b"pixabay|robot hand touch human|0").hexdigest()[:12] + ".mp4")
        src = cand if os.path.exists(cand) else None
    render(root, src=src, frame_t=args.t, text_main=args.text, text_sub=args.sub)


if __name__ == "__main__":
    main()
