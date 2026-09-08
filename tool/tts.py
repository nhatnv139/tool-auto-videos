"""
tts.py — Sinh VO cho tung cell co 'vo' trong config.

    python tool/run.py --case videos/<topic> tts --provider edge          # free test
    python tool/run.py --case videos/<topic> tts --provider elevenlabs    # can ELEVENLABS_API_KEY

Output: build/voice/cell-<id>.mp3 + build/voice/manifest.json
edge-tts: Microsoft neural, mien phi, khong can key.
ElevenLabs: can ELEVENLABS_API_KEY, giong tu nhien hon.
"""
import argparse
import json
import os
import sys

API = "https://api.elevenlabs.io"
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_MODEL = "eleven_multilingual_v2"


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
                      target_wpm=160.0, wpm_lo=150.0, wpm_hi=175.0,
                      fix_pace=True):
    out_dir = os.path.join(root, "build", "voice")
    os.makedirs(out_dir, exist_ok=True)
    cells = [c for c in cfg["cells"] if c.get("vo")]
    if not cells:
        print("config khong co cell nao co 'vo'")
        return []

    if provider == "edge":
        import asyncio
        import edge_tts
        voice = edge_voice or "en-US-ChristopherNeural"

        def generate(text, out_path, rate_str):
            async def _run():
                c = edge_tts.Communicate(text, voice, rate=rate_str)
                await c.save(out_path)
            asyncio.run(_run())
        key = None
    else:
        key = _key()

        def generate(text, out_path, rate_str):
            generate_one(key, voice, model, text, out_path,
                         stability=stability, similarity=similarity)

    from probe import duration

    def wpm_of(out_path, text):
        d = duration(out_path)
        return len(text.split()) / (d / 60.0), d

    def gen_one(c, rate_str):
        name = f"cell-{c['id']}"
        out_path = os.path.join(out_dir, f"{name}.mp3")
        generate(c["vo"], out_path, rate_str)
        wpm, d = wpm_of(out_path, c["vo"])
        return {"seg": name, "file": f"{name}.mp3", "dur": round(d, 3),
                "cell": c["id"], "wpm": round(wpm, 0)}

    # pass 1: sinh tai rate goc (hoac skip neu da co)
    manifest = []
    for c in cells:
        name = f"cell-{c['id']}"
        out_path = os.path.join(out_dir, f"{name}.mp3")
        if skip_existing and os.path.exists(out_path):
            wpm, d = wpm_of(out_path, c["vo"])
            manifest.append({"seg": name, "file": f"{name}.mp3",
                             "dur": round(d, 3), "cell": c["id"],
                             "wpm": round(wpm, 0)})
        else:
            manifest.append(gen_one(c, rate))

    # pass 2: fix pace — lap toi da 3 vong, sua cell con lech [lo, hi]
    if provider == "edge" and fix_pace:
        for _ in range(3):
            fixed_any = False
            for i, m in enumerate(manifest):
                c = next(x for x in cells if x["id"] == m["cell"])
                w = m["wpm"]
                if w < wpm_lo or w > wpm_hi:
                    delta = (target_wpm / w) - 1.0
                    try:
                        base = float(rate.replace("%", "").replace("+", "")) or 0.0
                    except ValueError:
                        base = 0.0
                    adj = round(base + delta * 100.0)
                    adj = max(-50, min(80, adj))
                    rate_str = f"{adj:+d}%"
                    fixed = gen_one(c, rate_str)
                    fixed["fixed"] = True
                    print(f"  fix pace cell {c['id']}: {w:.0f} -> {fixed['wpm']:.0f} "
                          f"wpm ({rate_str})")
                    manifest[i] = fixed
                    fixed_any = True
            if not fixed_any:
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
