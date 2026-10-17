"""music_lib.py — Nen nhac THAT tu thu vien assets/music_lib (16/10/2026).

Thay cho `nhac: ambience` (gio + drone tu sinh, nguoi xem nghe "nhat"). Dung:

    python tool/music_lib.py videos/<case> --dur 900 --seed <slug> [--tags epic,bi-an]

- Chon bai trong assets/music_lib theo the (manifest.json `tag`, hoac tien to
  ten file: epic-, bi-an-, buon-, a-dong-). Thu tu xao theo --seed (slug) nen
  dung lai cho ket qua y het, hai video lien nhau khong cung mot bai mo dau.
- Doi bai O DIEM CHUYEN CHUONG (cell co "chuong" trong config.json, xem
  script2config --chuong cat): moi chuong mot bai, cheo nhau 2,5s. Khong co
  chuong thi noi bai lien tiep, moi bai toi da --max-bai giay.
- Moi bai duoc chuan ve -16 LUFS (cung muc voi giong doc da chuan trong tts),
  nen assemble tinh duck bang "dB duoi giong" la dung.
- Ghi assets/music/bed.wav + bed.json (env=true -> assemble dung duong bao
  gain thay cho sidechaincompress) + music-credits.json (dong ghi cong cho mo
  ta YouTube — nhac CC-BY bat buoc ghi).
"""
import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(KIT, "assets", "music_lib")
sys.path.insert(0, os.path.join(KIT, "tool"))
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".m4a", ".flac")
TAGS = ("epic", "bi-an", "buon", "a-dong")
LUFS = -16.0


def _dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr or "")
    return float(m[-1]) if m else None


def _lufs_doan(path, off, dur):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{off:.2f}",
                        "-t", f"{dur:.2f}", "-i", path, "-af", "ebur128",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr or "")
    try:
        v = float(m[-1]) if m else None
    except ValueError:
        return None
    return v if v is not None and v > -60 else None


def _tag_of(fn):
    for t in sorted(TAGS, key=len, reverse=True):
        if fn.lower().startswith(t + "-"):
            return t
    return ""


def thu_vien(lib=LIB):
    """Danh sach bai: [{file, path, tag, title, author, attribution, license}]."""
    items = {}
    man = os.path.join(lib, "manifest.json")
    if os.path.exists(man):
        try:
            for it in json.load(open(man, encoding="utf-8")):
                p = os.path.join(lib, it["file"])
                if os.path.exists(p):
                    items[it["file"]] = dict(it, path=p,
                                             tag=it.get("tag") or _tag_of(it["file"]))
        except Exception as e:
            print(f"  WARN manifest.json loi: {e}")
    if os.path.isdir(lib):
        for fn in sorted(os.listdir(lib)):
            if fn.lower().endswith(AUDIO_EXT) and fn not in items:
                items[fn] = {"file": fn, "path": os.path.join(lib, fn),
                             "tag": _tag_of(fn), "title": os.path.splitext(fn)[0]}
    return list(items.values())


def _lufs_cache(lib=LIB):
    p = os.path.join(lib, ".lufs.json")
    try:
        return p, json.load(open(p, encoding="utf-8"))
    except Exception:
        return p, {}


def chuong_moc(case):
    """Moc giay cac diem chuyen chuong, tinh nhu assemble.plan."""
    try:
        import config as CFG
        import assemble as AS
        cfg = CFG.load(case)
        rows, total, _ = AS.plan(case, cfg, strict=False)
    except (SystemExit, Exception) as e:
        print(f"  (khong tinh duoc moc chuong: {e}) -> noi bai lien tiep")
        return [], None
    return [r["start"] for r in rows if r["cell"].get("chuong")], total


