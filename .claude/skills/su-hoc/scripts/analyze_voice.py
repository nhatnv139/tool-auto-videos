"""analyze_voice.py — do dac giong doc + nhip hinh cua mot video doi thu.

    python analyze_voice.py <URL youtube | file audio/video> --out <thu muc>
    tuy chon: --model small|medium  --no-transcribe  --keep-video

Sinh ra trong <thu muc>:
    voice.json   so lieu day du (may doc)
    report.md    bang tom tat (nguoi doc)
    frames/      anh tai moi diem cat canh trong 60s dau (de doi chieu voi loi doc)

Do nhung gi:
    - Loudness EBU R128: integrated LUFS, LRA, true peak.
    - Duong bao dBFS moi 20ms -> muc giong, muc nhac nen, chenh lech voice/nhac.
    - Ngat nghi: so pause/phut, median, p90, dai nhat, ti le im lang.
    - Toc do: am tiet/phut (gop) va am tiet/phut khi dang noi (tru pause).
    - 5s dau va 30s dau tach rieng: moc vao loi, so am tiet, pause, LUFS.
    - Bang theo tung phut de xem giong co xuong suc khong.
    - Cat canh (neu co video): nhip doi hinh, so cat trong 5s/30s dau.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np

HOP = 0.02          # 20ms
MIN_PAUSE = 0.15    # ngan hon coi la ngat hoi trong cau
SCENE_TH = 0.30


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def ensure_media(src, out):
    """Tra ve (audio_wav, video_mp4|None). Tai bang yt-dlp neu src la URL."""
    os.makedirs(out, exist_ok=True)
    wav = os.path.join(out, "audio.wav")
    vid = os.path.join(out, "video.mp4")
    meta = {}
    if src.startswith("http"):
        fmt = ("%(id)s\t%(channel)s\t%(title)s\t%(duration)s\t%(view_count)s"
               "\t%(upload_date)s")
        r = sh(["yt-dlp", "--skip-download", "--print", fmt, src])
        line = [l for l in r.stdout.strip().splitlines() if "\t" in l]
        if line:
            f = line[-1].split("\t")
            meta = dict(id=f[0], channel=f[1], title=f[2], duration=f[3],
                        views=f[4], upload=f[5])
        if not os.path.exists(wav):
            sh(["yt-dlp", "-f", "bestaudio/best", "-x", "--audio-format", "wav",
                "-o", os.path.join(out, "audio.%(ext)s"), src])
        if not os.path.exists(vid):
            sh(["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]",
                "--merge-output-format", "mp4", "-o", os.path.join(out, "video.%(ext)s"),
                src])
    else:
        if not os.path.exists(wav):
            sh(["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "48000", wav])
        if src.lower().endswith((".mp4", ".mkv", ".webm", ".mov")):
            vid = os.path.abspath(src)
        meta = dict(id=os.path.basename(src), channel="", title=os.path.basename(src))
    return wav, (vid if os.path.exists(vid) else None), meta


def loudness(path, start=None, dur=None):
    """EBU R128 qua filter loudnorm (print_format=json)."""
    cmd = ["ffmpeg", "-hide_banner"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"]
    r = sh(cmd)
    m = re.findall(r"\{[^{}]*input_i[^{}]*\}", r.stderr, re.S)
    if not m:
        return {}
    d = json.loads(m[-1])
    return {"I": float(d["input_i"]), "LRA": float(d["input_lra"]),
            "TP": float(d["input_tp"]), "thresh": float(d["input_thresh"])}


def envelope(wav):
    """Doc wav -> mang dBFS RMS moi HOP giay (mono 16k)."""
    r = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", wav, "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    n = int(16000 * HOP)
    trim = len(x) - len(x) % n
    fr = x[:trim].reshape(-1, n)
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms), len(x) / 16000.0


def split_speech(db):
    """Nguong thich nghi -> mat na dang noi + danh sach pause (start, dur)."""
    top = np.percentile(db, 90)
    th = top - 18.0
    voiced = db > th
    pauses, i, n = [], 0, len(voiced)
    while i < n:
        if not voiced[i]:
            j = i
            while j < n and not voiced[j]:
                j += 1
            d = (j - i) * HOP
            if d >= MIN_PAUSE:
                pauses.append((round(i * HOP, 2), round(d, 2)))
            i = j
        else:
            i += 1
    return voiced, th, top, pauses


def transcribe(wav, model_size="small"):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _info = model.transcribe(wav, language="vi", vad_filter=False,
                                   word_timestamps=True)
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2),
                    "text": s.text.strip(),
                    "words": [{"w": w.word.strip(), "s": round(w.start, 2),
                               "e": round(w.end, 2)} for w in (s.words or [])]})
    return out


def syllables(text):
    """Tieng Viet: moi am tiet la mot 'tu' cach nhau bang khoang trang."""
    t = re.sub(r"[^\w\sÀ-ỹ]", " ", text)
    return len([w for w in t.split() if w])


def scenes(video, upto=None):
    if not video:
        return []
    cmd = ["ffmpeg", "-hide_banner"]
    if upto:
        cmd += ["-t", str(upto)]
    cmd += ["-i", video, "-vf", f"select='gt(scene,{SCENE_TH})',metadata=print",
            "-an", "-f", "null", "-"]
    r = sh(cmd)
    return [round(float(m), 2)
            for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


def dump_frames(video, times, outdir):
    os.makedirs(outdir, exist_ok=True)
    for i, t in enumerate(times):
        p = os.path.join(outdir, f"{i:02d}_{t:07.2f}s.jpg")
        sh(["ffmpeg", "-y", "-v", "quiet", "-ss", str(t), "-i", video,
            "-frames:v", "1", "-vf", "scale=640:-1", p])


def window_stats(db, voiced, pauses, segs, t0, t1):
    a, b = int(t0 / HOP), int(t1 / HOP)
    w_db, w_v = db[a:b], voiced[a:b]
    syl = 0
    for s in segs:
        for wd in s["words"]:
            if t0 <= wd["s"] < t1:
                syl += syllables(wd["w"])
    p = [x for x in pauses if t0 <= x[0] < t1]
    speak = float(w_v.sum()) * HOP
    return {
        "tu": t0, "den": t1,
        "am_tiet": syl,
        "am_tiet_phut": round(syl / ((t1 - t0) / 60.0), 1) if t1 > t0 else 0,
        "am_tiet_phut_khi_noi": round(syl / (speak / 60.0), 1) if speak > 0.5 else 0,
        "ti_le_im_lang": round(1 - speak / (t1 - t0), 3) if t1 > t0 else 0,
        "so_pause": len(p),
        "pause_dai_nhat": max([x[1] for x in p], default=0.0),
        "db_khi_noi": round(float(np.median(w_db[w_v])), 1) if w_v.any() else None,
        "db_khi_im": round(float(np.median(w_db[~w_v])), 1) if (~w_v).any() else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="URL youtube hoac file audio/video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--no-transcribe", action="store_true")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    wav, video, meta = ensure_media(args.src, out)
    print(f"audio: {wav}\nvideo: {video}")

    db, dur = envelope(wav)
    voiced, th, top, pauses = split_speech(db)
    ln = loudness(wav)
    segs = [] if args.no_transcribe else transcribe(wav, args.model)
    if segs:
        json.dump(segs, open(os.path.join(out, "transcript.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=1)

    speak_s = float(voiced.sum()) * HOP
    total_syl = sum(syllables(s["text"]) for s in segs)
    pd = np.array([p[1] for p in pauses]) if pauses else np.array([0.0])
    cuts = scenes(video)
    holds = np.diff([0.0] + cuts) if cuts else np.array([])

    data = {
        "meta": meta,
        "thoi_luong_s": round(dur, 1),
        "loudness": ln,
        "nguong_dB": round(float(th), 1),
        "giong": {
            "db_median_khi_noi": round(float(np.median(db[voiced])), 1),
            "db_p10_khi_noi": round(float(np.percentile(db[voiced], 10)), 1),
            "db_p90_khi_noi": round(float(np.percentile(db[voiced], 90)), 1),
            "dai_dong_noi_bo_dB": round(float(np.percentile(db[voiced], 90)
                                              - np.percentile(db[voiced], 10)), 1),
        },
        "nhac_nen": {
            "db_median_trong_pause": round(float(np.median(db[~voiced])), 1),
            "chenh_voice_tru_nhac_dB": round(float(np.median(db[voiced])
                                                   - np.median(db[~voiced])), 1),
        },
        "ngat_nghi": {
            "so_pause": len(pauses),
            "pause_moi_phut": round(len(pauses) / (dur / 60.0), 1),
            "median_s": round(float(np.median(pd)), 2),
            "p90_s": round(float(np.percentile(pd, 90)), 2),
            "dai_nhat_s": round(float(pd.max()), 2),
            "ti_le_im_lang": round(1 - speak_s / dur, 3),
            "top10_pause_dai": sorted(pauses, key=lambda x: -x[1])[:10],
        },
        "toc_do": {
            "tong_am_tiet": total_syl,
            "am_tiet_phut_gop": round(total_syl / (dur / 60.0), 1),
            "am_tiet_phut_khi_noi": round(total_syl / (speak_s / 60.0), 1)
            if speak_s else 0,
        },
        "mo_dau": {
            "5s": window_stats(db, voiced, pauses, segs, 0, 5),
            "30s": window_stats(db, voiced, pauses, segs, 0, 30),
            "moc_vao_loi_s": round(segs[0]["words"][0]["s"], 2)
            if segs and segs[0]["words"] else None,
            "cau_dau": segs[0]["text"] if segs else None,
            "loudness_5s": loudness(wav, 0, 5),
            "loudness_30s": loudness(wav, 0, 30),
            "cat_canh_5s": [c for c in cuts if c <= 5],
            "cat_canh_30s": [c for c in cuts if c <= 30],
        },
        "theo_phut": [window_stats(db, voiced, pauses, segs, t, min(t + 60, dur))
                      for t in range(0, int(dur), 60)],
        "hinh_anh": {
            "so_cat_canh": len(cuts),
            "cat_moi_phut": round(len(cuts) / (dur / 60.0), 1) if cuts else 0,
            "giu_hinh_median_s": round(float(np.median(holds)), 2) if len(holds) else None,
            "giu_hinh_p90_s": round(float(np.percentile(holds, 90)), 2) if len(holds) else None,
            "moc_cat": cuts,
        },
    }
    json.dump(data, open(os.path.join(out, "voice.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    if video and cuts:
        dump_frames(video, [c + 0.4 for c in cuts if c <= 60][:20],
                    os.path.join(out, "frames"))

    write_report(data, segs, out)
    print(f"xong -> {os.path.join(out, 'report.md')}")


def write_report(d, segs, out):
    g, nn, ng, td, mo = (d["giong"], d["nhac_nen"], d["ngat_nghi"],
                         d["toc_do"], d["mo_dau"])
    L = ["# Do dac giong doc — " + (d["meta"].get("title") or ""),
         "", f"Kenh: {d['meta'].get('channel','')}  |  "
         f"Thoi luong: {d['thoi_luong_s']}s  |  View: {d['meta'].get('views','')}",
         "", "## Tong the", "",
         "| Chi so | Gia tri |", "|---|---|",
         f"| Integrated | {d['loudness'].get('I')} LUFS |",
         f"| LRA | {d['loudness'].get('LRA')} LU |",
         f"| True peak | {d['loudness'].get('TP')} dBTP |",
         f"| dB giong (median) | {g['db_median_khi_noi']} dBFS |",
         f"| Dai dong noi bo giong (p90-p10) | {g['dai_dong_noi_bo_dB']} dB |",
         f"| dB nhac nen (trong pause) | {nn['db_median_trong_pause']} dBFS |",
         f"| Chenh giong - nhac | {nn['chenh_voice_tru_nhac_dB']} dB |",
         f"| Toc do gop | {td['am_tiet_phut_gop']} am tiet/phut |",
         f"| Toc do khi dang noi | {td['am_tiet_phut_khi_noi']} am tiet/phut |",
         f"| Pause/phut | {ng['pause_moi_phut']} |",
         f"| Pause median / p90 / max | {ng['median_s']}s / {ng['p90_s']}s / {ng['dai_nhat_s']}s |",
         f"| Ti le im lang | {ng['ti_le_im_lang']*100:.1f}% |",
         f"| Cat canh | {d['hinh_anh']['so_cat_canh']} lan, "
         f"{d['hinh_anh']['cat_moi_phut']}/phut, giu hinh median "
         f"{d['hinh_anh']['giu_hinh_median_s']}s |",
         "", "## Mo dau", "",
         f"- Vao loi o giay **{mo['moc_vao_loi_s']}**",
         f"- Cau dau: {mo['cau_dau']}",
         f"- 5s dau: {mo['5s']['am_tiet']} am tiet "
         f"({mo['5s']['am_tiet_phut']}/phut), {mo['5s']['so_pause']} pause, "
         f"{mo['loudness_5s'].get('I')} LUFS, cat canh {len(mo['cat_canh_5s'])}",
         f"- 30s dau: {mo['30s']['am_tiet']} am tiet "
         f"({mo['30s']['am_tiet_phut']}/phut), {mo['30s']['so_pause']} pause, "
         f"{mo['loudness_30s'].get('I')} LUFS, cat canh {len(mo['cat_canh_30s'])}",
         "", "## Theo tung phut", "",
         "| Phut | am tiet/phut | pause | im lang | dB giong | dB nhac |",
         "|---|---|---|---|---|---|"]
    for i, w in enumerate(d["theo_phut"]):
        L.append(f"| {i+1} | {w['am_tiet_phut']} | {w['so_pause']} | "
                 f"{w['ti_le_im_lang']*100:.0f}% | {w['db_khi_noi']} | "
                 f"{w['db_khi_im']} |")
    if segs:
        L += ["", "## 30 giay dau — loi doc", ""]
        for s in segs:
            if s["start"] > 30:
                break
            L.append(f"- `{s['start']:05.2f}` {s['text']}")
    open(os.path.join(out, "report.md"), "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
