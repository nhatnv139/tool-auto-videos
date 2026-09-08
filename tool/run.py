"""
run.py — Lenh dieu khien pipeline ai-frontier (video-driven).

    python tool/run.py --case videos/<topic> config          # validate config.json
    python tool/run.py --case videos/<topic> fetch           # tai + cat clip tu manifest
    python tool/run.py --case videos/<topic> script2config   # script.md -> config.json
    python tool/run.py --case videos/<topic> render          # sinh build/shots/cell-*.mp4
    python tool/run.py --case videos/<topic> tts --provider edge   # VO (edge free test)
    python tool/run.py --case videos/<topic> tts --provider elevenlabs  # can ELEVENLABS_API_KEY
    python tool/run.py --case videos/<topic> music --dur 120 # nhac nen tam
    python tool/run.py --case videos/<topic> plan            # in timeline roi thoat
    python tool/run.py --case videos/<topic> assemble        # ghep ra build/final/*.mp4
    python tool/run.py --case videos/<topic> sources         # sinh build/sources.md

Flow video moi:
    1. clip-manifest.json + references.json + script/script.md
    2. script2config -> config.json
    3. fetch -> assets/clips/clip-*.mp4
    4. render -> build/shots/cell-*.mp4
    5. tts edge  -> build/voice/cell-*.mp3  (sau nay elevenlabs)
    6. music -> assets/music/bed.wav
    7. plan (xem timeline), assemble -> build/final/video-1.mp4
    8. sources -> build/sources.md (dang len mo ta video)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as CFG  # noqa: E402
import render as R  # noqa: E402
import music as MU  # noqa: E402
import assemble as AS  # noqa: E402


def case_root(name):
    root = os.path.abspath(name)
    if not os.path.isdir(root):
        raise SystemExit(f"khong thay case {name}")
    return root


def cmd_config(root):
    cfg = CFG.load(root)
    print(f"config OK: {cfg['name']}, {len(cfg['cells'])} cells, out={cfg['out']}")


def cmd_fetch(root, force):
    from fetch import fetch
    fetch(root, force=force)


def cmd_script2config(root):
    from script2config import build
    build(root)


def cmd_render(root, only):
    cfg = CFG.load(root)
    n, _ = R.render_all(cfg, root, only=only)
    print(f"\nrender xong {n} cell -> build/shots/")


def cmd_stock(root, all_stock, prune=False, prune_yes=False):
    if prune:
        from stock import prune_stock
        keep, drop, mb = prune_stock(root, dry_run=not prune_yes)
        if drop and not prune_yes:
            print("Chay lai voi --prune-yes de xoa that.")
        return
    if all_stock:
        from stock import fetch_stock_all
        fetch_stock_all(root, variants=12)
        return
    cfg = CFG.load(root)
    from stock import fetch_stock
    fetch_stock(root, cfg)


def cmd_stock_usage(root):
    cfg = CFG.load(root)
    from stock import list_stock_usage
    list_stock_usage(root, cfg)


def cmd_sfx(root, refresh, only, list_only):
    from sfx import fetch_sfx, list_sfx
    if list_only:
        list_sfx(root)
        return
    n = fetch_sfx(root, names=only, refresh=refresh)
    print(f"SFX xong: {n} file tai")


def cmd_tts(root, provider, edge_voice, rate, wpm):
    cfg = CFG.load(root)
    from tts import generate_for_case
    generate_for_case(root, cfg, provider=provider, edge_voice=edge_voice,
                      rate=rate, target_wpm=wpm)


def cmd_music(root, dur):
    out = os.path.join(root, "assets", "music", "bed.wav")
    MU.placeholder(out, dur)
    print("  -> ghi lai duong dan vao config.json / music.file neu can")


def cmd_plan(root):
    cfg = CFG.load(root)
    rows, total, missing = AS.plan(root, cfg, strict=False)
    if missing:
        print(f"(canh bao) {len(missing)} cell thieu VO file")
    print(f"tong: {total:.1f}s ({total/60:.1f} phut), {len(rows)} cell")
    card_dur = sum(r["dur"] for r in rows if r["cell"]["type"] in ("card", "quote")
                   and not r["cell"].get("vo"))
    clip_dur = sum(r["dur"] for r in rows if r["cell"]["type"] in ("clip", "clip-mute", "stock"))
    body_dur = total - sum(r["dur"] for r in rows if r["cell"]["type"] == "outro")
    ratio = card_dur / body_dur if body_dur else 0
    print(f"phan bo (tru outro): clip+stock {clip_dur:.0f}s ({clip_dur/body_dur*100:.0f}%), "
          f"card+quote(cam) {card_dur:.0f}s ({ratio*100:.0f}%)")
    if ratio > 0.15:
        print(f"  (canh bao) card/quote cam lang chiem {ratio*100:.0f}% > 15% — "
              f"can doi sang [[broll:]]/[[stock:]]")
    _warn_card_quality(cfg, rows)
    _warn_long_caption(cfg)
    _warn_repeat_source(root)
    for r in rows:
        tag = "VO+clip" if r["vo"] and r["audio"] else (
            "VO" if r["vo"] else ("clip" if r["audio"] else "hinh"))
        print(f"  cell {r['cell']['id']:>3}  start {r['start']:7.1f}  "
              f"dur {r['dur']:6.1f}  shot {r['shot_dur']:6.1f}  {tag}  "
              f"[{r['cell']['type']}]")


def _warn_card_quality(cfg, rows):
    """Card can co |src= va 2 card cach nhau >= 15s."""
    card_cells = [r for r in rows if r["cell"]["type"] in ("card", "quote")]
    prev_card_end = -99
    for r in card_cells:
        cell = r["cell"]
        if cell["type"] == "card" and not cell.get("src"):
            print(f"  (canh bao) cell {cell['id']} card thieu |src= — them nguon "
                  f"(|src=...); card trang tri khong nguon khong nen dung")
        if r["start"] - prev_card_end < 15:
            print(f"  (canh bao) cell {cell['id']} card/quote cach card truoc "
                  f"< 15s — khong nen don card; dung footage giua")
        prev_card_end = r["start"] + r["dur"]


def _warn_long_caption(cfg):
    """Canh bao caption dai (segments qua nhieu) — cau qua dai, tach trong script."""
    import assemble as A
    for cell in cfg["cells"]:
        if cell.get("cap"):
            segs = A._split_segments(cell["cap"])
            if len(segs) > 4:
                print(f"  (canh bao) cell {cell['id']} caption tach {len(segs)} doan > 4 "
                      f"— cau qua dai, nen tach trong script")


def _warn_repeat_source(root):
    """Canh bao neu 2 clip lien tiep cung video nguon (chong lap footage)."""
    from manifest import load_manifest
    from fetch import extract_video_id
    clips = load_manifest(root)
    url_by_id = {c["id"]: c for c in clips}
    cfg = CFG.load(root)
    prev_vid = None
    for cell in cfg["cells"]:
        cid = cell.get("clip")
        if cid and cid in url_by_id:
            c = url_by_id[cid]
            vid = extract_video_id(c["url"])
            if prev_vid and vid and vid == prev_vid:
                print(f"  (canh bao) clip lien tiep trung nguon video {vid} — "
                      f"doi sang nguon khac de tranh lap footage")
            prev_vid = vid
            # fair use: clip youtube ngan (<=15s)
            if c.get("src_type") == "youtube":
                dur = c["out"] - c["in"]
                if dur > 15:
                    print(f"  (canh bao) clip {cid} youtube dai {dur:.0f}s > 15s — "
                          f"fair use can clip ngan")
        elif cell.get("type") in ("card", "quote", "black", "sfx", "outro", "stock"):
            prev_vid = None


def cmd_assemble(root, emit_only):
    cfg = CFG.load(root)
    fps = cfg.get("fps", 24)
    rows, total, missing = AS.plan(root, cfg, strict=True)
    print(f"tong video: {total:.1f}s ({total/60:.1f} phut), {len(rows)} cell")
    if emit_only:
        AS.stage1_trim(rows, root, fps)
        AS.stage2_concat(rows, root, fps)
        AS.stage3_audio(rows, total, root, cfg)
        AS.stage4_mux(root, cfg, total)
        print("chay: source build/run_stage1.sh; stage2; stage3; stage4")
        return
    print("stage 1: trim + caption ...")
    AS.stage1_trim(rows, root, fps)
    AS.run_script(root, "run_stage1.sh")
    print("stage 2: concat (GOP 2s, no B-frame) ...")
    AS.stage2_concat(rows, root, fps)
    AS.run_script(root, "run_stage2.sh")
    print("stage 3: audio ...")
    AS.stage3_audio(rows, total, root, cfg)
    AS.run_script(root, "run_stage3.sh")
    print("stage 4: mux ...")
    AS.stage4_mux(root, cfg, total)
    AS.run_script(root, "run_stage4.sh")
    out = CFG.resolve(root, cfg["out"])
    print("stage 5: decode check ...")
    AS.decode_check(root, out)
    print(f"DONE  {out}")


def cmd_sources(root):
    from sources import generate
    cfg = CFG.load(root)
    generate(root, cfg["name"])


def cmd_search(root, q, site, n, cookies_browser):
    from search import search
    search(root, q, site=site, n=n, cookies_browser=cookies_browser)


def cmd_thumb(root, src, t):
    from thumbnail import render
    import os
    render(root, src=os.path.abspath(src) if src else None, frame_t=t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("command", choices=["config", "fetch", "script2config", "render",
                                        "stock", "stock-usage", "sfx", "tts", "music",
                                        "plan", "assemble", "sources", "search", "thumb"])
    ap.add_argument("--dur", type=float, default=120.0)
    ap.add_argument("--provider", choices=["elevenlabs", "edge"], default="edge")
    ap.add_argument("--edge-voice", default=None)
    ap.add_argument("--rate", default="+0%")
    ap.add_argument("--wpm", type=float, default=160.0)
    ap.add_argument("--emit-only", action="store_true")
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--sfx-only", nargs="*", dest="sfx_only", help="chi tai cac sfx nay")
    ap.add_argument("--list-sfx", action="store_true")
    ap.add_argument("--q", default=None, help="tu khoa search")
    ap.add_argument("--src", default=None, help="thumb: file mp4 stock lam nen")
    ap.add_argument("--t", type=float, default=0.0, help="thumb: giay lay frame")
    ap.add_argument("--site", choices=["youtube", "douyin", "bilibili"], default="youtube")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--cookies-from-browser", default=None)
    ap.add_argument("--all", action="store_true", help="stock --all: tai toan bo theme")
    ap.add_argument("--prune", action="store_true",
                    help="stock --prune: xoa file stock trung noi dung (dry-run)")
    ap.add_argument("--prune-yes", action="store_true",
                    help="stock --prune --prune-yes: xoa that")
    args = ap.parse_args()

    root = case_root(args.case)
    if args.command == "config":
        cmd_config(root)
    elif args.command == "fetch":
        cmd_fetch(root, args.force)
    elif args.command == "script2config":
        cmd_script2config(root)
    elif args.command == "render":
        cmd_render(root, args.only)
    elif args.command == "stock":
        cmd_stock(root, args.all, args.prune, args.prune_yes)
    elif args.command == "stock-usage":
        cmd_stock_usage(root)
    elif args.command == "sfx":
        cmd_sfx(root, args.refresh, args.sfx_only, args.list_sfx)
    elif args.command == "tts":
        cmd_tts(root, args.provider, args.edge_voice, args.rate, args.wpm)
    elif args.command == "music":
        cmd_music(root, args.dur)
    elif args.command == "plan":
        cmd_plan(root)
    elif args.command == "assemble":
        cmd_assemble(root, args.emit_only)
    elif args.command == "sources":
        cmd_sources(root)
    elif args.command == "search":
        cmd_search(root, args.q, args.site, args.n, args.cookies_from_browser)
    elif args.command == "thumb":
        cmd_thumb(root, args.src, args.t)


if __name__ == "__main__":
    main()
