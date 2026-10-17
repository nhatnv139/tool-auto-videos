"""
assemble.py — Ghep video tu config.json, chia 4 giai doan.

  Stage 1 (trim):   moi lo 8 cell -> build/trim/batch-<n>.mp4 (+ .sig), cac lo
                    encode SONG SONG (cat dung cell_dur, burn caption, dong
                    last frame neu shot ngan). Lo co chu ky khop -> dung lai.
  Stage 2 (concat): chi ghi build/trim/list.txt (khong con video.mp4 day du)
  Stage 3 (audio):  mix VO + clip audio + SFX + nhac duck -> audio_raw.flac
  Stage 4 (mux):    concat lo (-c copy) + audio, loudnorm MOT LAN -> out

Giai thich nhac: moi cell khai music (in/out/drop/swell). Voi test dau,
nhac = bed duy nhat, duck theo VO+clip audio (sidechaincompress). Cell
"out"/"drop" = nhac ngung (chen silence) — "nhac dung" cho beat.

Caption: burn o Stage 1 (can biet vo_dur). Text = cell['cap'], hien 0.3s
sau khi cell bat dau, o gan day man hinh. Clip talking-head (co tieng goc)
khong burn caption — chi attribution da co o render.

ffmpeg filter phuc tap chay qua git-bash (may nay segfault khi subprocess
spawn filter) — emit .sh va chay source.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import duration, streams  # noqa: E402
import config as CFG  # noqa: E402

GIT_BASH = os.environ.get("GIT_BASH") or r"C:\Program Files\Git\bin\bash.exe"
KIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AR = 48000
CAP_FADE = 0.3


# ---------------------------------------------------------------- plan
def plan(root, cfg, strict=True):
    rows = []
    cursor = 0.0
    missing = []
    fps = cfg.get("fps", 24)
    for cell in cfg["cells"]:
        cid = cell["id"]
        shot = os.path.join(root, "build", "shots", f"cell-{cid}.mp4")
        if not os.path.exists(shot):
            if strict:
                raise SystemExit(f"cell {cid}: thieu shot {shot}. Chay render truoc.")
            shot_dur = cell.get("dur") or 5.0
        else:
            shot_dur = duration(shot)
        vo_path, vo_dur = None, 0.0
        if cell.get("vo"):
            vo_path = os.path.join(root, "build", "voice", f"cell-{cid}.mp3")
            if not os.path.exists(vo_path):
                if strict:
                    raise SystemExit(f"cell {cid} co vo nhung thieu {vo_path}. Chay tts.")
                missing.append(cid)
            else:
                vo_dur = duration(vo_path)
        pause = cell.get("pause_after", 0.0)
        if cell.get("vo") and vo_dur > 0:
            cell_dur = vo_dur + pause
        elif cell.get("type") == "sfx" and os.path.exists(shot):
            # sfx: dung do dai audio that (whoosh dai hon dur khai bao)
            cell_dur = max(cell.get("dur") or shot_dur, shot_dur)
        else:
            # pause_after phai ap cho CA cell im lang (card/quote) — day chinh la
            # nhip "let it land" sau mot reveal; truoc day bi bo qua.
            cell_dur = (cell.get("dur", shot_dur) or shot_dur) + pause
        if cell_dur <= 0:
            cell_dur = shot_dur
        # Lam tron ve luoi frame TRUOC khi cong don: stage1 cat theo bien frame
        # nhung timeline audio tinh bang so thuc -> moi cell lech ~0.04s, video
        # 100 cell lech toi ~4s giua tieng va hinh.
        cell_dur = round(cell_dur * fps) / fps
        has_audio = bool(os.path.exists(shot) and streams(shot).get("audio"))
        rows.append({
            "cell": cell, "start": round(cursor, 3), "dur": round(cell_dur, 3),
            "shot_dur": round(shot_dur, 3), "shot": shot,
            "vo": vo_path, "vo_dur": round(vo_dur, 3), "audio": has_audio,
        })
        cursor += cell_dur
    return rows, round(cursor, 3), missing


# ---------------------------------------------------------------- stage 1
# Subtitle: ASS per-segment, instant show, 1-2 dong, sanitize ky tu khong font
# 42 ky tu o 56px bold ~ 1300px, con thua trong khung 1920. Ha xuong 34 lam
# menh de bi be doi giua chung ("machine," bat dau mot doan moi).
CAP_MAX_CHARS = 42
CAP_MIN_CHARS = 12


def _sanitize_sub(text):
    """Bo ky tu khong co trong font (tofu) + chuan hoa dau."""
    repl = {
        "→": "->", "←": "<-", "…": "...", "’": "'", "‘": "'",
        "“": '"', "”": '"', "–": "-", "—": " - ", "·": "",
    }
    for k, v in repl.items():
        text = text.replace(k, v)
    return " ".join(text.split())


def _split_segments(text, max_chars=CAP_MAX_CHARS, min_chars=CAP_MIN_CHARS):
    """Tach caption thanh cac doan ngoan (1-2 dong), instant sub."""
    import re
    text = _sanitize_sub(text)
    if not text.split():
        return []
    # Cat theo CAU truoc, roi trong moi cau uu tien cat o dau phay/cham phay —
    # ban cu chi cat tham theo so ky tu (du comment noi la cat theo cau) nen
    # ranh gioi cau roi vao giua doan, dau phay bi ket cuoi dong.
    segs = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= max_chars:
            segs.append(sent)
            continue
        cur = ""
        for chunk in re.split(r"(?<=[,;:])\s+", sent):
            for w in chunk.split():
                test = (cur + " " + w).strip()
                if len(test) <= max_chars:
                    cur = test
                else:
                    if cur:
                        segs.append(cur)
                    cur = w
            # het mot menh de: xuong doan moi neu doan hien tai da kha day
            if cur and len(cur) >= max_chars * 0.6:
                segs.append(cur)
                cur = ""
        if cur:
            segs.append(cur)
    # gop doan qua ngan vao doan truoc — nhung khong duoc vuot max_chars
    merged = []
    for s in segs:
        if (merged and len(s) < min_chars
                and len(merged[-1]) + 1 + len(s) <= max_chars):
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged


def _ts_ass(sec):
    """MM:SS.CC cho ASS."""
    sec = max(0.0, sec)
    ms = int(round(sec * 100))
    m, rem = divmod(ms, 6000)
    s, cs = divmod(rem, 100)
    return f"{m}:{s:02d}.{cs:02d}"


def _build_ass(root, cell, vo_dur, start=0.0):
    """Sinh file .ass subtitle cho cell co VO, instant, theo doan cau.

    Moi cell duoc trim rieng (stage1) nen ASS dung moc LOCAL cua cell
    (0..vo_dur). Tra ve path .ass (hoac None neu cell khong co cap/vo).
    """
    # Boc ky tu ngat nghi ('//', '|', '^', '*') truoc khi ve: chung la lenh nhip
    # cho TTS, khong phai chu — de lot vao day thi chung hien tren man hinh.
    from tts import strip_marks
    cap = strip_marks(cell.get("cap") or cell.get("vo") or "")
    if not cap or not vo_dur:
        return None
    segs = _split_segments(cap)
    if not segs:
        return None
    total_words = sum(len(s.split()) for s in segs)
    if total_words <= 0:
        return None
    tdir = os.path.join(root, "build", "trim")
    os.makedirs(tdir, exist_ok=True)
    # doi tuong toan bo ca video, khong phai per-cell: build cac dong voi
    # offset bat dau tu start cua cell (tinh bang giay video tong)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,46,&H00FFFFFF,&H000000FF,&H00000000,&H8C000000,"
        "-1,0,0,0,100,100,0,0,1,2,1,2,80,80,60,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    used = 0.0
    for s in segs:
        n_words = len(s.split())
        t0 = start + (used / total_words) * vo_dur
        used += n_words
        t1 = start + (used / total_words) * vo_dur
        t1 = max(t1, t0 + 0.4)
        if t1 > start + vo_dur:
            t1 = start + vo_dur
        lines.append(f"Dialogue: 0,{_ts_ass(t0)},{_ts_ass(t1)},Default,,0,0,0,,{s}")
    ass_path = os.path.join(tdir, f"cap-{cell['id']}.ass")
    with open(ass_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return ass_path


def _caption_filter(root, cell, f_bold, vo_dur, fps, cell_start=0.0):
    """Tra ve (filter_string, None) — drawtext per-segment instant.

    Moi doan cau (segment) ve bang 1 drawtext + textfile, hien INSTANTLY
    trong [t0,t1] (khong fade). Moc tinh tu 0 (local cua cell).
    """
    if not cell.get("vo") or not cell.get("cap"):
        return "", None
    from tts import strip_marks
    segs = _split_segments(strip_marks(cell["cap"]))
    if not segs or not vo_dur:
        return "", None
    marks = _word_marks(root, cell["id"])
    total_words = sum(len(s.split()) for s in segs)
    fpath = _ensure_font_bold(root)  # relative path, khong co drive colon
    parts = []
    used = 0
    for i, s in enumerate(segs):
        n_words = len(s.split())
        if marks and len(marks) >= total_words:
            # Moc tu THAT tu edge-tts (WordBoundary). Chia deu theo so tu se lech
            # 200-400ms, va lech nang hon nua khi VO co khoang lang giua cac cau.
            t0 = marks[min(used, len(marks) - 1)]["t"]
            j = min(used + n_words, len(marks) - 1)
            t1 = (marks[j]["t"] if used + n_words < len(marks)
                  else marks[-1]["t"] + marks[-1]["d"])
        else:
            t0 = (used / total_words) * vo_dur
            t1 = ((used + n_words) / total_words) * vo_dur
        used += n_words
        t1 = min(max(t1, t0 + 0.4), vo_dur)
        tf = _textfile(root, s, f"seg{cell['id']}_{i}")
        tf_rel = os.path.relpath(tf, root).replace("\\", "/")
        y = cell.get("cap_y", "h-260")
        parts.append(
            f"drawtext=fontfile={fpath}:textfile={tf_rel}:fontsize=56:"
            f"fontcolor=white:x=(w-text_w)/2:y={y}:"
            f"box=1:boxcolor=black@0.55:boxborderw=22:"
            f"borderw=4:bordercolor=black@0.9:"
            f"shadowcolor=black@0.9:shadowx=0:shadowy=3:"
            f"enable='between(t\\,{t0:.2f}\\,{t1:.2f})'")
    if not parts:
        return "", None
    return ",".join(parts), None


def _word_marks(root, cell_id):
    """Doc moc thoi gian tung tu do tts ghi ra (build/voice/cell-N.words.json)."""
    p = os.path.join(root, "build", "voice", f"cell-{cell_id}.words.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("words") or None
    except Exception:
        return None


def _ensure_font_bold(root):
    """Copy arialbd.ttf vao build/tmp, tra ve path tuong doi (no drive colon)."""
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    dst = os.path.join(tdir, "arialbd.ttf")
    if not os.path.exists(dst):
        import shutil
        shutil.copy(os.path.join(KIT_ROOT, "tool", "fonts", "arialbd.ttf"), dst)
    return os.path.relpath(dst, root).replace("\\", "/")


def _textfile(root, text, tag):
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    p = os.path.join(tdir, f"{tag}.txt")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


def _ensure_stage1_fonts(root):
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    src_dir = os.path.join(KIT_ROOT, "tool", "fonts")
    for fn in ("arial.ttf", "arialbd.ttf"):
        d = os.path.join(tdir, fn)
        if not os.path.exists(d) and os.path.exists(os.path.join(src_dir, fn)):
            import shutil
            shutil.copy(os.path.join(src_dir, fn), d)


# So cell moi lan encode. Moi input mo them ~250-300 MB (giai ma + bo dem), lo 8
# cell an ~2,6 GB. May 16 GB dang mo Chrome thi Claude Code tung tat runner o
# buoc nay vi het RAM (03/10/2026, hai lan). STAGE1_BATCH=4 -> ~1,3 GB/lo.
BATCH = int(os.environ.get("STAGE1_BATCH", "8"))


def batch_size(n_rows):
    """Video ngan thi chia lo nho hon de du lo chay song song: 15 cell / 8 = 2
    lo -> lo dau (164s video) la duong gang, may ranh mot nua thoi gian. Chi
    phu thuoc so cell (khong theo RAM luc chay) de chu ky lo on dinh khi resume.
    """
    return max(3, min(BATCH, -(-n_rows // 6)))


# ---------------------------------------------------------------- chuyen canh
# 16/10/2026 — config.json co cfg["dung"] (script2config --chuong cat /
# --chuyen-canh nhe). Khong co khoa nay -> ap_chuyen_canh khong gan gi, stage1
# chay dung duong cu (cat thang, lo chia nhu cu, chu ky lo khong doi).
#
# Nguoi xem phan nan "chuyen canh, sao chuyen lai chuong 1 chuong 2": video cu
# cat thang moi cell + 2,5s man den o moi chuong. Nay:
#   chuong     flash trang 0,5s (xfade fadewhite) + whoosh + tieng dong tram,
#              tieu de chuong nho tren hinh moi, nhac day len (assemble env)
#   chuyen y   cell truoc ket bang /// -> crossfade 0,4s hoac dip den 0,5s xen ke
#   cat thuong cu >= 3 lan cat thang thi mot lan crossfade / whip (hblur) /
#              zoomin; cac cat thang con lai: cu 2 lan thi 1 lan "punch-in"
#              (cell moi vao o zoom 1,06 roi lui ve 1,0 trong 10 frame)
# Moi chuyen canh deu la xfade TRONG mot lo: cell truoc keo dai them N frame duoi
# cell sau, offset = moc bat dau cell sau -> timeline tieng/phu de khong doi.
TR_CHUONG = {"kieu": "fadewhite", "frames": 12,
             "sfx": [("whoosh", -0.55, 0.30), ("cinematic-hit", 0.10, 0.20)]}
TR_Y = [{"kieu": "fade", "frames": 10, "sfx": []},
        {"kieu": "fadeblack", "frames": 12, "sfx": []}]
TR_THUONG = [{"kieu": "fade", "frames": 8, "sfx": []},
             {"kieu": "hblur", "frames": 7, "sfx": [("swoosh", -0.18, 0.12)]},
             {"kieu": "zoomin", "frames": 9, "sfx": []}]
PUNCH_FRAMES = 10
PUNCH_ZOOM = 1.06


def _dung(cfg):
    return (cfg or {}).get("dung") or {}


def ap_chuyen_canh(rows, cfg, root=None):
    """Gan r["tr"] (chuyen canh VAO row) + r["punch"] + sfx cho cell. Tra ve so
    chuyen canh. Khong co cfg["dung"] -> khong lam gi (hanh vi cu)."""
    d = _dung(cfg)
    chuong = d.get("chuong") == "cat"
    mode = d.get("chuyen_canh") or ""
    if not chuong and not mode:
        return 0
    n_tr, n_cut, i_y, i_th, n_punch = 0, 0, 0, 0, 0
    names = set()
    for k, r in enumerate(rows):
        r.pop("tr", None)
        r.pop("punch", None)
        if k == 0:
            continue
        prev = rows[k - 1]
        c, pc = r["cell"], prev["cell"]
        tr = None
        ngan = r["dur"] < 1.6 or prev["dur"] < 1.6
        if chuong and c.get("chuong"):
            tr = dict(TR_CHUONG)
        elif mode and not ngan and c.get("type") != "clip" and pc.get("type") != "clip":
            vo_prev = (pc.get("vo") or "").rstrip()
            if vo_prev.endswith("///"):
                tr = dict(TR_Y[i_y % len(TR_Y)])
                i_y += 1
            elif n_cut >= 1:
                # ranh gioi cell xen ke: chuyen canh / cat thang (+ punch). Cat
                # BEN TRONG cell (doan stock 6-7,5s) van la cat thang -> tong
                # cong ~1/3 so lan cat la chuyen canh mem.
                tr = dict(TR_THUONG[i_th % len(TR_THUONG)])
                i_th += 1
        if tr:
            r["tr"] = tr
            n_tr, n_cut = n_tr + 1, 0
            for name, _at, _v in tr["sfx"]:
                names.add(name)
        else:
            n_cut += 1
            if mode and r["dur"] >= 2.0:
                r["punch"] = True
                n_punch += 1
    # sfx: tai mot lan vao assets/sfx cua case, gan vao cell (sfx_list)
    if names and root:
        try:
            from sfx import fetch_sfx, sfx_file
            thieu = [n for n in names if not sfx_file(root, n)]
            if thieu:
                fetch_sfx(root, names=thieu)
        except Exception as e:      # mang hong -> van dung video, chi mat sfx
            print(f"  WARN khong tai duoc sfx chuyen canh: {e}")
    for r in rows:
        tr = r.get("tr")
        r["cell"].pop("sfx_list", None)
        if not tr or not tr["sfx"]:
            continue
        r["cell"]["sfx_list"] = [{"name": n, "at": at, "vol": vol}
                                 for n, at, vol in tr["sfx"]]
    if n_tr or n_punch:
        n_ch = sum(1 for r in rows if (r.get("tr") or {}).get("kieu") == "fadewhite")
        print(f"  chuyen canh: {n_tr} xfade ({n_ch} chuong), {n_punch} punch-in, "
              f"con lai cat thang")
    return n_tr


def _batches(rows):
    """Chia lo. Khong co chuyen canh -> y nhu cu (_chunked theo batch_size).
    Co -> khong de diem chuyen canh roi dung ranh gioi hai lo (lo noi bang -c
    copy nen o do chi cat thang duoc): keo lo dai them toi da 4 cell, van trung
    thi bo chuyen canh do."""
    bs = batch_size(len(rows))
    if not any(r.get("tr") for r in rows):
        return list(_chunked(rows, bs))
    out, i, n = [], 0, len(rows)
    while i < n:
        j = min(n, i + bs)
        ext = 0
        while j < n and rows[j].get("tr") and ext < 4:
            j += 1
            ext += 1
        if j < n and rows[j].get("tr"):
            rows[j].pop("tr", None)
            rows[j]["cell"].pop("sfx_list", None)
        out.append(rows[i:j])
        i = j
    return out


def _tieu_de_chuong(root, cell, fps):
    """drawtext tieu de chuong: nho, thanh, 0,4s -> 3,45s, mo dan vao/ra."""
    meta = cell.get("chuong") or {}
    if not meta:
        return ""
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    import shutil
    font = None
    for cand in (r"C:\Windows\Fonts\palab.ttf", r"C:\Windows\Fonts\georgiab.ttf"):
        if os.path.exists(cand):
            font = os.path.join(tdir, os.path.basename(cand))
            if not os.path.exists(font):
                shutil.copy(cand, font)
            break
    if not font:
        font = os.path.join(tdir, "arialbd.ttf")
    frel = os.path.relpath(font, root).replace("\\", "/")
    t_in, t_full, t_out, t_end = 0.40, 0.85, 3.0, 3.45
    alpha = (f"if(lt(t\\,{t_in})\\,0\\,if(lt(t\\,{t_full})\\,(t-{t_in})/{t_full - t_in:.2f}"
             f"\\,if(lt(t\\,{t_out})\\,1\\,if(lt(t\\,{t_end})\\,({t_end}-t)/{t_end - t_out:.2f}"
             f"\\,0))))")
    so = str(meta.get("so") or "").upper()
    label = f"PHẦN {so}" if so else ""
    title = _sanitize_sub(meta.get("tieu_de") or "")
    lines, cur = [], ""
    for w in title.split():
        if len(cur) + 1 + len(w) > 34 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    parts = []
    y = 96
    common = (f"alpha='{alpha}':enable='between(t\\,{t_in}\\,{t_end})'")
    if label:
        tf = _textfile(root, label, f"chuong{cell['id']}_lb")
        parts.append(
            f"drawtext=fontfile={frel}:textfile="
            f"{os.path.relpath(tf, root).replace(os.sep, '/')}:"
            f"fontsize=30:fontcolor=0xE0A82E:x=(w-text_w)/2:y={y}:"
            f"borderw=2:bordercolor=black@0.7:shadowcolor=black@0.8:shadowx=0:"
            f"shadowy=2:{common}")
        y += 48
    for i, ln in enumerate(lines):
        tf = _textfile(root, ln, f"chuong{cell['id']}_t{i}")
        parts.append(
            f"drawtext=fontfile={frel}:textfile="
            f"{os.path.relpath(tf, root).replace(os.sep, '/')}:"
            f"fontsize=54:fontcolor=white:x=(w-text_w)/2:y={y}:"
            f"borderw=3:bordercolor=black@0.75:shadowcolor=black@0.85:shadowx=0:"
            f"shadowy=3:{common}")
        y += 66
    return ",".join(parts)


def _punch_chain(cid, fps):
    """Punch-in: PUNCH_FRAMES frame dau o zoom 1,06 lui ve 1,0 (tach dau cell,
    zoompan, noi lai). Tra ve doan filter co nhan noi bo, chen giua chuoi."""
    n = PUNCH_FRAMES
    z = PUNCH_ZOOM
    step = (z - 1.0) / n
    return (f"split=2[pa{cid}][pb{cid}];"
            f"[pa{cid}]trim=end_frame={n},setpts=PTS-STARTPTS,"
            f"zoompan=z='max(1\\,{z}-{step:.5f}*on)':d=1:x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':s=1920x1080:fps={fps},setsar=1,format=yuv420p"
            f"[pc{cid}];"
            f"[pb{cid}]trim=start_frame={n},setpts=PTS-STARTPTS[pd{cid}];"
            f"[pc{cid}][pd{cid}]concat=n=2:v=1:a=0")


def _cell_chain(r, root, fps, rows, idx, tail_frames=0, no_dip=False):
    """Chuoi filter cho 1 cell trong filtergraph gop: pad/trim/scale/caption/fade.

    tail_frames > 0 (crossfade): cell keo dai them chung ay frame o CUOI — phan
    du nay nam duoi cell sau trong luc xfade, nen timeline (tieng/phu de) khong
    lech. no_dip: bo dip-to-black o beat music=drop (kenh khong muon man den).
    """
    dur = r["dur"]
    n_frames = int(round(dur * fps)) + int(tail_frames)
    vf = []
    need_pad = max(0.0, n_frames / fps - r["shot_dur"])
    if need_pad > 0.01:
        vf.append(f"tpad=stop_mode=clone:stop_duration={need_pad + 0.2:.3f}")
    vf.append("setpts=PTS-STARTPTS")
    # Cat theo SO FRAME, khong theo thoi gian: trim=duration so sanh PTS dau
    # phay dong nen moi cell rung mat dung 1 frame (video 6 cell ngan hon
    # timeline audio 0.25s, va sai so nay cong don theo do dai video).
    vf.append(f"fps={fps}")
    vf.append(f"trim=end_frame={n_frames}")
    vf.append("setpts=PTS-STARTPTS")
    # KHONG dat them fps= o day. fps thu hai (sau trim + scale) lam roi dung
    # MOT frame cuoi moi cell — do 01/10/2026: trim=end_frame=137 ra 136 frame;
    # lo 8 cell cua Can Long ngan hon ke hoach dung 8 frame, ca video 186 cell
    # hinh hut 7,75s so voi tieng (phu de chay truoc giong ~1 frame moi cell,
    # cuoi video -shortest cat mat duoi tieng). fps da chuan hoa truoc trim.
    vf.append("scale=1920:1080:force_original_aspect_ratio=decrease,"
              "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x14110F,setsar=1,"
              "format=yuv420p")
    if r.get("punch") and n_frames > PUNCH_FRAMES + 4:
        vf.append(_punch_chain(r["cell"]["id"], fps))
    cap, _ = _caption_filter(root, r["cell"], None, r["vo_dur"], fps)
    if cap:
        vf.append(cap)
    if r["cell"].get("chuong"):
        td = _tieu_de_chuong(root, r["cell"], fps)
        if td:
            vf.append(td)
    # CAT THANG giua cac cell. Truoc day moi cell fade ra den 0.2s roi cell sau
    # fade tu den 0.2s -> moi diem cat la 0.4s man hinh toi (video 6 cell/34s co
    # 2.4s bi am). Dung phim that cat thang; chi dip-to-black o beat co chu dinh
    # (music=drop) va o dau/cuoi video.
    first, last = idx == 0, idx == len(rows) - 1
    fi = 0.6 if first else 0.0
    fo = 0.8 if last else 0.0
    if (r["cell"].get("music") == "drop" and r["cell"].get("fx") != "flash"
            and not no_dip):
        fi, fo = max(fi, 0.35), max(fo, 0.35)
    if r["cell"].get("fx") == "flash":
        fi = 0.0
        vf.append("fade=t=in:st=0:d=0.15:color=white")
    if dur > (fi + fo + 0.2):
        if fi > 0:
            vf.append(f"fade=t=in:st=0:d={fi}")
        if fo > 0:
            vf.append(f"fade=t=out:st={dur - fo:.3f}:d={fo}")
    if tail_frames or no_dip or r.get("_xf_lo"):
        # xfade can link co frame rate CO DINH; sau trim/setpts link mat frame
        # rate (1/0) va xfade tu choi. Dat PTS = so thu tu frame roi fps= :
        # PTS da nam dung luoi nen fps khong roi/nhan doi frame nao.
        vf.append(f"setpts=N/({fps}*TB),fps={fps}")
    return ",".join(vf)


# Crossfade giua cac cell (kenh bat co kieu_the: long). 8 frame @24fps = 0,33s.
# Cell truoc keo dai 8 frame duoi cell sau; xfade bat dau DUNG luc cell sau bat
# dau tren timeline -> tong do dai lo khong doi, tieng/phu de khong lech. Giua
# hai LO (moi lo ~8 cell) van la cat thang vi cac lo noi bang -c copy.
XFADE_FRAMES = int(os.environ.get("XFADE_FRAMES", "8"))


def stage1_trim(rows, root, fps, xfade=False):
    """Trim + caption + noi — GOP THANH MOT LAN ENCODE cho moi lo cell.

    Truoc day moi cell duoc encode rieng (stage1) roi ca video encode lai lan
    nua de noi (stage2): moi frame qua 2 the he sau khi da qua 1 the he o
    render. Nay mot lo = mot filtergraph = mot lan encode; noi cac lo bang
    concat demuxer -c copy (stage2) nen khong con the he thu hai.
    """
    tdir = os.path.join(root, "build", "trim")
    os.makedirs(tdir, exist_ok=True)
    _ensure_stage1_fonts(root)
    cmds = []
    n_skip = 0
    batches = _batches(rows)
    pos = 0
    for b, batch in enumerate(batches):
        ins, chains, labels = [], [], ""
        xf = XFADE_FRAMES if (xfade and len(batch) > 1) else 0
        # chuyen canh co chu dich (ap_chuyen_canh): xfade o MOT SO ranh gioi,
        # con lai noi thang bang concat 2 dau vao. Ranh gioi dau lo luon cat thang.
        mixed = (not xf) and any(r.get("tr") for r in batch[1:])
        for k, r in enumerate(batch):
            ins += ["-i", r["shot"]]
            if mixed:
                nxt = batch[k + 1] if k < len(batch) - 1 else None
                tail = (nxt["tr"]["frames"] if nxt is not None and nxt.get("tr") else 0)
                r["_xf_lo"] = True
            else:
                tail = xf if k < len(batch) - 1 else 0
            chains.append(f"[{k}:v]"
                          + _cell_chain(r, root, fps, rows, pos + k,
                                        tail_frames=tail, no_dip=bool(xfade))
                          + f"[c{k}]")
            labels += f"[c{k}]"
            r.pop("_xf_lo", None)
        pos += len(batch)
        if mixed:
            prev, cum = "c0", int(round(batch[0]["dur"] * fps))
            for k in range(1, len(batch)):
                lab = "v" if k == len(batch) - 1 else f"x{k}"
                tr = batch[k].get("tr")
                if tr:
                    chains.append(f"[{prev}][c{k}]xfade=transition={tr['kieu']}:"
                                  f"duration={tr['frames'] / fps:.6f}:"
                                  f"offset={cum / fps:.6f}[{lab}]")
                else:
                    # concat ra timebase 1/1000000; xfade sau do doi hai dau vao
                    # cung timebase -> dua ve 1/fps, PTS = so thu tu frame.
                    chains.append(f"[{prev}][c{k}]concat=n=2:v=1:a=0,"
                                  f"settb=1/{fps},setpts=N/({fps}*TB),fps={fps}[{lab}]")
                prev = lab
                cum += int(round(batch[k]["dur"] * fps))
        elif xf:
            # offset = moc bat dau cell k trong lo (tinh bang frame cho chinh xac)
            prev, cum = "c0", int(round(batch[0]["dur"] * fps))
            for k in range(1, len(batch)):
                lab = "v" if k == len(batch) - 1 else f"x{k}"
                chains.append(f"[{prev}][c{k}]xfade=transition=fade:"
                              f"duration={xf / fps:.6f}:offset={cum / fps:.6f}"
                              f"[{lab}]")
                prev = lab
                cum += int(round(batch[k]["dur"] * fps))
        else:
            chains.append(f"{labels}concat=n={len(batch)}:v=1:a=0[v]")
        out = os.path.join(tdir, f"batch-{b}.mp4")
        cmd = ["ffmpeg", "-y", "-v", "error", *ins,
               "-filter_complex", ";".join(chains), "-map", "[v]",
               *final_venc(fps),
               "-colorspace", "bt709", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-an", out]
        sig = _batch_sig(root, batch, cmd)
        # Lo da encode xong thi bo qua — mot video 22 phut mat ~25 phut o
        # stage1, dut giua chung (het dia, bi kill) khong phai lam lai tu lo 0.
        # Ban cu chi xet "doc duoc va dai > 0" nen doi config/giong xong chay
        # lai van an nham lo CU (phu de, do dai cell sai). Nay lo phai kem chu ky
        # (hash lenh ffmpeg + kich thuoc/mtime shot + noi dung phu de) khop moi
        # duoc dung lai. Chu ky chi ghi SAU khi ffmpeg xong, nen file cut do bi
        # kill khong bao gio co chu ky.
        if _batch_ok(out, sig, sum(r["dur"] for r in batch)):
            n_skip += 1
            continue
        for p in (out, out + ".sig"):
            try:
                os.remove(p)
            except OSError:
                pass
        cmds.append(["sig1", sig, out, *cmd])
    if n_skip:
        print(f"  dung lai {n_skip} lo da encode (chu ky khop)")
    _emit(root, "run_stage1.sh", cmds, jobs=stage1_jobs())
    return tdir


# Encode cuoi (lan duy nhat nguoi xem thay). Ban cu libx264 CRF 16 preset slow,
# maxrate 20M. Do 01/10/2026 tren lo 8 cell (164s) cua case test, VMAF so voi
# ban lossless cung filter:
#   crf16 slow    200s  711 CPU-s  158 MB  VMAF 96.86
#   crf16 medium  117s  458 CPU-s  153 MB  VMAF 96.75   <- chon
#   crf17 medium  115s  445 CPU-s  133 MB  VMAF 96.64
#   crf16 fast    105s  401 CPU-s  149 MB  VMAF 96.72
# (rieng filter + giai ma ~160 CPU-s, phan con lai la encoder). Tran bitrate
# 12M: thuc te ra ~6,5 Mbps, video 30 phut ~1,5 GB; YouTube tu nen lai ve
# ~8 Mbps nen dat hon cung khong duoc gi.
FINAL_CRF = os.environ.get("FINAL_CRF", "16")
FINAL_PRESET = os.environ.get("FINAL_PRESET", "medium")
FINAL_MAXRATE = os.environ.get("FINAL_MAXRATE", "12M")
# Lo chay song song, toi da 3 (16 luong / ~5 luong hieu qua moi x264). Moi lo
# mo 8 shot 1080p cung luc: do 01/10/2026 an ~2,3 GB RAM, nen so lo con bi
# chan theo RAM dang trong (xem render.jobs_by_ram) — tran RAM thi Windows
# day ra pagefile va ca 3 lo cung bo.
def stage1_jobs():
    from render import jobs_by_ram
    return jobs_by_ram(2.3, max(2, (os.cpu_count() or 8) // 5), "STAGE1_JOBS")


def final_venc(fps):
    g = str(int(2 * fps))
    # -r: bo fps= trong chuoi filter thi timebase ra encoder la 1/1000000 va
    # packet CUOI moi lo khong co duration -> concat demuxer dat lo sau chong
    # len frame cuoi lo truoc (dts trung o moi moi noi). -r cho timebase 1/fps.
    return ["-r", str(fps),
            "-c:v", "libx264", "-crf", FINAL_CRF, "-preset", FINAL_PRESET,
            "-g", g, "-keyint_min", g, "-sc_threshold", "0", "-bf", "0",
            "-pix_fmt", "yuv420p", "-maxrate", FINAL_MAXRATE,
            "-bufsize", str(int(FINAL_MAXRATE.rstrip("Mm") or 12) * 2) + "M"]


def _batch_sig(root, batch, cmd):
    """Chu ky cua mot lo: doi bat cu dau vao nao -> lo bi lam lai."""
    import hashlib
    h = hashlib.md5()
    h.update("\x00".join(cmd).encode("utf-8"))
    for r in batch:
        for p in (r["shot"], r.get("vo")):
            if p and os.path.exists(p):
                st = os.stat(p)
                h.update(f"{p}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8"))
        # phu de doc tu textfile (ten co dinh theo cell) -> bam noi dung chu
        h.update((r["cell"].get("cap") or "").encode("utf-8"))
    return h.hexdigest()[:16]


def _batch_ok(out, sig, want_dur):
    if not os.path.exists(out):
        return False
    try:
        from probe import duration as _d
        got = _d(out)
    except (SystemExit, Exception):
        return False
    sp = out + ".sig"
    if not os.path.exists(sp):
        # Lo CU (truoc khi co chu ky, vd case dang do can-long) luon bi lam lai:
        # code cu roi mat 1 frame moi cell (xem _cell_chain) nen lo cu ngan hon
        # ke hoach dung so cell — do tren Can Long ca 23 lo deu hut 8 frame.
        # Tron lo cu voi lo moi con hong ca noi -c copy (SPS preset khac nhau).
        return False
    try:
        return (open(sp, encoding="utf-8").read().strip() == sig
                and abs(got - want_dur) <= 0.1)
    except OSError:
        return False


# ---------------------------------------------------------------- stage 2
def stage2_concat(rows, root, fps=24):
    """Noi cac LO -> video.mp4 bang concat demuxer, KHONG encode lai.

    Cac lo deu do stage1 encode voi cung tham so (cung fps, cung SAR, GOP 2s,
    -bf 0, keyframe co dinh) nen -c copy noi duoc thang. GOP 2s + keyint_min +
    sc_threshold=0 giu keyframe gan de Windows Media Player (codec DMO cu, fail
    0x80004005 khi seek giua GOP dai) van seek duoc.
    """
    # KHONG con ghi build/trim/video.mp4: ban cu noi cac lo ra mot ban day du
    # (-c copy) roi stage4 lai copy no sang final — tren dia cung luc co 3 ban
    # cua ca video (lo + video.mp4 + final), case 30 phut la ~6 GB chi cho
    # video. Nay stage4 doc thang danh sach lo bang concat demuxer.
    tdir = os.path.join(root, "build", "trim")
    n_batch = len(_batches(rows))
    list_file = os.path.join(tdir, "list.txt")
    with open(list_file, "w", encoding="utf-8", newline="\n") as f:
        for b in range(n_batch):
            f.write(f"file 'batch-{b}.mp4'\n")
    return list_file


def decode_check(root, out):
    """Decode toan bo file cuoi, bao loi neu co (rc != 0)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-f", "null", "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"decode check loi {out}:\n{r.stderr[-1500:]}")
    if (r.stderr or "").strip():
        # rc=0 nhung co canh bao (vd dts trung o moi noi lo) — in ra cho thay
        print("decode check: OK nhung co canh bao:\n" + r.stderr.strip()[-800:])
        return
    print("decode check: OK")


