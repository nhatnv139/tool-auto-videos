"""
render.py — Sinh build/shots/cell-<id>.mp4 cho tung cell trong config.

Loai cell:
  clip        talking-head: giu tieng goc, grade cinema nhe, attribution tag
  clip-mute   b-roll: lay hinh clip, tat tieng (audio bo o stage 3)
  card        text tren nen toi (PIL, zoom kenburns)
  quote       quote lon + attribution (PIL)
  hold        dung yen khung cuoi shot truoc + zoom nhe
  black       man hinh den
  sfx         video den + audio hit (cho assemble lay lam SFX)
  outro       card "nguon / video lien quan" (PIL)

Caption khong render o day — duoc burn o stage-1 trim (assemble) vi can
biet vo_dur thuc. Cell clip-co-tieng chi them attribution.

ffmpeg filter phuc tap EMIT ra build/run_render.sh, chay qua git-bash
(may nay segfault khi subprocess spawn filter phuc tap — kinh nghiem
truecrime-kit).
"""
import os
import shlex
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from probe import duration, streams

FPS = 24
W, H = 1920, 1080
KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Khoang thoi gian (giay, trong video) khong duoc dung lai 1 content stock gan nhat.
# Dedup theo "khoang thoi gian cell da dung": cell tai thoi diem t khong dung content
# da xuat hien trong [t-COOLDOWN, t]. Het content "mat" -> chon content dung lau nhat.
# Vi thu vien co ~791 content unique (du cho ca video 10-15 phut), mac dinh dedup
# TOAN VIDEO (COOLDOWN lon) — chi dung lai khi can kiet content. Giam neu pool nho.
COOLDOWN = 1e9

_sh = []


# ---------------------------------------------------------------- helpers
def hex_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=fnt) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def emit(cmd, root):
    _sh.append("r " + " ".join(shlex.quote(a) for a in cmd))


def run_sh(root, script_name="run_render.sh"):
    sh = os.path.join(root, "build", script_name)
    os.makedirs(os.path.dirname(sh), exist_ok=True)
    root_posix = "/" + root.replace("\\", "/").replace(":", "").lower()  # C:/x -> /c/x
    with open(sh, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\nset -e\n")
        f.write(f'cd "{root_posix}"\n')
        f.write("r() { n=0; while :; do \"$@\" && return 0; n=$((n+1)); "
                "[ $n -ge 3 ] && return 1; echo \"  retry $n\" >&2; sleep 1; done; }\n")
        f.write("\n".join(_sh) + "\n")
        f.write('echo "RENDER OK"\n')
    n = len([l for l in _sh if l.startswith("r ")])
    _sh.clear()
    return sh, n


def encode_frames(frames_dir, out, dur, crf=15):
    cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
           "-i", os.path.join(frames_dir, "%04d.jpg"),
           "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p", out]
    for _ in range(4):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return out
    raise SystemExit(f"encode {out} that bai:\n{r.stderr[-800:]}")


def render_kenburns_frames(src_img, dur, fdir, zoom_from=1.0, zoom_to=1.04,
                           center=(0.5, 0.5), fade_in=0.4, grain=1.0):
    import PIL.Image as _I
    SRC = 2
    sw, sh = W * SRC, H * SRC
    base = src_img.convert("RGB").resize((sw, sh), _I.LANCZOS)
    arr = np.asarray(base, dtype=np.float32)
    frames = int(dur * FPS)
    cx, cy = int(sw * center[0]), int(sh * center[1])
    os.makedirs(fdir, exist_ok=True)
    for n in range(frames):
        z = zoom_from + (zoom_to - zoom_from) * (n / max(1, frames - 1))
        vw, vh = sw / z, sh / z
        x0 = cx - vw / 2
        y0 = cy - vh / 2
        x0i, y0i = int(np.floor(x0)), int(np.floor(y0))
        xi, yi = int(np.ceil(x0 + vw)), int(np.ceil(y0 + vh))
        tile = np.pad(arr, ((max(0, -y0i), max(0, yi - sh)),
                            (max(0, -x0i), max(0, xi - sw)), (0, 0)),
                      mode="edge")
        offx = x0i - min(0, x0i)
        offy = y0i - min(0, y0i)
        sub = tile[offy:offy + (yi - y0i), offx:offx + (xi - x0i)]
        im = _I.fromarray(np.clip(sub, 0, 255).astype(np.uint8))
        im = im.resize((W, H), _I.LANCZOS)
        if fade_in > 0 and n < fade_in * FPS:
            k = (n + 1) / (fade_in * FPS)
            im = _I.blend(_I.new("RGB", (W, H), (0, 0, 0)), im, k)
        if grain:
            g = np.random.default_rng(n).normal(0.0, grain, (H, W, 1))
            a = np.asarray(im, dtype=np.float32)
            a = np.clip(a + g, 0, 255).astype(np.uint8)
            im = _I.fromarray(a)
        im.save(os.path.join(fdir, f"{n:04d}.jpg"), quality=92, subsampling=0)
    return frames


