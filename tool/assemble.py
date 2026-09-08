"""
assemble.py — Ghep video tu config.json, chia 4 giai doan.

  Stage 1 (trim):   moi cell -> build/trim/cell-<id>.mp4 (cat dung cell_dur,
                    burn caption khi co VO, dong last frame neu shot ngan)
  Stage 2 (concat): noi trim thanh build/trim/video.mp4
  Stage 3 (audio):  mix VO + clip audio + SFX + nhac duck -> build/trim/audio.m4a
  Stage 4 (mux):    ghep video + audio -> out

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
CAP_MAX_CHARS = 34      # chu to hon (56px) -> moi dong phai ngan lai
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
    cap = cell.get("cap") or cell.get("vo")
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
    segs = _split_segments(cell["cap"])
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


def stage1_trim(rows, root, fps):
    tdir = os.path.join(root, "build", "trim")
    os.makedirs(tdir, exist_ok=True)
    _ensure_stage1_fonts(root)
    cmds = []
    for r in rows:
        cid = r["cell"]["id"]
        out = os.path.join(tdir, f"cell-{cid}.mp4")
        dur = r["dur"]
        need_pad = max(0.0, dur - r["shot_dur"])
        vf = []
        if need_pad > 0.01:
            vf.append(f"tpad=stop_mode=clone:stop_duration={need_pad:.3f}")
        vf.append("setpts=PTS-STARTPTS")
        vf.append(f"trim=duration={dur}")
        vf.append("setpts=PTS-STARTPTS")
        vf.append("scale=1920:1080:force_original_aspect_ratio=decrease,"
                  "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x14110F,setsar=1,"
                  f"fps={fps},format=yuv420p")
        # subtitle: burn ASS instant (local timeline 0..vo_dur)
        cap, _ = _caption_filter(root, r["cell"], None, r["vo_dur"], fps)
        if cap:
            vf.append(cap)
        # fade: vao 0.2s, ra 0.2s; dip-to-black manh hon (0.4) o beat drop.
        # Cell fx=flash: white flash 0.15s dau (khong fade-in che).
        fi = 0.2
        fo = 0.2
        if r["cell"].get("music") == "drop" and r["cell"].get("fx") != "flash":
            fi, fo = 0.35, 0.35
        if r["cell"].get("fx") == "flash":
            fi = 0.0
            vf.append("fade=t=in:st=0:d=0.15:color=white")
        if dur > (fi + fo + 0.2):
            vf.append(f"fade=t=in:st=0:d={fi}")
            vf.append(f"fade=t=out:st={dur - fo:.3f}:d={fo}")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", r["shot"],
               "-vf", ",".join(vf), "-c:v", "libx264", "-crf", "16",
               "-an", out]
        cmds.append(cmd)
    _emit(root, "run_stage1.sh", cmds)
    return tdir


# ---------------------------------------------------------------- stage 2
def stage2_concat(rows, root, fps=24):
    """Noi cac cell -> video.mp4, RE-ENCODE de GOP ngan (2s) + khong B-frame.

    Ly do: Windows Media Player (codec DMO cu) fail 0x80004005 khi seek vao
    giua GOP dai (moi cell = 1 GOP 3-10s). `-g {2*fps}` (2s) + `-bf 0` lam
    keyframe gan de seek. Nha diem: file lon hon ~5-10%.
    """
    tdir = os.path.join(root, "build", "trim")
    list_file = os.path.join(tdir, "list.txt")
    with open(list_file, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(f"file 'cell-{r['cell']['id']}.mp4'\n")
    out = os.path.join(tdir, "video.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
           "-i", list_file, "-c:v", "libx264", "-crf", "16", "-preset", "fast",
           "-g", str(int(2 * fps)), "-bf", "0", "-pix_fmt", "yuv420p", out]
    _emit(root, "run_stage2.sh", [cmd])
    return out


def decode_check(root, out):
    """Decode toan bo file cuoi, bao loi neu co (rc != 0)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-f", "null", "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"decode check loi {out}:\n{r.stderr[-1500:]}")
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

    part_cmds, parts_by_tag = [], {}

    def _mk_partials(items, tag, is_vo=False, is_sfx=False):
        parts = []
        for ci, group in enumerate(_chunked(items, chunk)):
            if not group:
                continue
            ins, fc, n_in, src = [], [], 0, ""
            for it in group:
                if is_vo:
                    start, vo_path = it
                    ins += ["-i", vo_path]
                    fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts="
                              f"stereo,asetpts=PTS-STARTPTS,adelay={int(start*1000)}|"
                              f"{int(start*1000)},apad[{tag}{ci}_{n_in}]")
                elif is_sfx:
                    start, cid = it
                    cell = next(r["cell"] for r in rows if r["cell"]["id"] == cid)
                    name = cell.get("sfx")
                    sfx_path, sfx_len = _sfx_source(root, cell)
                    at_ms = int((start + cell.get("sfx_at", 0.0)) * 1000)
                    vol = cell.get("sfx_vol", 0.6)
                    ins += ["-i", sfx_path]
                    fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts="
                              f"stereo,asetpts=PTS-STARTPTS,atrim=duration={sfx_len:.3f},"
                              f"volume={vol},adelay={at_ms}|{at_ms},"
                              f"apad[{tag}{ci}_{n_in}]")
                else:
                    start, cid, vol = it
                    shot = next(r["shot"] for r in rows if r["cell"]["id"] == cid)
                    dur = next(r["dur"] for r in rows if r["cell"]["id"] == cid)
                    ins += ["-i", shot]
                    fc.append(f"[{n_in}:a]aformat=sample_rates={AR}:channel_layouts="
                              f"stereo,asetpts=PTS-STARTPTS,atrim=duration={dur},"
                              f"volume={vol},adelay={int(start*1000)}|{int(start*1000)},"
                              f"apad[{tag}{ci}_{n_in}]")
                src += f"[{tag}{ci}_{n_in}]"
                n_in += 1
            fc.append(f"{src}amix=inputs={n_in}:normalize=0,atrim=0:{total},"
                      f"asetpts=PTS-STARTPTS[a{ci}]")
            p = os.path.join(tdir, f"{tag}-{ci}.wav")
            part_cmds.append(["ffmpeg", "-y", "-v", "error", *ins,
                              "-filter_complex", ";".join(fc),
                              "-map", f"[a{ci}]", "-c:a", "pcm_s16le",
                              "-ar", str(AR), "-ac", "2", p])
            parts.append(p)
        parts_by_tag[tag] = parts
        return parts

    vo_parts = _mk_partials(vo_items, "vo", is_vo=True)
    clip_parts = _mk_partials(clip_items, "clip")
    sfx_parts = _mk_partials(sfx_items, "sfx", is_sfx=True)

    # gop: vo + clip-duck + sfx
    ins, fc, n_in = [], [], 0

    def _mix(parts, out_label):
        nonlocal n_in, ins, fc
        src = ""
        for p in parts:
            ins += ["-i", p]
            fc.append(f"[{n_in}:a]asetpts=PTS-STARTPTS[a{n_in}]")
            src += f"[a{n_in}]"
            n_in += 1
        if not src:
            ins += ["-f", "lavfi", "-t", str(total), "-i",
                    "anullsrc=r=48000:cl=stereo"]
            fc.append(f"[{n_in}:a]anull[{out_label}]")
            n_in += 1
        else:
            fc.append(f"{src}amix=inputs={len(parts)}:normalize=0[{out_label}]")

    _mix(vo_parts, "vo")
    _mix(clip_parts, "clipraw")
    _mix(sfx_parts, "sfx")
    fc.append("[vo][clipraw][sfx]amix=inputs=3:normalize=0,"
              f"atrim=0:{total:.2f},asetpts=PTS-STARTPTS[side]")

    audio_out = "[side]"
    music = CFG.resolve(root, cfg["music"]["file"]) if cfg.get("music") else None
    if music and os.path.exists(music):
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
    out = os.path.join(tdir, "audio_raw.wav")
    cmds = part_cmds + [["ffmpeg", "-y", "-v", "error", *ins,
                         "-filter_complex", ";".join(fc),
                         "-map", audio_out, "-c:a", "pcm_s24le",
                         "-ar", str(AR), "-ac", "2", "-t", str(total), out]]
    _emit(root, "run_stage3.sh", cmds)
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
    out = os.path.join(root, "build", "trim", "music-gate.wav")
    lst = []
    for i, (s, e, on) in enumerate(merged):
        if not on:
            continue
        p = os.path.join(root, "build", "trim", f"mseg-{i}.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(s), "-i", music,
             "-t", str(max(0.1, e - s)), "-c:a", "pcm_s16le", "-ar", str(AR),
             "-ac", "2", p], check=True)
        lst.append((s, p))
    # mix cac doan nhac dung vao dung moc
    ins, fc, src, n = [], [], "", 0
    for start, p in lst:
        ins += ["-i", p]
        fc.append(f"[{n}:a]asetpts=PTS-STARTPTS,adelay={int(start*1000)}|"
                  f"{int(start*1000)},apad[m{n}]")
        src += f"[m{n}]"
        n += 1
    if not lst:
        subprocess.run(["ffmpeg", "-y", "-v", "error",
                        "-f", "lavfi", "-t", str(total), "-i",
                        "anullsrc=r=48000:cl=stereo", out], check=True)
        return out
    fc.append(f"{src}amix=inputs={len(lst)}:normalize=0,atrim=0:{total},"
              f"asetpts=PTS-STARTPTS[aout]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins,
                    "-filter_complex", ";".join(fc),
                    "-map", "[aout]", "-c:a", "pcm_s16le",
                    "-ar", str(AR), "-ac", "2", out], check=True)
    return out