# ---------------------------------------------------------------- stage 3
def _chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _sfx_source(root, cell):
    """Tra ve (path_audio, dur) cho sfx cua cell. Ten hoac noise tu sinh."""
    from sfx import sfx_file
    name = cell.get("sfx")
    path = sfx_file(root, name) if name else None
    if path:
        dur = cell.get("sfx_dur") or duration(path)
        dur = min(dur, duration(path))
        return path, dur
    # noise hit tu sinh: ghi wav tam
    tdir = os.path.join(root, "build", "tmp")
    os.makedirs(tdir, exist_ok=True)
    d = cell.get("sfx_dur") or 0.8
    wav = os.path.join(tdir, f"noise-{cell['id']}.wav")
    gen = (f"anoisesrc=color=pink:sample_rate=48000:amplitude=0.6:duration={d}:seed=7,"
           f"lowpass=f=3200,highpass=f=120,"
           f"afade=t=in:st=0:d=0.005,afade=t=out:st={max(0.0, d-0.25):.2f}:d=0.25,"
           f"volume=1.2")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", gen,
                    "-c:a", "pcm_s16le", "-ar", str(AR), "-ac", "2", wav],
                   check=True)
    return wav, d


def stage3_audio(rows, total, root, cfg, chunk=12):
    """Mix VO + clip audio (duck theo VO) + SFX + nhac (duck theo tieng noi).

    Clip = main, VO = sidechain: khi VO doc thi clip tu ha xuong.
    Nhac: bed full, nhung cell co music=out/drop thi nhac ngung (chen silence
    tai doan do) — dung "let it land".
    """
    tdir = os.path.join(root, "build", "trim")
    os.makedirs(tdir, exist_ok=True)

    vo_items = [(r["start"], r["vo"]) for r in rows if r["vo"]]
    vo_cells = {r["cell"]["id"] for r in rows if r["vo"]}
    clip_items = []
    for r in rows:
        if r["audio"]:
            vol = r["cell"].get("clip_vol",
                                0.6 if r["cell"]["id"] in vo_cells else 1.0)
            clip_items.append((r["start"], r["cell"]["id"], vol))
    # SFX: gan vao cell (sfx field), phat tai cell_start + sfx_at
    sfx_items = []
    for r in rows:
        if r["cell"].get("sfx"):
            sfx_items.append((r["start"], r["cell"]["id"]))
    # sfx chuyen canh (ap_chuyen_canh): nhieu tieng moi cell, moc tuyet doi
    from sfx import sfx_file as _sfx_file
    fx_items = []
    for r in rows:
        for it in r["cell"].get("sfx_list") or []:
            pth = _sfx_file(root, it["name"])
            if not pth:
                continue
            at = max(0.0, r["start"] + float(it.get("at", 0.0)))
            fx_items.append((at, pth, duration(pth), float(it.get("vol", 0.3))))

    part_cmds, parts_by_tag = [], {}

    # Moi file tung phan chi phu DUNG KHOANG thoi gian cua nhom no (roi dat vao
    # moc o lan mix cuoi), va luu FLAC. Ban cu moi phan dai BANG CA VIDEO
    # (adelay + apad + atrim=total), PCM 16-bit stereo: video 30 phut 186 cell
    # = 16 phan x 345 MB = 5,5 GB chi cho giong doc — chinh no lam case Can Long
    # chet het dia o assemble. Nay tong cac phan ~ do dai video x 1, nen FLAC.
    def _mk_partials(items, tag, is_vo=False, is_sfx=False, is_fx=False):
        parts = []
        for ci, group in enumerate(_chunked(items, chunk)):
            if not group:
                continue
            spans = []
            for it in group:
                if is_fx:
                    spans.append((it[0], it[0] + it[2]))
                elif is_vo:
                    start, vo_path = it
                    spans.append((start, start + duration(vo_path)))
                elif is_sfx:
                    start, cid = it
                    cell = next(r["cell"] for r in rows if r["cell"]["id"] == cid)
                    at = start + cell.get("sfx_at", 0.0)
                    spans.append((at, at + _sfx_source(root, cell)[1]))
                else:
                    start, cid, _vol = it
                    dur = next(r["dur"] for r in rows if r["cell"]["id"] == cid)
                    spans.append((start, start + dur))
            g0 = min(s for s, _ in spans)
            g1 = min(total, max(e for _, e in spans) + 0.05)
            ins, fc, n_in, src = [], [], 0, ""
            for it, (s0, _e) in zip(group, spans):
                rel_ms = int(round((s0 - g0) * 1000))
                if is_fx:
                    _at, fpath, flen, fvol = it
                    ins += ["-i", fpath]
                    fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts="
                              f"stereo,asetpts=PTS-STARTPTS,atrim=duration={flen:.3f},"
                              f"volume={fvol},adelay={rel_ms}|{rel_ms},"
                              f"apad[{tag}{ci}_{n_in}]")
                elif is_vo:
                    start, vo_path = it
                    ins += ["-i", vo_path]
                    fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts="
                              f"stereo,asetpts=PTS-STARTPTS,adelay={rel_ms}|"
                              f"{rel_ms},apad[{tag}{ci}_{n_in}]")
                elif is_sfx:
                    start, cid = it
                    cell = next(r["cell"] for r in rows if r["cell"]["id"] == cid)
                    sfx_path, sfx_len = _sfx_source(root, cell)
                    vol = cell.get("sfx_vol", 0.6)
                    ins += ["-i", sfx_path]
                    fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts="
                              f"stereo,asetpts=PTS-STARTPTS,atrim=duration={sfx_len:.3f},"
                              f"volume={vol},adelay={rel_ms}|{rel_ms},"
                              f"apad[{tag}{ci}_{n_in}]")
                else:
                    start, cid, vol = it
                    shot = next(r["shot"] for r in rows if r["cell"]["id"] == cid)
                    dur = next(r["dur"] for r in rows if r["cell"]["id"] == cid)
                    ins += ["-i", shot]
                    fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts="
                              f"stereo,asetpts=PTS-STARTPTS,atrim=duration={dur},"
                              f"volume={vol},adelay={rel_ms}|{rel_ms},"
                              f"apad[{tag}{ci}_{n_in}]")
                src += f"[{tag}{ci}_{n_in}]"
                n_in += 1
            fc.append(f"{src}amix=inputs={n_in}:normalize=0,atrim=0:{g1 - g0:.3f},"
                      f"asetpts=PTS-STARTPTS[a{ci}]")
            p = os.path.join(tdir, f"{tag}-{ci}.flac")
            part_cmds.append(["ffmpeg", "-y", "-v", "error", *ins,
                              "-filter_complex", ";".join(fc),
                              "-map", f"[a{ci}]", "-c:a", "flac",
                              "-ar", str(AR), "-ac", "2", p])
            parts.append((p, g0))
        parts_by_tag[tag] = parts
        return parts

    vo_parts = _mk_partials(vo_items, "vo", is_vo=True)
    clip_parts = _mk_partials(clip_items, "clip")
    sfx_parts = _mk_partials(sfx_items, "sfx", is_sfx=True)
    sfx_parts += _mk_partials(fx_items, "fx", is_fx=True)

    # gop: vo + clip-duck + sfx
    ins, fc, n_in = [], [], 0

    def _mix(parts, out_label):
        nonlocal n_in, ins, fc
        src = ""
        for p, g0 in parts:
            ins += ["-i", p]
            ms = int(round(g0 * 1000))
            fc.append(f"[{n_in}:a]asetpts=PTS-STARTPTS,adelay={ms}|{ms},apad,"
                      f"atrim=0:{total:.3f}[a{n_in}]")
            src += f"[a{n_in}]"
            n_in += 1
        if not src:
            ins += ["-f", "lavfi", "-t", str(total), "-i",
                    "anullsrc=r=48000:cl=stereo"]
            fc.append(f"[{n_in}:a]anull[{out_label}]")
            n_in += 1
        else:
            fc.append(f"{src}amix=inputs={len(parts)}:normalize=0[{out_label}]")

    music = CFG.resolve(root, cfg["music"]["file"]) if cfg.get("music") else None
    bed_spec = _bed_spec(music)
    _mix(vo_parts, "vo")
    if bed_spec and float(bed_spec.get("hook_db", 0) or 0) > 0:
        # 5 giay dau: giong to hon ~2 dB (BLV Hai Thanh: 5s dau giong +2,6 dB,
        # nhac -4,6 dB so voi than bai) — nguoi xem bam vao nghe giong truoc.
        g = 10 ** (float(bed_spec["hook_db"]) / 20.0)
        fc.append(f"[vo]volume='if(lt(t\\,5)\\,{g:.4f}\\,if(lt(t\\,5.6)\\,"
                  f"{g:.4f}-({g - 1:.4f})*(t-5)/0.6\\,1))':eval=frame[voh]")
        vo_lab = "[voh]"
    else:
        vo_lab = "[vo]"
    _mix(clip_parts, "clipraw")
    _mix(sfx_parts, "sfx")
    fc.append(f"{vo_lab}[clipraw][sfx]amix=inputs=3:normalize=0,"
              f"atrim=0:{total:.2f},asetpts=PTS-STARTPTS[side]")

    audio_out = "[side]"
    if music and os.path.exists(music) and bed_spec:
        # Nhac that (music_lib): KHONG sidechaincompress (muc duck phu thuoc muc
        # vao, nhac to nho khac nhau la duck khac nhau). Thay bang DUONG BAO dung
        # san tu timeline giong: duoi giong D dB, 5s dau sau hon, khe >= 0,9s
        # nhac nhich len, truoc diem chuyen chuong nhac day len.
        music_seg = _build_music_segments(root, cfg, rows, total)
        env = _build_music_env(root, rows, total, bed_spec)
        ins += ["-i", music_seg, "-i", env]
        fi = cfg["music"].get("fade_in", 1.5)
        fo = cfg["music"].get("fade_out", 3.0)
        lvl = float(bed_spec.get("level", 1.0))
        fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts=stereo,"
                  f"volume={lvl},afade=t=in:st=0:d={fi},"
                  f"afade=t=out:st={max(0.0, total - fo):.2f}:d={fo}[mb]")
        fc.append(f"[{n_in + 1}:a]aresample={AR},aformat=sample_rates={AR}:"
                  f"channel_layouts=stereo,apad,atrim=0:{total:.3f}[menv]")
        n_in += 2
        fc.append("[mb][menv]amultiply[mduck]")
        fc.append(f"[side][mduck]amix=inputs=2:normalize=0,atrim=0:{total},"
                  f"aformat=sample_rates={AR}:channel_layouts=stereo[aout]")
        audio_out = "[aout]"
    elif music and os.path.exists(music):
        # tao nhac co silence tai cell out/drop
        music_seg = _build_music_segments(root, cfg, rows, total)
        ins += ["-i", music_seg]
        level = cfg["music"].get("level", 0.28)
        fi = cfg["music"].get("fade_in", 1.5)
        fo = cfg["music"].get("fade_out", 3.0)
        fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts=stereo,"
                  f"volume={level},"
                  f"afade=t=in:st=0:d={fi},afade=t=out:st={max(0.0,total-fo):.2f}:"
                  f"d={fo}[mb]")
        n_in += 1
        # DUCKING: nen nhac theo tin hieu thoai. sidechaincompress chi xuat luong
        # main (nhac) da nen — no KHONG tra lai sidechain — nen phai split va mix
        # thoai vao lai sau do. Ban cu map thang output cua no nen mat VO, roi
        # ket luan nham la "ffmpeg loi" va bo duck luon.
        fc.append("[side]asplit=2[side_out][side_key]")
        fc.append("[side_key]highpass=f=200,lowpass=f=4000,volume=3[key]")
        fc.append("[mb][key]sidechaincompress=threshold=0.02:ratio=8:attack=15:"
                  "release=350:makeup=1:level_sc=1[mduck]")
        fc.append(f"[side_out][mduck]amix=inputs=2:normalize=0,atrim=0:{total},"
                  f"aformat=sample_rates={AR}:channel_layouts=stereo[aout]")
        audio_out = "[aout]"

    # Xuat WAV: loudnorm + AAC duoc lam MOT LAN o stage4 (do duoc loudness that
    # roi moi chuan hoa tuyen tinh), thay vi encode AAC o day roi encode lai.
    # FLAC thay WAV 24-bit (30 phut = 518 MB): khong mat mat, nhe ~3 lan.
    out = os.path.join(tdir, "audio_raw.flac")
    final = [["ffmpeg", "-y", "-v", "error", *ins,
              "-filter_complex", ";".join(fc),
              "-map", audio_out, "-c:a", "flac", "-sample_fmt", "s32",
              "-ar", str(AR), "-ac", "2", "-t", str(total), out]]
    # cac phan doc lap nhau -> chay song song; lan mix cuoi chay sau cung
    _emit(root, "run_stage3.sh", part_cmds, jobs=4, after=final)
    return out