# ---------------------------------------------------------------- PIL cards
def _fit_font(d, text, f_bold, max_w, max_lines, S):
    """Chon font size lon nhat sao cho text wrap <= max_lines, khong tran max_w."""
    size = 76
    best = (size, None)
    while size >= 30:
        fnt = font(f_bold, int(size * S))
        lines = wrap(d, text, fnt, max_w)
        if len(lines) <= max_lines:
            return size, lines, fnt
        size -= 4
    size = 30
    fnt = font(f_bold, int(size * S))
    lines = wrap(d, text, fnt, max_w)
    return size, lines, fnt


def _draw_box_text(d, base, lines, fnt, lh, max_w, y_start, color=("paper",)):
    """Ve text can giua theo cot, moi dong mau rieng. Tra ve y cuoi."""
    y = y_start
    for i, ln in enumerate(lines):
        col = color if isinstance(color, str) else color[i % len(color)]
        col = hex_rgb(col) if isinstance(col, str) else col
        ww = d.textlength(ln, font=fnt)
        d.text(((base.width - ww) / 2, y), ln, font=fnt, fill=col)
        y += lh
    return y


def render_pil(cell, style, out, root):
    """card / quote: ve text 1 lan thanh PNG, zoom nhe thanh video.

    Auto-shrink font theo do dai text (khong nhon dong), line-height 1.7,
    max 3 dong cho card. Quote: chu ngoac kep + attribution.
    """
    dur = cell.get("dur", 5.0)
    ink = hex_rgb(style["ink"])
    paper = hex_rgb(style["paper"])
    amber = hex_rgb(style["amber"])
    f_reg = style["font_reg"]
    f_bold = style["font_bold"]
    f_reg = os.path.join(KIT_ROOT, f_reg) if not os.path.isabs(f_reg) else f_reg
    f_bold = os.path.join(KIT_ROOT, f_bold) if not os.path.isabs(f_bold) else f_bold

    fdir = os.path.join(root, "build", "tmp", "cell-" + str(cell["id"]))
    os.makedirs(fdir, exist_ok=True)
    png_path = os.path.join(fdir, "card.png")

    S = 2
    base = Image.new("RGB", (W * S, H * S), ink)
    # gradient nhe de khong phang
    yy = np.linspace(-1, 1, H * S)[:, None]
    grad = (np.clip(1 - np.abs(yy) * 0.45, 0.62, 1.0) * 255)
    overlay = Image.new("RGB", (W * S, H * S), (0, 0, 0))
    mask = Image.fromarray(np.tile(grad, (1, W * S)).astype(np.uint8), "L")
    base = Image.composite(overlay, base, mask)
    d = ImageDraw.Draw(base)

    max_w = W * S * 0.78
    if cell["type"] == "quote":
        text = cell.get("text", "")
        who = cell.get("who", "")
        role = cell.get("role", "")
        size, lines, fnt = _fit_font(d, text, f_bold, max_w, 3, S)
        lh = int(size * 1.55 * S)
        extra = (int(size * 1.5 * S)) if who else 0
        total_h = len(lines) * lh + extra
        y = (H * S - total_h) // 2
        # dau ngoac kep am — dau ngoac deco
        q = '"'
        if len(lines) == 1:
            text1 = f"{q}{lines[0]}{q}"
            ww = d.textlength(text1, font=fnt)
            d.text(((W * S - ww) / 2, y), text1, font=fnt, fill=paper)
            y += lh
        else:
            for ln in lines:
                ww = d.textlength(ln, font=fnt)
                d.text(((W * S - ww) / 2, y), ln, font=fnt, fill=paper)
                y += lh
            # ve dau ngoac kep to o phia tren
            qfnt = font(f_bold, int(size * 2.2 * S))
            d.text((int(W * S * 0.06), int(H * S * 0.14)), '"', font=qfnt, fill=amber)
        if who:
            y += int(size * 0.45 * S)
            at = (who + (" — " + role if role else ""))
            sfnt = font(f_reg, int(26 * S))
            sw = d.textlength(at, font=sfnt)
            d.text(((W * S - sw) / 2, y), at, font=sfnt, fill=amber)
    else:  # card
        text = cell.get("text", "") or cell.get("cap", "")
        size, lines, fnt = _fit_font(d, text, f_bold, max_w, 3, S)
        lh = int(size * 1.7 * S)
        y = (H * S - len(lines) * lh) // 2
        for i, ln in enumerate(lines):
            color = amber if i == len(lines) - 1 and cell.get("emph_last") else paper
            ww = d.textlength(ln, font=fnt)
            d.text(((W * S - ww) / 2, y), ln, font=fnt, fill=color)
            y += lh
        src = cell.get("src")
        if src:
            sfnt = font(f_reg, int(22 * S))
            stxt = f"SOURCE: {src}"
            sw = d.textlength(stxt, font=sfnt)
            d.rounded_rectangle((int(40 * S), H * S - int(60 * S),
                                 int(40 * S) + sw + int(24 * S), H * S - int(20 * S)),
                                radius=4, fill=(0, 0, 0))
            d.text((int(52 * S), H * S - int(50 * S)), stxt, font=sfnt, fill=amber)

    base = base.resize((W, H), Image.LANCZOS)
    base.save(png_path, quality=95)
    # ffmpeg zoompan tren PNG (nhanh hon ve tung frame bang PIL)
    png_rel = os.path.relpath(png_path, root).replace("\\", "/")
    zoom_to = cell.get("zoom_end", 1.05)
    z = 1.0 / 60.0  # tang 1.0 -> zoom_to trong ~dur*60 buoc (cham, muot)
    zstep = (zoom_to - 1.0) / (dur * 60.0)
    # card/quote: khong fade-in o render (tranh den 0.4s truoc khi text hien;
    # stage1 xu ly fade nhanh 0.2s). Giu zoompan nhe.
    fade = cell.get("fade_in", 0.0)
    vf = (f"scale={W}:{H},setsar=1,"
          f"zoompan=z='min(zoom+{zstep:.5f},{zoom_to})':"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"d=1:fps={FPS}:s={W}x{H},"
          f"format=yuv420p")
    if fade:
        vf += f",fade=t=in:st=0:d={fade}"
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-loop", "1", "-t", f"{dur:.3f}", "-i", png_rel,
           "-vf", vf, "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
           os.path.join(root, out)]
    emit(cmd, root)
    return os.path.join(root, out)


