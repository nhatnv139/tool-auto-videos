"""
sfx.py — Tai kho hieu ung am thanh (SFX) mien phi tu Mixkit.

Mixkit (mixkit.co/free-sound-effects/) — mien phi dung thuong mai, khong can
attribution. Tool tai 'preview' mp3 ve assets/sfx/<ten>.mp3 (cache).

Danh sach SFX co san (manifest):
  whoosh, riser, hit, beep, pop, glitch, drone, transition

Lenh:
  python tool/run.py --case videos/<topic> sfx          # tai cac file thieu
  python tool/run.py --case videos/<topic> sfx --list   # xem gi da co
  python tool/run.py --case videos/<topic> sfx --refresh# tai lai het

Script dung: [[sfx:whoosh]] trong script.md -> cell sfx dung file nay.
"""
import json
import os
import subprocess
import sys
import urllib.request

SFX_MANIFEST = {
    "whoosh":     "https://assets.mixkit.co/active_storage/sfx/1489/1489-preview.mp3",
    "riser":      "https://assets.mixkit.co/active_storage/sfx/790/790-preview.mp3",
    "hit":        "https://assets.mixkit.co/active_storage/sfx/788/788-preview.mp3",
    "beep":       "https://assets.mixkit.co/active_storage/sfx/1083/1083-preview.mp3",
    "pop":        "https://assets.mixkit.co/active_storage/sfx/2358/2358-preview.mp3",
    "glitch":     "https://assets.mixkit.co/active_storage/sfx/2595/2595-preview.mp3",
    "drone":      "https://assets.mixkit.co/active_storage/sfx/2744/2744-preview.mp3",
    "transition": "https://assets.mixkit.co/active_storage/sfx/1492/1492-preview.mp3",
    "click":      "https://assets.mixkit.co/active_storage/sfx/1133/1133-preview.mp3",
    "notification": "https://assets.mixkit.co/active_storage/sfx/2870/2870-preview.mp3",
    "alarm":      "https://assets.mixkit.co/active_storage/sfx/995/995-preview.mp3",
    "swoosh":     "https://assets.mixkit.co/active_storage/sfx/166/166-preview.mp3",
    "horror":     "https://assets.mixkit.co/active_storage/sfx/1143/1143-preview.mp3",
    "tension":    "https://assets.mixkit.co/active_storage/sfx/577/577-preview.mp3",
    "science-fiction": "https://assets.mixkit.co/active_storage/sfx/238/238-preview.mp3",
    "machine":    "https://assets.mixkit.co/active_storage/sfx/1092/1092-preview.mp3",
    "keyboard":   "https://assets.mixkit.co/active_storage/sfx/1386/1386-preview.mp3",
    "impact":     "https://assets.mixkit.co/active_storage/sfx/1143/1143-preview.mp3",
    "boom":       "https://assets.mixkit.co/active_storage/sfx/2902/2902-preview.mp3",
    "punch":      "https://assets.mixkit.co/active_storage/sfx/2198/2198-preview.mp3",
    "rising":     "https://assets.mixkit.co/active_storage/sfx/691/691-preview.mp3",
    "cinematic-hit": "https://assets.mixkit.co/active_storage/sfx/677/677-preview.mp3",
    "digital":    "https://assets.mixkit.co/active_storage/sfx/992/992-preview.mp3",
    "ui":         "https://assets.mixkit.co/active_storage/sfx/2619/2619-preview.mp3",
    "glitch-whoosh": "https://assets.mixkit.co/active_storage/sfx/2596/2596-preview.mp3",
    "cinematic-boom": "https://assets.mixkit.co/active_storage/sfx/1286/1286-preview.mp3",
    "hit-impact": "https://assets.mixkit.co/active_storage/sfx/2148/2148-preview.mp3",

    # --- khong khi thien nhien / lang que -------------------------------------
    # Cho video truyen van hoa Viet: bo tren khong hop: whoosh/glitch/beep la
    # ngon ngu video cong nghe. Canh lang can gio qua tan la, chim, la kho, song.
    "gio-tan-la":   "https://assets.mixkit.co/active_storage/sfx/2427/2427-preview.mp3",
    "chim-sang":    "https://assets.mixkit.co/active_storage/sfx/2472/2472-preview.mp3",
    "dem-con-trung": "https://assets.mixkit.co/active_storage/sfx/2414/2414-preview.mp3",
    "la-kho":       "https://assets.mixkit.co/active_storage/sfx/2428/2428-preview.mp3",
    "song-nuoc":    "https://assets.mixkit.co/active_storage/sfx/2452/2452-preview.mp3",
    "gio-trong":    "https://assets.mixkit.co/active_storage/sfx/2658/2658-preview.mp3",
    "chim-hot":     "https://assets.mixkit.co/active_storage/sfx/2432/2432-preview.mp3",
    "mua-nhe":      "https://assets.mixkit.co/active_storage/sfx/2393/2393-preview.mp3",
    "mua-rung":     "https://assets.mixkit.co/active_storage/sfx/2396/2396-preview.mp3",
    "sam":          "https://assets.mixkit.co/active_storage/sfx/2405/2405-preview.mp3",

    # --- chuyen chuong --------------------------------------------------------
    "chuong-tram":  "https://assets.mixkit.co/active_storage/sfx/623/623-preview.mp3",
    "chuong-ngan":  "https://assets.mixkit.co/active_storage/sfx/3109/3109-preview.mp3",
    "chuong-manh":  "https://assets.mixkit.co/active_storage/sfx/619/619-preview.mp3",
}