def _bed_spec(music):
    """bed.json canh bed.wav (tool/music_lib.py ghi) -> dict, hoac None (cu)."""
    if not music:
        return None
    p = os.path.splitext(music)[0] + ".json"
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return None
    return d if d.get("env") else None


def _speech_spans(root, rows):
    """Cac doan DANG NOI tren timeline (giay). Uu tien moc tu words.json (biet
    ca khe giua cau trong cell), khong co thi ca cell VO."""
    spans = []
    for r in rows:
        if not r["vo"]:
            if r["audio"]:          # clip co tieng goc
                spans.append((r["start"], r["start"] + r["dur"]))
            continue
        marks = _word_marks(root, r["cell"]["id"])
        if marks:
            cur = None
            for w in marks:
                a = r["start"] + float(w["t"])
                b = a + float(w.get("d", 0.2))
                if cur and a - cur[1] < 0.35:
                    cur[1] = max(cur[1], b)
                else:
                    if cur:
                        spans.append(tuple(cur))
                    cur = [a, b]
            if cur:
                spans.append(tuple(cur))
        else:
            spans.append((r["start"], r["start"] + r["vo_dur"]))
    return spans


def _build_music_env(root, rows, total, spec):
    """Duong bao gain cho nhac (WAV 1 kHz mono, 1.0 = muc bed).

    Muc tinh theo dB DUOI muc giong (bed da chuan ve cung loudness voi giong):
      duoi_giong (18)  khi dang noi
      hook_them  (+3)  sau hon nua trong 5s dau (doi thu: 20 dB o hook)
      khe_len    (8)   khe khong loi >= 0,9s: nhac nhich len 8 dB
      chuong_len (12)  1,8s truoc -> 0,4s sau diem chuyen chuong: day len 12 dB
    """
    import numpy as np
    D = float(spec.get("duoi_giong", 18))
    hook_extra = float(spec.get("hook_them", 3))
    gap_up = float(spec.get("khe_len", 8))
    khe_min = float(spec.get("khe_min", 0.9))
    ch_up = float(spec.get("chuong_len", 12))
    hz = 100
    n = int(total * hz) + 2
    db = np.full(n, -(D - gap_up))          # mac dinh: khe (khong loi)
    spans = _speech_spans(root, rows)
    # khe ngan giua hai doan noi (< 0,9s) -> giu duck, khong de nhac nhap nho
    merged = []
    for a, b in sorted(spans):
        if merged and a - merged[-1][1] < khe_min:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for a, b in merged:
        i0 = max(0, int((a - 0.25) * hz))
        i1 = min(n, int((b + 0.2) * hz) + 1)
        db[i0:i1] = -D
    # hook 5s dau: nhac sau hon
    h = min(n, 5 * hz)
    db[:h] = np.minimum(db[:h], -(D + hook_extra))
    # chuyen chuong: day len trong khe truoc diem cat (khong de len giong)
    speak = np.zeros(n, dtype=bool)
    for a, b in merged:
        speak[max(0, int(a * hz)):min(n, int(b * hz) + 1)] = True
    for r in rows:
        if (r.get("tr") or {}).get("kieu") == "fadewhite" or r["cell"].get("chuong"):
            c = r["start"]
            i0, i1 = max(0, int((c - 1.8) * hz)), min(n, int((c + 0.4) * hz))
            seg = db[i0:i1]
            up = -(D - ch_up)
            db[i0:i1] = np.where(speak[i0:i1], seg, np.maximum(seg, up))
    # lam muot: trung binh truot 0,3s (len/xuong deu, khong giat)
    k = 30
    pad = np.pad(db, (k // 2, k // 2), mode="edge")
    sm = np.convolve(pad, np.ones(k) / k, mode="valid")[:n]
    g = 10 ** (sm / 20.0)
    sr = 1000
    t_ctrl = np.arange(n) / hz
    t_out = np.arange(int(total * sr) + sr) / sr
    gg = np.interp(t_out, t_ctrl, g)
    out = os.path.join(root, "build", "trim", "music-env.wav")
    import wave
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(gg, 0, 1) * 32767).astype("<i2").tobytes())
    return out


