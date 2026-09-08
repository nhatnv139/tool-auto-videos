"""
music.py — Nhac nen placeholder (sine chord + tremolo) de test pipeline.

Nhap nhac that (Epidemic Sound) vao assets/music/ truoc khi dang; dunging
sidechaincompress tu dong trong assemble ha nhac khi co tieng noi.
"""
import argparse
import os
import subprocess

CHORD = {
    "Dm": [146.83, 174.61, 220.00],
    "Am": [110.00, 130.81, 164.81],
    "C":  [130.81, 164.81, 196.00],
    "Em": [82.41, 123.47, 164.81],
}


def placeholder(out, dur, root="Dm", level=0.13):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    freqs = CHORD[root]
    ins, chains = [], []
    for i, f in enumerate(freqs):
        label = f"s{i}"
        ins += ["-f", "lavfi", "-i",
                f"sine=frequency={f}:sample_rate=48000:duration={dur}"]
        chains.append(
            f"[{i}:a]volume={level},lowpass=f=420,"
            f"afade=t=in:st=0:d=2.0,afade=t=out:st={dur-3.0:.1f}:d=2.0[{label}]")
    mix = "".join(f"[{l}]" for l in [f"s{i}" for i in range(len(freqs))])
    chains.append(f"{mix}amix=inputs={len(freqs)}:normalize=0,"
                  f"tremolo=f=0.15:d=0.45,highpass=f=55[aout]")
    cmd = ["ffmpeg", "-y", *ins, "-filter_complex", ";".join(chains),
           "-map", "[aout]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"sinh nhac loi:\n{r.stderr[-1000:]}")
    print(f"OK  {out}  ({dur}s, ton {root}, level {level})")


def scan(music_dir):
    exts = (".mp3", ".wav", ".flac", ".m4a")
    hits = []
    if os.path.isdir(music_dir):
        for name in sorted(os.listdir(music_dir)):
            if name.lower().endswith(exts):
                hits.append(name)
    if not hits:
        print(f"(rong) {music_dir} — chay music de sinh placeholder hoac bo file vao")
    else:
        for h in hits:
            print(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="videos/test-60s/assets/music/bed.wav")
    ap.add_argument("--dur", type=float, default=120.0)
    ap.add_argument("--root", choices=list(CHORD), default="Dm")
    ap.add_argument("--scan", metavar="DIR")
    args = ap.parse_args()
    if args.scan:
        scan(args.scan)
    else:
        placeholder(args.out, args.dur, args.root)


if __name__ == "__main__":
    main()
