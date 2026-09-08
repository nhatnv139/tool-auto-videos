"""
probe.py — ffprobe helpers (dur, stream info).
"""
import json
import shutil
import subprocess


def ffprobe(path):
    exe = shutil.which("ffprobe")
    if not exe:
        raise SystemExit("khong thay ffprobe trong PATH")
    r = subprocess.run(
        [exe, "-v", "error", "-print_format", "json",
         "-show_entries", "format=duration:stream=codec_type,width,height,codec_name",
         path], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ffprobe loi {path}:\n{r.stderr[-800:]}")
    return json.loads(r.stdout)


def duration(path):
    d = ffprobe(path)
    v = d.get("format", {}).get("duration")
    if v is None:
        raise SystemExit(f"khong doc duoc duration cua {path}")
    return float(v)


def streams(path):
    d = ffprobe(path)
    out = {"video": None, "audio": None}
    for s in d.get("streams", []):
        t = s.get("codec_type")
        if t == "video" and out["video"] is None:
            out["video"] = dict(w=s.get("width"), h=s.get("height"),
                                codec=s.get("codec_name"))
        elif t == "audio" and out["audio"] is None:
            out["audio"] = dict(codec=s.get("codec_name"))
    return out