def _build_music_segments(root, cfg, rows, total):
    """Tao nhac full: sine bed duy nhat, nhung tai cell out/drop thi silence."""
    music = CFG.resolve(root, cfg["music"]["file"])
    # tach thanh doan: on/off theo cell
    segs = []  # (start, end, on)
    for r in rows:
        m = r["cell"].get("music", "in")
        on = m in ("in", "swell")
        segs.append((r["start"], r["start"] + r["dur"], on))
    segs.sort()
    # gop lien tiep cung trang thai
    merged = []
    for s, e, on in segs:
        if merged and merged[-1][2] == on and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e), on)
        else:
            merged.append((s, e, on))
    # tao track gating: cat bed theo doan, chen silence
    # MOT lenh: tat tieng bed trong cac doan off bang volume=0:enable. Ban cu
    # cat moi doan "on" ra mseg-i.wav (moi doan mot tien trinh ffmpeg) roi mix
    # lai thanh music-gate.wav day du — ket qua y het (doan on lay dung bed tai
    # cung moc giay) nhung ton N+1 lan chay va ~2x do dai video PCM tren dia.
    out = os.path.join(root, "build", "trim", "music-gate.flac")
    offs = [(s, e) for s, e, on in merged if not on]
    af = [f"aformat=sample_rates={AR}:channel_layouts=stereo", "apad",
          f"atrim=0:{total}", "asetpts=PTS-STARTPTS"]
    if offs:
        expr = "+".join(f"between(t\\,{s:.3f}\\,{e:.3f})" for s, e in offs)
        af.append(f"volume=0:enable='{expr}'")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", music,
                    "-filter_complex", "[0:a]" + ",".join(af) + "[aout]",
                    "-map", "[aout]", "-c:a", "flac",
                    "-ar", str(AR), "-ac", "2", out], check=True)
    return out