def build(case, dur, seed="", tags="", duoi_giong=7.0, max_bai=240.0,
          xf=2.5, lib=LIB):
    case = os.path.abspath(case)
    bai = thu_vien(lib)
    if not tags:
        # mac dinh chi xoay 4 the kenh su; bai the khac (vd kinh-di) phai goi ten
        bai = [b for b in bai if b.get("tag") in TAGS] or bai
    if tags:
        want = [t.strip() for t in tags.split(",") if t.strip()]
        loc = [b for b in bai if b.get("tag") in want]
        if loc:
            bai = loc
        else:
            print(f"  WARN khong co bai the {want} -> dung ca thu vien")
    if not bai:
        raise SystemExit(f"thu vien nhac rong: {lib}")
    rnd = random.Random(int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16))
    rnd.shuffle(bai)

    cache_p, cache = _lufs_cache(lib)
    for b in bai:
        key = f"{b['file']}|{os.path.getsize(b['path'])}"
        if key not in cache:
            cache[key] = {"I": _lufs(b["path"]), "dur": _dur(b["path"])}
        b["I"], b["dur"] = cache[key]["I"], cache[key]["dur"]
    try:
        json.dump(cache, open(cache_p, "w", encoding="utf-8"), indent=1)
    except OSError:
        pass

    moc, _total = chuong_moc(case)
    # doan: [0, ch1), [ch1, ch2) ... [chN, dur). Doan qua dai (> max_bai, khong
    # co chuong) -> chia them de bai khong lap lai lien tuc qua lau.
    cuts = [0.0] + [m for m in moc if 5.0 < m < dur - 5.0]
    cuts = sorted(set(cuts)) + [dur]
    doan = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        n = max(1, int((b - a) // max_bai) + (1 if (b - a) % max_bai > 30 else 0))
        step = (b - a) / n
        for i in range(n):
            doan.append((a + i * step, a + (i + 1) * step))

    out_dir = os.path.join(case, "assets", "music")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "bed.wav")
    ins, fc, labs, dung = [], [], "", []
    for i, (a, b) in enumerate(doan):
        t = bai[i % len(bai)]
        L = (b - a) + (xf if i < len(doan) - 1 else 0.0)
        # Bai dai hon doan: bat dau o 0 (phan intro cua bai) — tru doan dau,
        # vao thang phan co nhac (bo 2s im/nho dau bai) cho hook co nen ngay.
        off = 2.0 if (i == 0 and t["dur"] > L + 4) else 0.0
        # Chuan loudness theo DOAN THAT SU DUNG, khong theo ca bai: intro cua bai
        # epic thuong nho hon cao trao 8-10 dB, chuan theo ca bai thi 1-2 phut
        # dau video nhac gan nhu mat (do 16/10: nhac trong khe -42,6 dBFS).
        seg_I = _lufs_doan(t["path"], off, min(L, max(1.0, t["dur"] - off)))
        ref_I = seg_I if seg_I is not None else t.get("I")
        gain = (LUFS - ref_I) if ref_I is not None else 0.0
        gain = max(-12.0, min(12.0, gain))
        ins += ["-stream_loop", "-1", "-ss", f"{off:.2f}", "-t", f"{L:.3f}", "-i", t["path"]]
        fin = 1.0 if i == 0 else xf
        ms = int(round(a * 1000))
        fc.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                  f"volume={gain:.2f}dB,afade=t=in:st=0:d={fin},"
                  f"afade=t=out:st={max(0.0, L - xf):.3f}:d={xf},"
                  f"adelay={ms}|{ms},apad,atrim=0:{dur:.3f}[m{i}]")
        labs += f"[m{i}]"
        dung.append({"tu": round(a, 1), "den": round(b, 1), "file": t["file"],
                     "title": t.get("title", ""), "tag": t.get("tag", "")})
    fc.append(f"{labs}amix=inputs={len(doan)}:normalize=0,"
              f"alimiter=limit=0.89:level=disabled[out]")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *ins,
                        "-filter_complex", ";".join(fc), "-map", "[out]",
                        "-t", f"{dur:.3f}", "-ar", "48000", "-ac", "2",
                        "-c:a", "pcm_s16le", out], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("music_lib ffmpeg loi:\n" + r.stderr[-1500:])
    spec = {"env": True, "level": 1.0, "duoi_giong": float(duoi_giong),
            "hook_them": 3.0, "hook_db": 2.0,
            # khe/chuong: nhac len them nhung khong bao gio vuot muc giong - 2 dB
            "khe_len": min(4.0, max(0.0, float(duoi_giong) - 3.0)), "khe_min": 0.6,
            "chuong_len": min(10.0, max(0.0, float(duoi_giong) - 2.0)),
            "lufs_bai": LUFS, "doan": dung}
    json.dump(spec, open(os.path.join(out_dir, "bed.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    # ghi cong — file *-credits.json duoc don_dep giu lai
    seen, credits = set(), []
    for d in dung:
        it = next((b for b in bai if b["file"] == d["file"]), {})
        if d["file"] in seen:
            continue
        seen.add(d["file"])
        credits.append({"file": d["file"], "title": it.get("title", ""),
                        "author": it.get("author", ""), "license": it.get("license", ""),
                        "url": it.get("url", ""),
                        "attribution": it.get("attribution", "")})
    json.dump(credits, open(os.path.join(case, "music-credits.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"bed: {len(doan)} doan, {len(seen)} bai, {dur:.0f}s -> {out}")
    for d in dung:
        print(f"  {d['tu']:7.1f}-{d['den']:7.1f}s  [{d['tag'] or '-'}] {d['title'] or d['file']}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--seed", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--duoi-giong", type=float, default=7.0, dest="duoi_giong",
                    help="nhac duoi giong (dB LUFS) khi dang noi; 7 -> do trong khe ~13-17 dB nhu BLV Hai Thanh")
    ap.add_argument("--max-bai", type=float, default=240.0, dest="max_bai")
    ap.add_argument("--lib", default=LIB)
    a = ap.parse_args()
    build(a.case, a.dur, a.seed, a.tags, a.duoi_giong, a.max_bai, lib=a.lib)


if __name__ == "__main__":
    main()
