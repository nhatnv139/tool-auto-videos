"""
transcript.py — Cache transcript video nguon (yt-script cho YouTube,
faster-whisper cho nguon khac: Bilibili, Douyin...).

Import truc tiep app.py cua yt-script de lay RAW segments (mien min, co
start/dur) cho YouTube. Nguon khong phai YouTube -> gio bang faster-whisper
tu build/raw/<vid>.mp4. Cache vao build/transcript/<video_id>.json.

Dung cho:
  - align cau: dich timestamp cua clip ve dau manh transcript (fetch)
  - Mode B (quote -> tim timestamp)
"""
import json
import importlib.util
import os
import sys

from manifest import detect_src_type, extract_video_id

# Optional: yt-script local server cho transcript YouTube chinh xac (align auto,
# search). Neu khong cai, dat YT_SCRIPT_PATH="" hoac de trong -> fetch van chay
# duoc vi manifest mac dinh dung align:false; chi mat chuc nang align tu dong.
YT_SCRIPT = os.environ.get("YT_SCRIPT_PATH", "")
_yt_app = None


def _load_yt_app():
    global _yt_app
    if _yt_app is not None:
        return _yt_app
    if not YT_SCRIPT or not os.path.exists(YT_SCRIPT):
        raise SystemExit(
            "Thieu yt-script (YT_SCRIPT_PATH). Cai theo docs/02-research.md hoac "
            "de align:false trong clip-manifest.")
    spec = importlib.util.spec_from_file_location("yt_app", YT_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["yt_app"] = mod
    spec.loader.exec_module(mod)
    _yt_app = mod
    return _yt_app


def cache_path(root, video_id):
    d = os.path.join(root, "build", "transcript")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{video_id}.json")


def _whisper_transcribe(root, video_id, url):
    """Gio bang faster-whisper tu build/raw/<vid>.mp4. Tra ve segments."""
    raw = os.path.join(root, "build", "raw", f"{video_id}.mp4")
    if not os.path.exists(raw):
        from fetch import download_video
        raw = download_video(root, url, os.path.join(root, "build", "raw"))
        if not raw:
            return None
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    chunks, _ = model.transcribe(raw, vad_filter=True)
    return [{"start": c.start, "dur": c.end - c.start, "text": c.text.strip()}
            for c in chunks if c.text.strip()]


def fetch_transcript(root, video_id, url, force=False):
    """Lay transcript (list {start, dur, text}) — co cache. None neu khong co."""
    path = cache_path(root, video_id)
    if os.path.exists(path) and not force:
        data = json.load(open(path, encoding="utf-8"))
        return data.get("segments")
    print(f"  transcript {video_id} ...")
    try:
        if detect_src_type(url) == "youtube":
            app = _load_yt_app()
            data = app.get_transcript(url, None, None)
            segments = [{"start": s.get("start", 0), "dur": s.get("dur", 0),
                         "text": s.get("text", "")} for s in data.get("segments", [])]
        else:
            segments = _whisper_transcribe(root, video_id, url)
    except Exception as e:
        print(f"  WARN khong lay duoc transcript {video_id}: {str(e)[:200]}")
        json.dump({"segments": None}, open(path, "w", encoding="utf-8"))
        return None
    if not segments:
        json.dump({"segments": None}, open(path, "w", encoding="utf-8"))
        return None
    json.dump({"segments": segments}, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return segments


def sentence_boundaries(segments):
    """Uoc luong moc cuoi cau (period) tu cac manh transcript.

    Mo manh: tach text theo dau cau (. ! ?), phan phoi duration theo ti le tu.
    Tra ve list cac moc (time) la CUOI cau.
    """
    import re
    marks = []
    for s in segments:
        text = s.get("text", "")
        dur = s.get("dur") or 8.0
        start = s["start"]
        words = text.split()
        if not words:
            continue
        per = dur / len(words)
        pos = 0.0
        for w in words:
            pos += per
            if w.endswith((".", "!", "?", "!", "?")) or \
                    any(p in w for p in (".", "!", "?")):
                marks.append(round(start + pos, 2))
    return marks


def _near_back(marks, t, tol=2.0):
    """Tim moc cuoi cau gan nhat o TRUOC t trong pham vi tol."""
    best = None
    for m in marks:
        if m < t and (best is None or m > best):
            best = m
    return best if (best is not None and t - best <= tol) else None


def _near_forward(marks, t, tol=8.0):
    """Tim moc cuoi cau gan nhat o SAU t trong pham vi tol."""
    best = None
    for m in marks:
        if m > t + 0.3 and (best is None or m < best):
            best = m
    return best if (best is not None and best - t <= tol) else None


def align_in(segments, cin, max_shift=8.0, margin=0.2):
    """Dich cin ve dau cau (moc cuoi cau truoc + 1 tu) neu dang giua cau."""
    if not segments:
        return cin, None, False
    marks = sentence_boundaries(segments)
    prev_end = _near_back(marks, cin, tol=max_shift)
    if prev_end is not None:
        # dau cau moi = moc cuoi cau truoc + le nho (dau tu moi)
        return round(prev_end + margin, 2), None, True
    return cin, None, False


def align_out(segments, cout, max_extend=14.0):
    """Keo cout den CUOI cau (dau cau gan nhat sau cout), tranh cat giua cau."""
    if not segments:
        return cout
    marks = sentence_boundaries(segments)
    # neu cout dang ngay sau mot moc cuoi cau (vua moi cau bat dau) -> giu nguyen
    near_back = _near_back(marks, cout, tol=1.0)
    if near_back is not None:
        return cout
    nxt = _near_forward(marks, cout, tol=max_extend)
    if nxt is not None:
        return round(nxt, 2)
    return cout