# Lop khong khi nen (ambience) — chay duoi suot ca video, khac voi SFX mot phat.
AMBIENCE = ["gio-tan-la", "chim-sang", "dem-con-trung", "gio-trong", "song-nuoc"]


def sfx_dir(root):
    d = os.path.join(root, "assets", "sfx")
    os.makedirs(d, exist_ok=True)
    return d


def _normalize(path):
    """Chuan hoa am luong ve -16 LUFS (khong choi/gay giua video)."""
    tmp = path + ".norm.mp3"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", path,
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "libmp3lame",
         "-b:a", "192k", tmp], capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(tmp):
        os.replace(tmp, path)
        return True
    return False


def fetch_sfx(root, names=None, refresh=False, force_all=False):
    """Tai SFX thieu + normalize. Tra ve so file da tai."""
    d = sfx_dir(root)
    targets = names if names else list(SFX_MANIFEST)
    n = 0
    for name in targets:
        if name not in SFX_MANIFEST:
            print(f"  WARN sfx '{name}' khong co trong manifest "
                  f"({sorted(SFX_MANIFEST)})")
            continue
        out = os.path.join(d, f"{name}.mp3")
        if os.path.exists(out) and not refresh and not force_all:
            print(f"  {name}: da co")
            continue
        url = SFX_MANIFEST[name]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            tmp = out + ".part"
            with urllib.request.urlopen(req, timeout=60) as r:
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            os.replace(tmp, out)
            _normalize(out)
            kb = os.path.getsize(out) // 1024
            print(f"  tai {name}: {kb} KB (normalized)")
            n += 1
        except Exception as e:
            print(f"  WARN tai {name} that bai: {e}")
    return n


def list_sfx(root):
    d = sfx_dir(root)
    for name in sorted(SFX_MANIFEST):
        p = os.path.join(d, f"{name}.mp3")
        print(f"  {name}: {'OK' if os.path.exists(p) else 'chua co'}")


def sfx_file(root, name):
    """Tra ve duong dan file sfx (hoac None)."""
    if name not in SFX_MANIFEST:
        return None
    p = os.path.join(root, "assets", "sfx", f"{name}.mp3")
    return p if os.path.exists(p) else None


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--only", nargs="*", help="chi tai cac ten nay")
    args = ap.parse_args()

    root = os.path.abspath(args.case)
    if args.list:
        list_sfx(root)
    else:
        n = fetch_sfx(root, names=args.only, refresh=args.refresh)
        print(f"SFX xong: {n} file tai")


if __name__ == "__main__":
    main()
