"""
fetch.py — Tai video nguon tu clip-manifest.json, cat dung [in,out].

Quy trinh moi clip:
  1. yt-dlp tai toan bo video -> build/raw/<vid>.mp4 (skip neu da co)
  2. ffmpeg cat [in,out] -> assets/clips/clip-<id>.mp4 (skip neu da co)

Cache bang video id de nhieu clip cung 1 video chi tai 1 lan.
Clip co URL khong tai duoc (x.com, facebook) -> warn, bo qua.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from manifest import load_manifest, is_skippable, extract_video_id  # noqa: E402


def _run(cmd, timeout=None):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"lenh that bai: {' '.join(cmd)}\n{r.stderr[-1000:]}")
    return r


def download_video(root, url, raw_dir):
    vid = extract_video_id(url)
    if not vid:
        return None
    os.makedirs(raw_dir, exist_ok=True)
    out = os.path.join(raw_dir, f"{vid}.mp4")
    if os.path.exists(out):
        return out
    print(f"  download {vid} ...")
    cmd = [
        "yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format", "mp4", "-o", out, url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  WARN khong tai duoc {url}: {r.stderr[-400:]}".strip())
        return None
    return out if os.path.exists(out) else None


def cut_clip(root, src, cin, cout, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    dur = max(0.5, cout - cin)
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{cin:.3f}", "-i", src,
           "-t", f"{dur:.3f}", "-c:v", "libx264", "-crf", "18",
           "-preset", "fast", "-c:a", "aac", "-b:a", "192k",
           "-ar", "48000", out_path]
    _run(cmd)


def _align_clip(root, c):
    """Dich in ve dau cau + keo out den cuoi cau (tranh cat giua).

    Tra ve (in, out) da chinh. Neu khong co transcript / khong can -> giu.
    """
    if not c.get("align"):
        return c["in"], c["out"]
    from transcript import fetch_transcript, align_in, align_out
    vid = extract_video_id(c["url"])
    if not vid:
        return c["in"], c["out"]
    segs = fetch_transcript(root, vid, c["url"])
    new_in, _, aligned = align_in(segs, c["in"])
    new_out = align_out(segs, c["out"])
    if aligned or new_out != c["out"]:
        print(f"  align clip {c['id']}: in {c['in']:.0f}->{new_in:.0f}s "
              f"out {c['out']:.0f}->{new_out:.0f}s")
    return new_in, new_out


def fetch(root, force=False):
    clips = load_manifest(root)
    if not clips:
        print("(rong) khong co clip-manifest.json hoac manifest rong")
        return 0
    raw_dir = os.path.join(root, "build", "raw")
    clips_dir = os.path.join(root, "assets", "clips")
    ok, skipped = 0, 0
    for c in clips:
        if is_skippable(c["url"]):
            print(f"clip {c['id']}: SKIP (khong tai duoc) {c['url']}")
            skipped += 1
            continue
        out = os.path.join(clips_dir, f"clip-{c['id']}.mp4")
        if os.path.exists(out) and not force:
            print(f"clip {c['id']}: da co {os.path.basename(out)}")
            ok += 1
            continue
        src = download_video(root, c["url"], raw_dir)
        if not src:
            skipped += 1
            continue
        try:
            cin, cout = _align_clip(root, c)
            cut_clip(root, src, cin, cout, out)
            print(f"clip {c['id']}: {cin:.0f}-{cout:.0f}s -> {os.path.relpath(out, root)}")
            ok += 1
        except SystemExit as e:
            print(f"  WARN clip {c['id']}: {e}")
            skipped += 1
    print(f"\nfetch xong: {ok} ok, {skipped} skip/warn")
    return ok


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "videos/test-60s"
    fetch(root)
