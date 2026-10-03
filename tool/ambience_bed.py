"""ambience_bed.py — Dung nen khong khi cho video truyen van hoa.

Vi sao can: `music.placeholder()` chi la ba song sine + tremolo. Nghe tren mot
video 20 phut ke chuyen su thi no khong phai nhac, no la tieng u u cua may. Con
de trong hoan toan thi cac cell card thanh khoang chet (loi da gap o video
chu-nguyen-chuong truoc: 9 cell card = 9 khoang chet 4,5 giay).

Giai phap: mot lop GIO lap lien tuc (tu SFX Mixkit) tron duoi mot lop DRONE tram
(sine loc thap). Gio cho khong gian, drone cho suc nang. Co y KHONG dung
chim/nuoc/con trung trong AMBIENCE cua sfx.py — chung hop canh lang que, khong
hop mot video ve kho luu tru va bo may nha nuoc.

    python tool/ambience_bed.py videos/<case> --dur 1300
    python tool/ambience_bed.py videos/<case> --dur 1300 --drone Em
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sfx as SFX  # noqa: E402

# Chi lay lop gio. 'gio-trong' la gio hun hut (khong gian rong, lanh),
# 'gio-tan-la' nhe hon, dung de pha cam giac lap cua lop kia.
WIND = ["gio-trong", "gio-tan-la"]

# Drone tram: quang nam rong, khong co quang ba nen khong "vui" cung khong
# "buon" — de duoi loi ke ma khong ap dat cam xuc.
DRONE = {
    "Dm": [73.42, 110.00, 146.83],
    "Em": [82.41, 123.47, 164.81],
    "Am": [55.00, 82.41, 110.00],
}


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def build(root, dur, drone="Dm", wind_db=-24.0, drone_db=-30.0, layers=None):
    """layers: ten SFX trong sfx.AMBIENCE/SFX_MANIFEST (vd ["gio-trong",
    "song-nuoc"] cho canh song nuoc). Mac dinh WIND."""
    layers = [x for x in (layers or WIND) if x]
    d = SFX.sfx_dir(root)
    SFX.fetch_sfx(root, names=layers)

    srcs = [os.path.join(d, f"{n}.mp3") for n in layers]
    srcs = [p for p in srcs if os.path.exists(p) and duration(p) > 1.0]
    if not srcs:
        raise SystemExit("khong tai duoc file gio nao — kiem tra mang")

    ins, chains, labels = [], [], []
    for i, p in enumerate(srcs):
        # Moi lop gio: lap vo han, cat dung do dai, fade hai dau. Lop thu hai
        # bi day cham mot nhip (atrim) de hai lop khong trung chu ky lap ->
        # tai khong bat duoc diem noi.
        offset = 3.7 if i else 0.0
        ins += ["-stream_loop", "-1", "-i", p]
        chains.append(
            f"[{i}:a]atrim=start={offset}:duration={dur + 1:.1f},asetpts=PTS-STARTPTS,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"volume={wind_db + (0 if i == 0 else -3.0)}dB[w{i}]")
        labels.append(f"w{i}")

    n = len(srcs)
    for j, f in enumerate(DRONE[drone]):
        k = n + j
        ins += ["-f", "lavfi", "-i",
                f"sine=frequency={f}:sample_rate=48000:duration={dur:.1f}"]
        chains.append(
            f"[{k}:a]lowpass=f=260,volume={drone_db - (j * 2.0)}dB,"
            f"aformat=channel_layouts=stereo[d{j}]")
        labels.append(f"d{j}")

    mix = "".join(f"[{x}]" for x in labels)
    chains.append(
        f"{mix}amix=inputs={len(labels)}:normalize=0,"
        f"atrim=duration={dur:.1f},"
        f"afade=t=in:st=0:d=3,afade=t=out:st={dur - 4:.1f}:d=4,"
        f"highpass=f=45[aout]")

    out = os.path.join(root, "assets", "music", "bed.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins,
                    "-filter_complex", ";".join(chains), "-map", "[aout]",
                    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out],
                   check=True)
    print(f"  -> {out}  ({duration(out):.1f}s, {len(srcs)} lop gio + drone {drone})")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--drone", default="Dm", choices=sorted(DRONE))
    ap.add_argument("--layers", default="",
                    help="lop khong khi, phan cach dau phay (vd gio-trong,song-nuoc)")
    a = ap.parse_args()
    build(os.path.abspath(a.case), a.dur, a.drone,
          layers=[x.strip() for x in a.layers.split(",") if x.strip()] or None)


if __name__ == "__main__":
    main()
