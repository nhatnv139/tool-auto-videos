"""slow_voice.py — Ha nhip giong doc ve dung dich (wpm) sau khi TTS.

Vi sao can: Vbee chi cho speed_rate trong [0.7, 1.2], va rieng giong
hn_male_manhdung_full_24k-st thi tham so nay gan nhu khong an. Do thuc te:
speed_rate 1.0 -> 233 wpm, 0.84 -> 223 wpm, 0.80 -> 220 wpm. Khong the cham
hon 220 wpm bang tham so, trong khi style "truyen van hoa" can 196 wpm.

Module nay keo dai audio bang ffmpeg atempo (giu nguyen cao do giong), roi
co gian LUON timestamp trong <cell>.words.json theo dung he so — neu khong
phu de se lech dan ve cuoi video.

Dung:
    python tool/slow_voice.py videos/<case> --wpm 196
    python tool/slow_voice.py videos/<case> --wpm 196 --dry-run
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys


def duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def atempo_chain(factor):
    """atempo chi nhan 0.5-2.0 moi lan; ghep nhieu tang neu vuot nguong."""
    if factor <= 0:
        raise ValueError("factor phai > 0")
    parts, f = [], factor
    while f < 0.5:
        parts.append("atempo=0.5")
        f /= 0.5
    while f > 2.0:
        parts.append("atempo=2.0")
        f /= 2.0
    parts.append(f"atempo={f:.6f}")
    return ",".join(parts)


# Bo keo gian. rubberband (phase vocoder co giu formant, cua so ngan cho giong
# noi) nghe it "rung/vang" hon atempo (WSOLA cat-dan tung khung) khi he so
# xuong duoi ~0.92 — dung vung kieu "doan" can: Phu Thang doc ca doan noi o
# ~298 am tiet/phut (do 01/10/2026), keo ve 196 tong can he so ~0.87.
# Quay ve kieu cu: SLOW_VOICE_ENGINE=atempo.
def _co_rubberband():
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                           capture_output=True, text=True)
        return " rubberband " in r.stdout
    except Exception:
        return False


def tempo_filter(factor):
    if (os.environ.get("SLOW_VOICE_ENGINE", "rubberband") != "atempo"
            and _co_rubberband()):
        # window=short (goi y cho giong noi) lam hut 2,1 dB, mac dinh hut
        # 1,2 dB (do 01/10 tren cell Vbee, tempo 0.9) -> bu lai o bu_loudness.
        return (f"rubberband=tempo={factor:.6f}"
                f":formant=preserved:pitchq=quality")
    return atempo_chain(factor)


def _lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr or "")
    return float(m[-1]) if m else None


def bu_loudness(src_goc, dst):
    """Keo gian lam lech muc to (rubberband hut ~1-2 dB) -> tra ve dung muc
    cua ban goc, de cell da keo va chua keo khong chenh nhau."""
    a, b = _lufs(src_goc), _lufs(dst)
    if a is None or b is None or abs(a - b) < 0.3:
        return
    tmp = dst + ".vol.mp3"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", dst, "-af",
                        f"volume={a - b:.2f}dB", "-c:a", "libmp3lame",
                        "-b:a", "192k", tmp], capture_output=True, text=True)
    if r.returncode == 0:
        os.replace(tmp, dst)


_MARK_TOKEN = re.compile(r"^(/{2,4}|[|^*])$")


def dem_am_tiet(text):
    """Dem am tiet DOC THAT: bo token chi gom ky tu ngat (//, ///, |, ^, *).

    Ban cu dem ca '//' la mot tu -> tuong giong doc nhanh hon, keo cham qua tay.
    """
    return sum(1 for w in (text or "").replace("^", " ").replace("*", " ").split()
               if not _MARK_TOKEN.match(w))


def scale_words(wpath, factor):
    """Co gian moc thoi gian tu. factor < 1 = doc cham lai = moc gian ra."""
    if not os.path.exists(wpath):
        return 0
    with open(wpath, encoding="utf-8") as f:
        data = json.load(f)
    words = data.get("words") or []
    k = 1.0 / factor
    for w in words:
        for key in ("start", "end", "t", "t0", "t1", "d"):
            if key in w and isinstance(w[key], (int, float)):
                w[key] = round(w[key] * k, 4)
    with open(wpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return len(words)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--wpm", type=float, default=196.0, help="nhip dich")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-factor", type=float, default=0.75,
                    help="khong keo cham hon muc nay (tranh meo tieng)")
    args = ap.parse_args()

    root = os.path.abspath(args.case)
    vdir = os.path.join(root, "build", "voice")
    cfg = json.load(open(os.path.join(root, "config.json"), encoding="utf-8"))
    vo = {c["id"]: c["vo"] for c in cfg["cells"] if c.get("vo")}

    # Do nhip hien tai tren TOAN BO cac cell (khong lay mau), vi mot vai cell
    # ngan co the lech rat xa.
    tot_w = tot_d = 0.0
    files = []
    for cid, text in vo.items():
        p = os.path.join(vdir, f"cell-{cid}.mp3")
        if not os.path.exists(p):
            continue
        d = duration(p)
        w = dem_am_tiet(text)
        tot_w += w
        tot_d += d
        files.append((cid, p, w, d))

    if not files:
        raise SystemExit(f"khong thay file giong nao trong {vdir}")

    cur = tot_w / (tot_d / 60.0)
    factor = args.wpm / cur
    print(f"{len(files)} cell, {int(tot_w)} am tiet, {tot_d/60:.1f} phut")
    print(f"nhip hien tai {cur:.0f} wpm -> dich {args.wpm:.0f} wpm "
          f"=> atempo {factor:.4f}")

    if factor >= 0.995:
        print("da dat dich, khong can chinh.")
        return
    if factor < args.min_factor:
        print(f"CANH BAO: he so {factor:.3f} duoi nguong {args.min_factor}, "
              f"keo cham the nay se meo tieng. Kep lai o {args.min_factor}.")
        factor = args.min_factor

    if args.dry_run:
        print(f"(dry-run) se keo {len(files)} file voi atempo={factor:.4f} "
              f"-> thoi luong moi ~{tot_d/factor/60:.1f} phut")
        return

    chain = tempo_filter(factor)
    bak = os.path.join(vdir, "_pretempo")
    os.makedirs(bak, exist_ok=True)
    done = 0
    for cid, p, w, d in files:
        keep = os.path.join(bak, os.path.basename(p))
        if not os.path.exists(keep):
            shutil.copyfile(p, keep)          # giu ban goc de chay lai duoc
        tmp = p + ".tmp.mp3"
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", keep, "-filter:a", chain,
             "-c:a", "libmp3lame", "-b:a", "192k", tmp],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  LOI cell {cid}: {r.stderr[-300:]}")
            continue
        bu_loudness(keep, tmp)
        os.replace(tmp, p)
        scale_words(os.path.join(vdir, f"cell-{cid}.words.json"), factor)
        done += 1

    # Cap nhat manifest cho khop do dai moi
    mpath = os.path.join(vdir, "manifest.json")
    if os.path.exists(mpath):
        man = json.load(open(mpath, encoding="utf-8"))
        for seg in man.get("segs", []):
            p = os.path.join(vdir, seg["file"])
            if os.path.exists(p):
                seg["dur"] = round(duration(p), 3)
                seg["speech"] = round(seg["dur"], 3)
                text = vo.get(seg.get("cell"), "")
                if text:
                    seg["wpm"] = round(dem_am_tiet(text) / (seg["dur"] / 60.0), 0)
        man["slowed_atempo"] = round(factor, 4)
        json.dump(man, open(mpath, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    new_d = sum(duration(p) for _, p, _, _ in files)
    print(f"xong {done}/{len(files)} cell. Ban goc luu o {bak}")
    print(f"nhip moi: {tot_w/(new_d/60):.0f} wpm, tong {new_d/60:.1f} phut")


if __name__ == "__main__":
    main()