# ---------------------------------------------------------------- ffmpeg types
def _ensure_fonts(root):
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    for src, dst in (("arial.ttf", "arial.ttf"), ("arialbd.ttf", "arialbd.ttf")):
        s = os.path.join(KIT_ROOT, "tool", "fonts", src)
        d = os.path.join(tdir, dst)
        if not os.path.exists(d):
            import shutil
            shutil.copy(s, d)
    return "build/tmp/arial.ttf", "build/tmp/arialbd.ttf"


def _escape_ffpath(p):
    """Escape path cho ffmpeg option: C:\\Users -> C\\:/Users (colon dau tien)."""
    p = p.replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = p[0] + "\\:" + p[2:]
    return p


def _textfile(root, text):
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    import hashlib
    h = hashlib.md5(text.encode("utf-8")).hexdigest()[:10]
    p = os.path.join(tdir, f"t-{h}.txt")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return os.path.relpath(p, root).replace("\\", "/")


def _attribution_filter(root, cell, f_reg, f_bold, label_in="[v0]", label_out="[v]"):
    """Tag ten + vai tro nguoi noi, hien sau 0.5s, goc trai tren."""
    who = cell.get("src") or " ".join(x for x in (cell.get("speaker"), cell.get("role")) if x)
    if not who:
        return f"{label_in}{label_out}"
    tf = _textfile(root, who)
    fpath = f_bold if f_bold else "build/tmp/arialbd.ttf"
    alpha = "if(lt(t\\,0.5)\\,0\\,min(1\\,(t-0.5)/0.4))"
    sep = "," if not label_in.endswith(",") else ""
    return (f"{label_in}{sep}drawtext=fontfile={fpath}:textfile={tf}:fontsize=34:"
            f"fontcolor=white:x=48:y=48:alpha={alpha}:"
            f"box=1:boxcolor=black@0.55:boxborderw=18:"
            f"shadowcolor=black@0.8:shadowx=2:shadowy=2{label_out}")