# ---------------------------------------------------------------- stage 4
TARGET_LUFS = -14.0     # chuan YouTube
TARGET_TP = -1.0        # true peak


def _measure_loudness(path, I=TARGET_LUFS, TP=TARGET_TP, LRA=11):
    """Pass 1 cua loudnorm: do loudness that de pass 2 chuan hoa TUYEN TINH.

    Chuan hoa 1 pass se nen dong (bop dynamic); 2 pass chi dich gain nen giu
    nguyen nhip to-nho cua giong doc.
    """
    if not os.path.exists(path):
        return None
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:"
                        f"print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = r.stderr or ""
    i = txt.rfind("{")
    if i < 0:
        return None
    try:
        import json as _json
        return _json.loads(txt[i:txt.rfind("}") + 1])
    except Exception:
        return None


def loud_marker(out):
    """File ghi dich loudness ma final da duoc chuan — steps.chuan_tieng doc no
    de biet khong can encode audio lan nua."""
    return os.path.splitext(out)[0] + ".loudness.json"


def finish_loud(out):
    """Goi SAU khi stage4 chay xong: marker .pending -> marker that."""
    p = loud_marker(out) + ".pending"
    if os.path.exists(p):
        os.replace(p, loud_marker(out))
        os.utime(loud_marker(out))    # mtime > final: chuan_tieng so sanh moc nay


