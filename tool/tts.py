"""
tts.py — Sinh VO cho tung cell co 'vo' trong config.

    python tool/run.py --case videos/<topic> tts --provider edge          # free test
    python tool/run.py --case videos/<topic> tts --provider elevenlabs    # can ELEVENLABS_API_KEY

Output: build/voice/cell-<id>.mp3 + build/voice/manifest.json
edge-tts: Microsoft neural, mien phi, khong can key.
ElevenLabs: can ELEVENLABS_API_KEY, giong tu nhien hon.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys

API = "https://api.elevenlabs.io"
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_MODEL = "eleven_multilingual_v2"

# Giong edge mac dinh. Christopher thuoc lop "News, Novel" — giong doc ban tin
# the he cu, cadence deu, gan nhu khong co ngu dieu hoi thoai. Andrew thuoc lop
# "Conversation" moi, am va tu nhien hon han cho video binh luan.
EDGE_VOICE = "en-US-AndrewMultilingualNeural"

TICKS = 10_000_000      # edge-tts tra offset/duration theo 100ns

# Cat khoang lang edge-tts tu chen o dau (~0.15s) va cuoi (~0.35-0.90s) moi cau.
TRIM_AF = ("silenceremove=start_periods=1:start_duration=0:"
           "start_threshold=-45dB:detection=peak,areverse,"
           "silenceremove=start_periods=1:start_duration=0:"
           "start_threshold=-45dB:detection=peak,areverse")

# Khoang lang CHU DONG sau moi cau, theo dau ket cau. edge-tts phan ung rat yeu
# voi dau cau (do thuc te: chenh lech chi ~0.3s giua co va khong co dau), nen
# nhip phai do minh chen chu khong the trong cho TTS tu ngat.
GAP_BY_PUNCT = {"?": 0.46, "!": 0.40, ".": 0.32, ":": 0.30, ";": 0.26, ",": 0.16}
GAP_DEFAULT = 0.24

# Bien thien toc do nhe giua cac cau — pha nhip metronome. Co dinh (khong random)
# de build lai cho ket qua giong nhau.
RATE_JITTER = [0.0, 3.0, -2.0, 2.0, -3.0, 1.0]

SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=["“(]?[A-Z0-9])')


def prep_vo_text(t):
    """Chuan hoa text truoc khi doc: dash/ellipsis -> ranh gioi cau that.

    Doi dash thanh cau moi la cach duy nhat lay duoc khoang nghi co kiem soat,
    vi edge-tts gan nhu bo qua chinh cac dau do.
    """
    t = t.replace("—", ". ").replace("–", ". ")
    t = re.sub(r"\s+-\s+", ". ", t)
    t = t.replace("…", ". ").replace("...", ". ")
    t = (t.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"'))
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text):
    """Tach theo CAU (khong tach o dau phay: moi utterance edge-tts co ngu dieu
    ket cau rieng, tach nho qua se nghe roi rac)."""
    return [s.strip() for s in SENT_SPLIT.split(" ".join(text.split())) if s.strip()]


def gap_after(sent):
    return GAP_BY_PUNCT.get(sent.rstrip()[-1:], GAP_DEFAULT)


def sentence_rate(i, n, base_pct, sent):
    """Cau mo dau tu ton, cau cuoi ha canh, cau hoi keo ra — cong jitter nhe."""
    adj = base_pct + RATE_JITTER[i % len(RATE_JITTER)]
    if n > 1 and i == 0:
        adj -= 3.0
    if n > 1 and i == n - 1:
        adj -= 5.0
    if sent.rstrip().endswith("?"):
        adj -= 4.0
    return f"{int(round(max(-40.0, min(60.0, adj)))):+d}%"


def _loudnorm_2pass(src, dst, lufs=-16.0, tp=-1.5, lra=11.0):
    """Chuan hoa loudness EBU R128. 2 pass + linear=true: chi dich gain, khong
    nen dong — giu nguyen nhip to-nho cua giong doc."""
    af = f"loudnorm=I={lufs}:TP={tp}:LRA={lra}"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src,
                        "-af", af + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = p.stderr or ""
    i = txt.rfind("{")
    if i >= 0:
        try:
            m = json.loads(txt[i:txt.rfind("}") + 1])
            af += (f":linear=true:measured_I={m['input_i']}"
                   f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                   f":measured_thresh={m['input_thresh']}"
                   f":offset={m['target_offset']}")
        except Exception:
            pass
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-af", af,
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000",
                    "-ac", "1", dst], check=True)


def edge_render_cell(text, out_path, voice, base_pct=0.0, pitch="+0Hz",
                     volume="+0%", lufs=-16.0, tries=3):
    """Doc TUNG CAU -> cat lang -> ghep lai voi khoang lang do ta quyet dinh.

    Tra ve (speech_dur, total_dur, word_timings). speech_dur khong tinh khoang
    lang — day moi la con so dung de do toc do doc.
    """
    import time
    import edge_tts
    from probe import duration

    sents = split_sentences(prep_vo_text(text)) or [prep_vo_text(text)]
    tmp_dir = os.path.join(os.path.dirname(out_path), "_seg",
                           os.path.splitext(os.path.basename(out_path))[0])
    os.makedirs(tmp_dir, exist_ok=True)

    async def _one(sent, rate_str, raw):
        # boundary mac dinh la SentenceBoundary -> khong co moc tung tu.
        c = edge_tts.Communicate(sent, voice, rate=rate_str, pitch=pitch,
                                 volume=volume, boundary="WordBoundary")
        words, buf = [], bytearray()
        async for ch in c.stream():
            if ch["type"] == "audio":
                buf += ch["data"]
            elif ch["type"] == "WordBoundary":
                words.append({"t": ch["offset"] / TICKS,
                              "d": ch["duration"] / TICKS, "w": ch["text"]})
        with open(raw, "wb") as f:
            f.write(bytes(buf))
        return words

    segs, timings, cursor, speech = [], [], 0.0, 0.0
    for i, sent in enumerate(sents):
        rate_str = sentence_rate(i, len(sents), base_pct, sent)
        raw = os.path.join(tmp_dir, f"raw{i}.mp3")
        wav = os.path.join(tmp_dir, f"seg{i}.wav")
        for attempt in range(tries):
            try:
                words = asyncio.run(_one(sent, rate_str, raw))
                break
            except Exception:
                if attempt == tries - 1:
                    raise
                time.sleep(2 + 2 * attempt)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw,
                        "-af", TRIM_AF + ",aresample=48000",
                        "-ac", "1", "-c:a", "pcm_s16le", wav], check=True)
        d = duration(wav)
        lead = words[0]["t"] if words else 0.0   # WordBoundary tinh trƯoc khi trim
        for w in words:
            timings.append({"w": w["w"], "t": round(cursor + w["t"] - lead, 3),
                            "d": round(w["d"], 3)})
        gap = gap_after(sent) if i < len(sents) - 1 else 0.0
        segs.append((wav, gap))
        speech += d
        cursor += d + gap

    ins, fc, n = [], [], 0
    for wav, gap in segs:
        ins += ["-i", wav]
        fc.append(f"[{n}:a]aresample=48000[x{n}]")
        n += 1
        if gap > 0:
            ins += ["-f", "lavfi", "-t", f"{gap:.3f}", "-i",
                    "anullsrc=r=48000:cl=mono"]
            fc.append(f"[{n}:a]aresample=48000[x{n}]")
            n += 1
    fc.append("".join(f"[x{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1[cat]")
    joined = os.path.join(tmp_dir, "joined.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins,
                    "-filter_complex", ";".join(fc), "-map", "[cat]",
                    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", joined],
                   check=True)
    _loudnorm_2pass(joined, out_path, lufs=lufs)
    return round(speech, 3), duration(out_path), timings


def _key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        raise SystemExit(
            "Thieu ELEVENLABS_API_KEY. Dat: $env:ELEVENLABS_API_KEY='...'")
    return k


def _eleven_call(path, headers, data=None):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(API + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"ElevenLabs loi {e.code}: {body}")


def generate_one(key, voice, model, text, out_path, stability=0.45, similarity=0.8):
    import json as _j
    body = _j.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability, "similarity_boost": similarity,
            "style": 0.2, "use_speaker_boost": True,
        },
    }).encode("utf-8")
    audio = _eleven_call(
        f"/v1/text-to-speech/{voice}",
        {"xi-api-key": key, "Content-Type": "application/json",
         "Accept": "audio/mpeg"}, data=body)
    with open(out_path, "wb") as f:
        f.write(audio)
    print(f"OK  {os.path.basename(out_path)}  ({len(audio)/1024:.0f} KB)")


def generate_for_case(root, cfg, voice=DEFAULT_VOICE, model=DEFAULT_MODEL,
                      provider="edge", edge_voice=None, rate="+0%",
                      stability=0.45, similarity=0.8, skip_existing=True,
                      target_wpm=158.0, wpm_lo=145.0, wpm_hi=172.0,
                      fix_pace=True):
    out_dir = os.path.join(root, "build", "voice")
    os.makedirs(out_dir, exist_ok=True)
    cells = [c for c in cfg["cells"] if c.get("vo")]
    if not cells:
        print("config khong co cell nao co 'vo'")
        return []

    try:
        base_pct0 = float(str(rate).replace("%", "").replace("+", "") or 0.0)
    except ValueError:
        base_pct0 = 0.0

    if provider == "edge":
        voice = edge_voice or EDGE_VOICE
        key = None

        def generate(text, out_path, base_pct):
            return edge_render_cell(text, out_path, voice, base_pct=base_pct)
    else:
        key = _key()

        def generate(text, out_path, base_pct):
            from probe import duration as _d
            generate_one(key, voice, model, text, out_path,
                         stability=stability, similarity=similarity)
            d = _d(out_path)
            return d, d, []

    from probe import duration

    def _text_hash(c):
        return hashlib.md5((c["vo"] + "|" + str(voice)).encode("utf-8")).hexdigest()[:12]

    def gen_one(c, base_pct):
        name = f"cell-{c['id']}"
        out_path = os.path.join(out_dir, f"{name}.mp3")
        speech, total, words = generate(c["vo"], out_path, base_pct)
        # wpm do tren PHAN NOI THAT. Ban cu chia cho do dai ca file (gom ~1s
        # lang cuoi) nen tuong giong doc cham, roi ep rate len — ket qua la doc
        # gap 200+ wpm roi ngoi im gan mot giay. Chinh la cam giac "may doc".
        wpm = len(c["vo"].split()) / (max(0.01, speech) / 60.0)
        with open(os.path.join(out_dir, f"{name}.words.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"hash": _text_hash(c), "words": words}, f,
                      ensure_ascii=False)
        return {"seg": name, "file": f"{name}.mp3", "dur": round(total, 3),
                "speech": round(speech, 3), "cell": c["id"],
                "wpm": round(wpm, 0), "rate_pct": round(base_pct, 1)}

    # pass 1: sinh tai rate goc (hoac skip neu da co VA text khong doi)
    manifest = []
    for c in cells:
        name = f"cell-{c['id']}"
        out_path = os.path.join(out_dir, f"{name}.mp3")
        wpath = os.path.join(out_dir, f"{name}.words.json")
        cached = None
        if skip_existing and os.path.exists(out_path) and os.path.exists(wpath):
            try:
                with open(wpath, encoding="utf-8") as f:
                    if json.load(f).get("hash") == _text_hash(c):
                        cached = duration(out_path)
            except Exception:
                cached = None
        if cached:
            manifest.append({"seg": name, "file": f"{name}.mp3",
                             "dur": round(cached, 3), "speech": round(cached, 3),
                             "cell": c["id"],
                             "wpm": round(len(c["vo"].split()) / (cached / 60.0), 0),
                             "rate_pct": base_pct0})
        else:
            manifest.append(gen_one(c, base_pct0))

    # pass 2: fix pace — CHINH MOT LAN, co giam chan, va giu lai ban tot hon.
    # Do thuc te: edge-tts tra ve do dai khac nhau ~7% giua hai lan goi CUNG
    # tham so, va rate khong don dieu tuyet doi (-25% co the cham hon -30%).
    # Vong lap duoi ba lan cua ban cu vi the cu bam bap quanh dich va moi lan
    # sinh lai la mot ban thu am khac — vua ton request vua khong hoi tu.
    if provider == "edge" and fix_pace:
        import shutil
        for i, m in enumerate(manifest):
            c = next(x for x in cells if x["id"] == m["cell"])
            out_path = os.path.join(out_dir, f"{m['seg']}.mp3")
            for _ in range(2):
                w = manifest[i]["wpm"]
                if wpm_lo <= w <= wpm_hi:
                    break
                cur_pct = manifest[i].get("rate_pct", base_pct0)
                speed = (1.0 + cur_pct / 100.0) * (target_wpm / w)
                new_pct = max(-35.0, min(45.0, (speed - 1.0) * 100.0))
                new_pct = cur_pct + 0.6 * (new_pct - cur_pct)      # giam chan
                if abs(new_pct - cur_pct) < 1.5:
                    break
                bak = out_path + ".bak"
                shutil.copyfile(out_path, bak)
                cand = gen_one(c, new_pct)
                if abs(cand["wpm"] - target_wpm) < abs(w - target_wpm):
                    cand["fixed"] = True
                    manifest[i] = cand
                    print(f"  chinh nhip cell {c['id']}: {w:.0f} -> "
                          f"{cand['wpm']:.0f} wpm ({new_pct:+.0f}%)")
                    os.remove(bak)
                else:
                    shutil.move(bak, out_path)   # ban moi te hon -> giu ban cu
                    print(f"  giu nguyen cell {c['id']}: {w:.0f} wpm "
                          f"(thu {new_pct:+.0f}% ra {cand['wpm']:.0f})")
                    break
        # canh bao cell con lech ngay ca sau 3 vong
        for m in manifest:
            if not (wpm_lo <= m["wpm"] <= wpm_hi):
                print(f"  WARN cell {m['cell']}: {m['wpm']:.0f} wpm ngoai "
                      f"[{wpm_lo:.0f},{wpm_hi:.0f}] (edge-tts gioi han rate)")

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"provider": provider, "voice": voice, "target_wpm": target_wpm,
                   "segs": manifest}, f, ensure_ascii=False, indent=2)
    total = round(sum(m["dur"] for m in manifest), 1)
    avg_wpm = round(sum(m["wpm"] for m in manifest) / max(1, len(manifest)), 0)
    print(f"\n{len(manifest)} cell VO, tong {total}s (~{total/60:.1f} phut), "
          f"avg {avg_wpm:.0f} wpm")
    return manifest


def list_voices():
    import urllib.request
    key = _key()
    raw = _eleven_call("/v1/voices", {"xi-api-key": key})
    for v in json.loads(raw).get("voices", []):
        print(f"{v['voice_id']}  {v['name']}  labels={v.get('labels', {})}")


def list_edge_voices():
    import asyncio
    import edge_tts
    vs = asyncio.run(edge_tts.list_voices())
    for v in vs:
        if v["Locale"].startswith("en-"):
            print(f"{v['ShortName']}  {v['Gender']}  {v['Locale']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--provider", choices=["elevenlabs", "edge"], default="edge")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--edge-voice", default=None)
    ap.add_argument("--rate", default="+0%")
    ap.add_argument("--wpm", type=float, default=170.0, help="target words/minute")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()

    if args.list_voices:
        if args.provider == "edge":
            list_edge_voices()
        else:
            list_voices()
        return

    root = os.path.abspath(args.case)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as CFG
    cfg = CFG.load(root)
    generate_for_case(root, cfg, args.voice, args.model,
                      provider=args.provider, edge_voice=args.edge_voice,
                      rate=args.rate, target_wpm=args.wpm)


if __name__ == "__main__":
    main()