def _cinema(cell):
    """Grade dien anh + film grain + vignette + letterbox; fx per-cell.

    cinema: bat mac dinh cho clip/stock (tru khi "cinema": false). Per-cell fx:
      blur-in  — mo ro net trong 1.2s dau (cold open)
      vhs      — scanline + chroma noise
      glitch   — jitter crop ngang nhe
      shake    — camera shake 0.5s dau (impact moment)
      flash    — trang flash 0.15s dau (cut den / hit)
    """
    if cell.get("cinema") is False:
        return ""
    strength = cell.get("cinema_strength", 6)
    fx = cell.get("fx", "")
    parts = []
    # base grade
    parts.append(f"noise=alls={strength}:allf=t")
    parts.append("eq=contrast=1.06:saturation=0.90:brightness=-0.02:gamma=0.98")
    parts.append("vignette=angle=PI/5")
    # letterbox nhe (cinematic bars)
    parts.append("drawbox=x=0:y=0:w=iw:h=44:color=black:t=fill")
    parts.append("drawbox=x=0:y=ih-44:w=iw:h=44:color=black:t=fill")
    if fx == "blur-in":
        # boxblur radius khong ho tro bieu thuc t trong build nay -> static 1.2s
        parts.append(r"boxblur=luma_radius=14:luma_power=1:enable=lt(t\,1.2)")
    elif fx == "vhs":
        parts.append("noise=alls=14:allf=t,chromashift=cb=2:cr=-2")
    elif fx == "glitch":
        parts.append("crop=w=iw-6*random(1):h=ih,pad=iw+6:ih:(ow-iw)/2:0:0x14110F")
    elif fx == "shake":
        # crop jitter theo sin tan nhanh 0.5s dau
        parts.append(r"crop=w=iw:h=ih:x='8*sin(80*t)*lt(t\,0.5)'"
                     r":y='5*sin(70*t+1)*lt(t\,0.5)'")
    elif fx == "flash":
        # white flash 0.15s: dung fade tu trang (dau clip)
        parts.append("fade=t=in:st=0:d=0.15:color=white")
    return "," + ",".join(parts)


def _reframe(cell):
    """Crop/zoom reframe de video fingerprint khac ban goc (tranh Content ID).

    Mac dinh: zoom 1.06 (reframe nhe). Tu chon:
      zoom=1.12      scale len
      crop=x,y,w,h   (ty le 0-1): x,y = goc, w,h = kich thuoc vung giu
      flip=true      lat ngang
    """
    zoom = cell.get("zoom", 1.06)
    crop = cell.get("crop")
    parts = []
    if crop:
        x, y, w, h = (float(v) for v in crop.split(","))
        parts.append(f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}")
    if zoom and abs(zoom - 1.0) > 0.001:
        parts.append(f"scale=iw*{zoom}:ih*{zoom}")
    if cell.get("flip"):
        parts.append("hflip")
    if not parts:
        return ""
    return ",".join(parts)


def render_clip(cell, out, root, style=None):
    """clip / clip-mute: reframe + scale 1080p + cinema + attribution.

    clip-mute: bo audio tru khi cell co 'low' (giu audio ~0.2, VO duck de).
    """
    src = os.path.join(root, "assets", "clips", f"clip-{cell['clip']}.mp4")
    if not os.path.exists(src):
        raise SystemExit(f"cell {cell['id']}: thieu clip {src}. Chay fetch truoc.")
    dur = cell.get("dur")
    clip_dur = duration(src)
    if dur is None or dur <= 0:
        dur = clip_dur
    else:
        dur = min(dur, clip_dur)
    f_reg, f_bold = _ensure_fonts(root)
    reframe = _reframe(cell)
    scale = f"[0:v]"
    if reframe:
        scale += reframe + ","
    scale += (f"scale=1920:1080:force_original_aspect_ratio=decrease,"
              f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x14110F,"
              f"setsar=1,format=yuv420p,fps={FPS}")
    scale += _cinema(cell)
    # chi hien attribution (ten nguoi noi) cho clip talking-head, KHONG phai
    # clip-mute/broll (broll la nen khi VO doc, VO tu gioi thieu)
    if cell["type"] == "clip":
        fc = _attribution_filter(root, cell, f_reg, f_bold,
                                 label_in=scale, label_out="[v]")
    else:
        fc = f"{scale}[v]"
    is_mute = cell["type"] == "clip-mute"
    low = cell.get("low")
    keep_audio = (not is_mute) or low
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src,
           "-filter_complex", fc,
           "-map", "[v]"]
    if keep_audio:
        cmd += ["-map", "0:a?"]
    cmd += ["-c:v", "libx264", "-crf", "16"]
    if keep_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
        if low:
            cmd += ["-filter:a", "volume=0.22"]
    cmd += ["-t", f"{dur:.3f}", os.path.join(root, out)]
    emit(cmd, root)
    return dur