def stage4_mux(root, cfg, total, loud=None):
    """Ghep lo video (concat demuxer, -c copy) + audio -> final. Chuan hoa
    loudness MOT LAN o day.

    loud = {"I", "LRA", "TP"} (tu queue.yml qua steps): chuan thang ve dich cua
    kenh. Ban cu chuan 3 lan: tts -16/cell, o day -14 + alimiter + AAC 256k,
    roi steps.chuan_tieng lai loudnorm ve -19,7 va encode AAC lan hai (100s
    cho video 20 phut, va hai the he AAC). Nay mot lan loudnorm 2 pass dung
    dich, mot lan AAC; chuan_tieng chi con do lai de xac nhan.
    Khong co loud (goi tay tu CLI) -> hanh vi cu: -14 LUFS / TP -1.
    """
    tdir = os.path.join(root, "build", "trim")
    out = CFG.resolve(root, cfg["out"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    araw = os.path.join(tdir, "audio_raw.flac")
    try:
        os.remove(loud_marker(out))
    except OSError:
        pass
    if loud:
        I, LRA, TP = float(loud["I"]), float(loud["LRA"]), float(loud["TP"])
        m = _measure_loudness(araw, I=I, TP=TP, LRA=LRA)
        af = f"loudnorm=I={I}:LRA={LRA}:TP={TP}"
        if m:
            print(f"  loudness truoc: {m['input_i']} LUFS (dai dong {m['input_lra']} LU)"
                  f", peak {m['input_tp']} dBTP -> chuan MOT LAN ve {I} LUFS / "
                  f"LRA {LRA} / TP {TP}")
            # linear=true: neu dat duoc dich chi bang dich gain thi giu nguyen
            # dong; khong dat (LRA do > LRA dich) ffmpeg tu chuyen sang nen
            # dong — dung nhu ban loudnorm 1 pass cu cua chuan_tieng.
            af += (f":linear=true:measured_I={m['input_i']}"
                   f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                   f":measured_thresh={m['input_thresh']}"
                   f":offset={m['target_offset']}")
        cmd = ["ffmpeg", "-y", "-v", "error",
               "-f", "concat", "-safe", "0", "-i", os.path.join(tdir, "list.txt"),
               "-i", araw,
               "-map", "0:v", "-map", "1:a", "-af", af,
               "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(AR),
               "-movflags", "+faststart", "-shortest", out]
        _emit(root, "run_stage4.sh", [cmd])
        with open(loud_marker(out) + ".pending", "w", encoding="utf-8") as f:
            json.dump({"I": I, "LRA": LRA, "TP": TP}, f)
        return out
    m = _measure_loudness(araw)
    lra = 11.0
    ln = ""
    if m:
        # Timeline video co dai dong rat rong (doan noi to xen doan chi con nhac):
        # do duoc LRA ~23 LU. Neu dat LRA muc tieu thap hon LRA do duoc thi
        # loudnorm bo che do linear, chuyen sang nen dong va KHONG toi dich —
        # do la ly do ban dau ra -16.3 thay vi -14. Noi rong LRA de chi dich gain.
        lra = max(11.0, float(m["input_lra"]) + 1.0)
        print(f"  loudness truoc: {m['input_i']} LUFS (dai dong {m['input_lra']} LU), "
              f"peak {m['input_tp']} dBTP -> chuan hoa ve {TARGET_LUFS} LUFS")
    ln = f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA={lra:.1f}"
    if m:
        ln += (f":linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
               f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
               f":offset={m['target_offset']}")
    af = ln + ",alimiter=limit=0.97:attack=5:release=50:level=disabled"
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "concat", "-safe", "0", "-i", os.path.join(tdir, "list.txt"),
           "-i", araw,
           "-map", "0:v", "-map", "1:a", "-af", af,
           "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", str(AR),
           "-movflags", "+faststart", "-shortest", out]
    _emit(root, "run_stage4.sh", [cmd])
    return out


# ---------------------------------------------------------------- helpers
def _emit(root, name, cmds, jobs=1, after=()):
    """Ghi lenh ra .sh. jobs > 1: chay song song toi da `jobs` lenh (xem
    render.par_header). Lenh bat dau bang "sig1 <sig> <out>" = ffmpeg xong thi
    ghi chu ky vao <out>.sig (de lan chay sau biet lo nay con dung duoc)."""
    from render import par_header, par_line, PAR_FOOTER
    sh = os.path.join(root, "build", name)
    root_posix = root.replace("\\", "/")
    with open(sh, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\nset -e\n")
        f.write(f'cd "{root_posix}"\n')
        f.write("r() { n=0; while :; do \"$@\" && return 0; n=$((n+1)); "
                "[ $n -ge 3 ] && return 1; echo \"  retry $n\" >&2; sleep 1; done; }\n")
        f.write("sig1() { s=\"$1\"; o=\"$2\"; shift 2; \"$@\" && "
                "printf '%s\\n' \"$s\" > \"$o.sig\"; }\n")
        if jobs > 1:
            f.write(par_header(jobs))
        for c in cmds:
            line = "r " + " ".join(shlex.quote(a) for a in c)
            f.write((par_line(line) if jobs > 1 else line) + "\n")
        if jobs > 1:
            f.write(PAR_FOOTER)
        for c in after:          # chay tuan tu, SAU khi moi lenh song song xong
            f.write("r " + " ".join(shlex.quote(a) for a in c) + "\n")
        f.write(f'echo "{name} OK"\n')
    print(f"emit {len(cmds)} lenh -> {name}" + (f" (song song {jobs})" if jobs > 1 else ""))


def run_script(root, name):
    sh = os.path.join(root, "build", name)
    r = subprocess.run([GIT_BASH, "-lc", f'source "{sh.replace(os.sep, "/")}"'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1200:])
        print(r.stderr[-1200:])
        raise SystemExit(f"{name} loi rc={r.returncode}")
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--emit-only", action="store_true")
    args = ap.parse_args()

    root = os.path.abspath(args.case)
    if not os.path.isdir(root):
        raise SystemExit(f"khong thay {root}")
    cfg = CFG.load(root)
    rows, total, missing = plan(root, cfg, strict=True)
    if missing:
        raise SystemExit(f"{len(missing)} cell thieu VO, chay tts truoc: {missing[:10]}")
    print(f"tong video: {total:.1f}s ({total/60:.1f} phut), {len(rows)} cell")
    ap_chuyen_canh(rows, cfg, root)
    from render import kieu_the
    xf = kieu_the(cfg) in ("long", "info")

    if args.emit_only:
        stage1_trim(rows, root, cfg.get("fps", 24), xfade=xf)
        stage2_concat(rows, root)
        stage3_audio(rows, total, root, cfg)
        stage4_mux(root, cfg, total)
        print("chay lan luot: source build/run_stage1.sh, stage3, stage4")
        return

    print("stage 1: trim + caption ...")
    stage1_trim(rows, root, cfg.get("fps", 24), xfade=xf)
    run_script(root, "run_stage1.sh")
    stage2_concat(rows, root)
    print("stage 3: audio ...")
    stage3_audio(rows, total, root, cfg)
    run_script(root, "run_stage3.sh")
    print("stage 4: mux ...")
    stage4_mux(root, cfg, total)
    run_script(root, "run_stage4.sh")
    finish_loud(CFG.resolve(root, cfg["out"]))
    print(f"DONE  {CFG.resolve(root, cfg['out'])}")


if __name__ == "__main__":
    main()