# ---------------------------------------------------------------- stage 4
TARGET_LUFS = -14.0     # chuan YouTube
TARGET_TP = -1.0        # true peak


def _measure_loudness(path):
    """Pass 1 cua loudnorm: do loudness that de pass 2 chuan hoa TUYEN TINH.

    Chuan hoa 1 pass se nen dong (bop dynamic); 2 pass chi dich gain nen giu
    nguyen nhip to-nho cua giong doc.
    """
    if not os.path.exists(path):
        return None
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-af", f"loudnorm=I={TARGET_LUFS}:TP={TARGET_TP}:LRA=11:"
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


def stage4_mux(root, cfg, total):
    tdir = os.path.join(root, "build", "trim")
    out = CFG.resolve(root, cfg["out"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    araw = os.path.join(tdir, "audio_raw.wav")
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
           "-i", os.path.join(tdir, "video.mp4"),
           "-i", araw,
           "-map", "0:v", "-map", "1:a", "-af", af,
           "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", str(AR),
           "-movflags", "+faststart", "-shortest", out]
    _emit(root, "run_stage4.sh", [cmd])
    return out


# ---------------------------------------------------------------- helpers
def _emit(root, name, cmds):
    sh = os.path.join(root, "build", name)
    root_posix = root.replace("\\", "/")
    with open(sh, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\nset -e\n")
        f.write(f'cd "{root_posix}"\n')
        f.write("r() { n=0; while :; do \"$@\" && return 0; n=$((n+1)); "
                "[ $n -ge 3 ] && return 1; echo \"  retry $n\" >&2; sleep 1; done; }\n")
        for c in cmds:
            f.write("r " + " ".join(shlex.quote(a) for a in c) + "\n")
        f.write(f'echo "{name} OK"\n')
    print(f"emit {len(cmds)} lenh -> {name}")


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

    if args.emit_only:
        stage1_trim(rows, root, cfg.get("fps", 24))
        stage2_concat(rows, root)
        stage3_audio(rows, total, root, cfg)
        stage4_mux(root, cfg, total)
        print("chay lan luot: source build/run_stage1.sh .. stage4")
        return

    print("stage 1: trim + caption ...")
    stage1_trim(rows, root, cfg.get("fps", 24))
    run_script(root, "run_stage1.sh")
    print("stage 2: concat ...")
    stage2_concat(rows, root)
    run_script(root, "run_stage2.sh")
    print("stage 3: audio ...")
    stage3_audio(rows, total, root, cfg)
    run_script(root, "run_stage3.sh")
    print("stage 4: mux ...")
    stage4_mux(root, cfg, total)
    run_script(root, "run_stage4.sh")
    print(f"DONE  {CFG.resolve(root, cfg['out'])}")


if __name__ == "__main__":
    main()