def render_black(cell, out, root):
    dur = cell.get("dur", 3.0)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
           "-i", f"color=c=0x000000:s={W}x{H}:r={FPS}:d={dur}",
           "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
           os.path.join(root, out)]
    emit(cmd, root)
    return dur


def render_sfx(cell, out, root):
    dur = cell.get("dur", 0.8)
    hit_at = cell.get("hit_at", 0.0)
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    # SFX ten (assets/sfx/<ten>.mp3) hoac noise hit tu sinh
    from sfx import sfx_file
    named = sfx_file(root, cell.get("sfx")) if cell.get("sfx") else None
    if named:
        src_dur = duration(named)
        # neu khai dur (ngan hon file) thi trim + fade out
        trim = min(dur, src_dur) if cell.get("dur") else src_dur
        total = max(trim, hit_at + 0.5)
        af = (f"adelay={int(hit_at*1000)}|{int(hit_at*1000)},apad,"
              f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
              f"afade=t=out:st={max(0.0, total-0.2):.2f}:d=0.2")
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-f", "lavfi", "-i", f"color=c=0x000000:s={W}x{H}:r={FPS}:d={total}",
               "-i", named,
               "-filter:a", af,
               "-map", "0:v", "-map", "1:a",
               "-c:v", "libx264", "-crf", "16", "-c:a", "aac",
               "-t", str(total), os.path.join(root, out)]
        emit(cmd, root)
        return total
    hit_wav = os.path.join(tdir, f"hit-{cell['id']}.wav")
    gen = (f"anoisesrc=color=pink:sample_rate=48000:amplitude=0.6:duration={dur}:seed=7,"
           f"lowpass=f=3200,highpass=f=120,"
           f"afade=t=in:st=0:d=0.005,afade=t=out:st={max(0.0, dur-0.25):.2f}:d=0.25,"
           f"volume=1.6,adelay={int(hit_at*1000)}|{int(hit_at*1000)}")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", gen,
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", hit_wav],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"sfx gen loi: {r.stderr[-500:]}")
    total = max(dur, hit_at + 0.8)
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", f"color=c=0x000000:s={W}x{H}:r={FPS}:d={total}",
           "-i", hit_wav,
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-crf", "16", "-c:a", "aac",
           "-t", str(total), os.path.join(root, out)]
    emit(cmd, root)
    return total


def render_hold(prev_shot, out, root, dur=4.0):
    fdir = os.path.join(root, "build", "tmp", "cell-hold")
    os.makedirs(fdir, exist_ok=True)
    frame_png = os.path.join(fdir, "last.png")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2",
                        "-i", prev_shot, "-frames:v", "1", frame_png],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"extract last frame loi: {r.stderr[-600:]}")
    img = Image.open(frame_png).convert("RGB")
    fdir2 = os.path.join(root, "build", "tmp", "cell-hold-frames")
    render_kenburns_frames(img, dur, fdir2, zoom_from=1.0, zoom_to=1.03,
                           center=(0.5, 0.5), fade_in=0.0, grain=0.8)
    out_path = os.path.join(root, out)
    encode_frames(fdir2, out_path, dur)
    return dur


def render_outro(cell, style, out, root):
    """Card don gian: 'nguon: xem mo ta' + link. Chua co thumbs strip."""
    dur = cell.get("dur", 10.0)
    card = dict(cell, type="card", text=cell.get("text", "Sources in the description."),
                src=cell.get("src", ""))
    return render_pil(card, style, out, root)


def render_stock(cell, out, root, style=None, stock_idx=0, avail=None,
                 src_override=None, segment_pool=None, timeline=None,
                 cell_start=0.0):
    """stock: footage tu Pixabay/Pexels (mute), VO doc de. Fallback ve card.

    src_override: file CU THE da chon boi render_all (dedup toan video) — dung
    file nay thay vi tu chon theo idx. Neu None -> tu chon tu pool keyword.
    Cell dai -> moi doan 6s dung MOT FILE khac nhau (xoay qua pool).
    timeline (list mutable): moi segment append {cell,file,content,start,end}
    de do luong "cell nao, giay nao da dung" cho lan cat ke tiep.
    """
    from stock import stock_pool, _content_hash
    kw = cell.get("stock") or cell.get("keyword") or ""
    if src_override:
        src = src_override
    else:
        if avail is None:
            avail = stock_pool(root, kw) if kw else []
        src = avail[stock_idx % len(avail)] if avail else None
    if not src or not os.path.exists(src):
        print(f"  WARN cell {cell['id']}: khong co stock cho '{kw}' -> dung card")
        card = dict(cell, type="card", text=cell.get("cap") or cell.get("vo") or kw,
                    src="stock")
        return render_pil(card, style, out, root)
    clip_cell = dict(cell, type="clip-mute", clip=None)
    f_reg, f_bold = _ensure_fonts(root)
    # cell stock co VO: dur = vo_dur + pause (neu voice file da co tu tts).
    dur = cell.get("dur")
    if cell.get("vo"):
        vo_path = os.path.join(root, "build", "voice", f"cell-{cell['id']}.mp3")
        if os.path.exists(vo_path):
            dur = duration(vo_path) + cell.get("pause_after", 0.0)
        else:
            print(f"  WARN cell {cell['id']}: VO chua co file voice ({os.path.basename(vo_path)}) "
                  f"— dang dung duration file stock, video se DUNG HINH khi voice dai hon. "
                  f"Chay tts TRUOC khi render lai.")
    if dur is None or dur <= 0:
        dur = duration(src)
    reframe = _reframe(clip_cell)

    SEG = 6.0  # moi doan stock 6s (giam nhu cau so doan, it lap hon)
    if timeline is None:
        timeline = []
    # content da dung trong video (toan bo) — ko dung lai
    used_at = {}
    for rec in timeline:
        h = rec.get("content")
        if h:
            used_at.setdefault(h, rec.get("end", 0))

    if dur <= SEG + 1.5:
        _render_stock_segment(src, 0.0, dur, reframe, clip_cell, f_reg, f_bold, root, out)
        timeline.append({"cell": cell["id"], "file": src,
                         "content": _content_hash(src),
                         "start": cell_start, "end": cell_start + dur})
        return dur
    # cell dai: moi doan dung 1 file khac nhau, uu tien content chua dung toan video.
    n_seg = int(dur / SEG) + 1
    seg_files = []
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    # pool xoay: uu tien segment_pool (global, da dedup content) roi avail
    rotate_pool = segment_pool or avail or ([src] if src else [])
    # content fresh: chua dung bao gio trong video
    fresh = [f for f in rotate_pool
             if _content_hash(f) and _content_hash(f) not in used_at]
    # sap xep de bat dau tu src_override (giu lien mach voi cell)
    if fresh and src in fresh:
        fresh.insert(0, fresh.pop(fresh.index(src)))
    pool = fresh or rotate_pool
    for i in range(n_seg):
        f = pool[i % len(pool)] if pool else src
        seg_file = os.path.join(tdir, f"stockseg-{cell['id']}-{i}.mp4")
        seg_dur = min(SEG, max(0.0, dur - i * SEG))
        if seg_dur <= 0.3:
            break
        _render_stock_segment(f, 0.0, seg_dur, reframe, clip_cell, f_reg, f_bold,
                              root, seg_file)
        seg_files.append(seg_file)
        timeline.append({"cell": cell["id"], "file": f,
                         "content": _content_hash(f),
                         "start": cell_start + i * SEG,
                         "end": cell_start + i * SEG + seg_dur})
        # content nay vua dung -> khong dung lai o segment ke tiep cua video
        h = _content_hash(f)
        if h:
            used_at.setdefault(h, cell_start + i * SEG + seg_dur)
    # concat cac segment — dung concat FILTER (re-encode) de PTS dung;
    # concat demuxer -c copy cho PTS sai khi segment co B-frames -> video bi
    # cat cum, giam thoi luong that (khong khop VO).
    inputs = []
    fmap = ""
    for i, sf in enumerate(seg_files):
        inputs += ["-i", os.path.abspath(sf)]
        fmap += f"[{i}:v]"
    if len(seg_files) == 1:
        emit(["ffmpeg", "-y", "-v", "error", "-i", os.path.abspath(seg_files[0]),
              "-c", "copy", os.path.join(root, out)], root)
        return dur
    fmd = f"{fmap}concat=n={len(seg_files)}:v=1:a=0[out]"
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fmd,
           "-map", "[out]", "-c:v", "libx264", "-crf", "18", "-preset", "fast",
           "-pix_fmt", "yuv420p", "-an", os.path.join(root, out)]
    emit(cmd, root)
    return dur


def _render_stock_segment(src, offset, seg_dur, reframe, clip_cell, f_reg, f_bold,
                          root, out):
    """Render 1 doan stock (mute) tu offset -> offset+seg_dur."""
    scale = f"[0:v]"
    if reframe:
        scale += reframe + ","
    scale += (f"scale=1920:1080:force_original_aspect_ratio=decrease,"
              f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x14110F,"
              f"setsar=1,format=yuv420p,fps={FPS}")
    scale += _cinema(clip_cell)
    fc = _attribution_filter(root, clip_cell, f_reg, f_bold,
                             label_in=scale, label_out="[v]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1",
           "-ss", f"{offset:.2f}", "-i", src,
           "-filter_complex", fc,
           "-map", "[v]", "-c:v", "libx264", "-crf", "16",
           "-t", f"{seg_dur:.2f}", os.path.join(root, out)]
    emit(cmd, root)


def render_cell(cfg, cell, root, prev_shot=None, stock_idx=0, stock_avail=None,
                src_override=None, segment_pool=None, timeline=None, cell_start=0.0):
    cid = cell["id"]
    out = os.path.join("build", "shots", f"cell-{cid}.mp4")
    os.makedirs(os.path.join(root, "build", "shots"), exist_ok=True)
    t = cell["type"]
    style = cfg.get("style", {})
    if t == "outro":
        return render_outro(cell, style, out, root)
    if t in ("card", "quote"):
        return render_pil(cell, style, out, root)
    if t in ("clip", "clip-mute"):
        return render_clip(cell, out, root, style)
    if t == "stock":
        return render_stock(cell, out, root, style, stock_idx, stock_avail,
                            src_override, segment_pool, timeline, cell_start)
    if t == "black":
        return render_black(cell, out, root)
    if t == "sfx":
        return render_sfx(cell, out, root)
    if t == "hold":
        if not prev_shot:
            raise SystemExit(f"cell {cid}: hold nhung khong co shot truoc")
        dur = cell.get("dur", 4.0)
        return render_hold(prev_shot, out, root, dur)
    raise SystemExit(f"cell {cid}: type khong ho tro {t}")


def _build_global_pool(root, stock_avail):
    """Pool chung toan video: gop TAT CA file stock trong assets/stock (791 content
    unique), dedup theo CONTENT hash. Uu tien file thuoc keyword/theme co trong
    config truoc, roi mo rong ra toan bo kho — de khong can kiet khi video dai."""
    from stock import _content_hash, theme_keywords, _stock_dir
    seen_c, pool = set(), []
    # uu tien: file thuoc theme cua keyword trong config (giu visual lien mach)
    order = []
    for tk in sorted({tk for k in stock_avail for tk in theme_keywords(k)}):
        order.append(tk)
    # them cac keyword khac trong kho (de phong phu)
    import stock as _st
    for grp in _st.STOCK_THEMES:
        for kw in grp:
            if kw not in order:
                order.append(kw)
    import os as _os
    d = _stock_dir(root)
    if not _os.path.isdir(d):
        return pool
    by_kw = {}
    for kw in order:
        for idx in range(12):
            for api in ("pixabay", "pexels"):
                import hashlib
                h = hashlib.md5(f"{api}|{kw}|{idx}".encode()).hexdigest()[:12]
                f = _os.path.join(d, h + ".mp4")
                if _os.path.exists(f):
                    by_kw.setdefault(kw, []).append(f)
    for kw in order:
        for f in by_kw.get(kw, []):
            h = _content_hash(f)
            if h and h in seen_c:
                continue
            if h:
                seen_c.add(h)
            pool.append(f)
    return pool


def _pick_cell_file(global_pool, avail, timeline, now, kw):
    """Chon file cho 1 cell stock bat dau tai thoi diem `now`. Uu tien:
    1) content CHUA dung bao gio trong avail (theme khop).
    2) content CHUA dung trong global_pool (bat ky theme) — tranh tai dung.
    3) het toan bo -> content dung lau nhat (fallback).
    Tra ve (file, content_hash) hoac (None, None)."""
    from stock import _content_hash
    if not avail and not global_pool:
        return None, None
    used_at = {}
    for rec in timeline:
        h = rec.get("content")
        if h:
            used_at.setdefault(h, rec.get("end", 0))
    fresh = [f for f in (avail or []) if _content_hash(f)
             and _content_hash(f) not in used_at]
    if fresh:
        f = fresh[0]
        return f, _content_hash(f)
    # avail (theme) het fresh -> tim fresh trong global pool (moi theme)
    gfresh = [f for f in (global_pool or []) if _content_hash(f)
              and _content_hash(f) not in used_at]
    if gfresh:
        f = gfresh[0]
        return f, _content_hash(f)
    # that su can kiet -> content dung lau nhat (gan day nhat)
    best = None
    for f in (avail or []) + (global_pool or []):
        h = _content_hash(f)
        if not h:
            continue
        last = used_at.get(h, -1e9)
        if best is None or last < best[0]:
            best = (last, f)
    if best:
        return best[1], _content_hash(best[1])
    return None, None


def render_all(cfg, root, only=None):
    import json
    from probe import duration as _dur
    n = 0
    prev_shot = None
    dur_map = {}
    state_path = os.path.join(root, "build", "stock-state.json")
    state = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
    stock_seen = state.get("stock_seen", {})  # keyword -> so lan da render
    stock_avail = {}  # keyword -> list file stock (tu keyword + cung theme)
    # timeline: [{cell, file, content, start, end}] — nhung gi da dung + luc nao
    timeline = list(state.get("stock_timeline", []))
    # pool chung TOAN VIDEO: gop pool cua MOI keyword trong cfg (khong chi keyword
    # gap truoc) de dedup content xuyen cell. Build 1 lan tu dau.
    from stock import stock_pool
    global_pool = None
    for cell in cfg["cells"]:
        if cell.get("type") != "stock":
            continue
        k = cell.get("stock") or cell.get("keyword") or ""
        if not k or k in stock_avail:
            continue
        stock_avail[k] = stock_pool(root, k)
    if stock_avail:
        global_pool = _build_global_pool(root, stock_avail)
    chosen = None
    t_cursor = 0.0  # thoi diem bat dau cell hien tai trong video
    for cell in cfg["cells"]:
        if only and int(cell["id"]) not in only:
            continue
        out_path = os.path.join(root, "build", "shots", f"cell-{cell['id']}.mp4")
        if os.path.exists(out_path) and not only:
            prev_shot = out_path
            t_cursor += _dur(out_path)
            n += 1
            continue
        stock_idx = 0
        if cell.get("type") == "stock":
            from stock import _content_hash
            kw = cell.get("stock") or cell.get("keyword") or ""
            avail = stock_avail.get(kw)
            if avail:
                stock_seen[kw] = stock_seen.get(kw, 0) + 1
                # re-render: bo record cu cua cell nay, ghi lai moi
                timeline = [r for r in timeline if r.get("cell") != cell["id"]]
                chosen, ch = _pick_cell_file(global_pool, avail, timeline,
                                             t_cursor, kw)
                if chosen in avail:
                    stock_idx = avail.index(chosen)
        prev_shot = render_cell(cfg, cell, root, prev_shot, stock_idx,
                                stock_avail.get(cell.get("stock") or cell.get("keyword") or ""),
                                chosen if cell.get("type") == "stock" else None,
                                global_pool, timeline, t_cursor)
        dur_map[cell["id"]] = prev_shot
        # render_cell tra ve DURATION (float) cua cell -> t_cursor tien len
        if isinstance(prev_shot, (int, float)):
            t_cursor += prev_shot
        n += 1
    if _sh:
        sh, cnt = run_sh(root)
        print(f"emit {cnt} lenh filter -> {sh}")
        bash = r"C:\Program Files\Git\bin\bash.exe"
        r = subprocess.run([bash, "-lc", f'source "{sh.replace(os.sep, "/")}"'],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-1200:])
            print(r.stderr[-1200:])
            raise SystemExit(f"render filter loi rc={r.returncode}")
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "ok")
    # save state: keyword seen + timeline (file/content + thoi diem da dung)
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"stock_seen": stock_seen,
                       "stock_timeline": timeline},
                      f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return n, dur_map
