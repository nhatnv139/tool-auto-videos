"""
search.py — Tim video nguon theo tu khoa, them vao clip-manifest.json.

    python tool/run.py --case videos/<topic> search --q "AI frontier" [--n 8]
    python tool/run.py --case videos/<topic> search --q "AI 前沿" --site douyin

site:
  youtube (mac dinh): yt-dlp ytsearch:N — hoat dong chac chan.
  douyin: can cookies chong bot (--cookies-from-browser edge/chrome). Neu
          khong co cookie, in huong dan dung URL thong cong.

Sau khi liet ke: nguoi dung nhap so (vd '1 3 5') -> tool tu ghi vao
clip-manifest.json (id tu tang, in=0, out=6s, type dung site, note=title).
Nguoi dung sua timestamp sau.

Luu y: Bilibili khong ho tro (IP may bi chan 403).
"""
import json
import os
import subprocess
import sys


def _yt_search(q, n):
    cmd = ["yt-dlp", "--skip-download", "--no-warnings", "--flat-playlist",
           "-f", "best", "--print", "%(id)s\t%(title).70s\t%(duration)s\t%(uploader).30s",
           f"ytsearch{n}:{q}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"search loi: {r.stderr[-500:]}")
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append({
                "id": parts[0],
                "title": parts[1],
                "dur": parts[2] if len(parts) > 2 else "",
                "uploader": parts[3] if len(parts) > 3 else "",
            })
    return rows


def _print_results(rows):
    print(f"\n{'#':>2}  {'id':<14} {'dur':>5}  {'uploader':<22} title")
    for i, r in enumerate(rows, 1):
        print(f"{i:>2}. {r['id']:<14} {r['dur']:>5}  {r['uploader']:<22} {r['title']}")


def _add_to_manifest(root, rows, picks, site):
    path = os.path.join(root, "clip-manifest.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = []
    nxt = max([c["id"] for c in manifest] or [0]) + 1
    for p in picks:
        r = rows[p - 1]
        manifest.append({
            "id": nxt,
            "url": ("https://www.douyin.com/video/" + r["id"] if site == "douyin"
                    else f"https://youtu.be/{r['id']}"),
            "in": 0, "out": 6,
            "speaker": r["uploader"],
            "note": r["title"],
            "type": site,
        })
        nxt += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\nOK: them {len(picks)} clip vao clip-manifest.json")


def search(root, q, site="youtube", n=8, cookies_browser=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if site == "bilibili":
        print("Bilibili khong ho tro (IP may bi chan 403). Dung douyin hoac youtube.")
        return
    if site == "douyin":
        _douyin_hint(q, n, cookies_browser)
        return
    rows = _yt_search(q, n)
    if not rows:
        print("(rong) khong co ket qua")
        return
    _print_results(rows)
    pick = input("\nNhap so muon them (vd '1 3 5', Enter de bo qua): ").strip()
    if not pick:
        print("bo qua")
        return
    picks = []
    for tok in pick.split():
        try:
            i = int(tok)
            if 1 <= i <= len(rows):
                picks.append(i)
        except ValueError:
            pass
    if picks:
        _add_to_manifest(root, rows, picks, site)


def _douyin_hint(q, n, cookies_browser):
    cmd = ["yt-dlp", "--skip-download", "--no-warnings", "--flat-playlist",
           "--print", "%(id)s\t%(title).70s\t%(duration)s",
           f"https://www.douyin.com/search/{q}"]
    if cookies_browser:
        cmd = cmd[:2] + [f"--cookies-from-browser", cookies_browser] + cmd[2:]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        rows = [dict(id=p[0], title=p[1], dur=p[2] if len(p) > 2 else "", uploader="")
                for p in (ln.split("\t") for ln in r.stdout.splitlines()) if len(p) >= 2]
        if rows:
            _print_results(rows)
            pick = input("\nNhap so muon them (Enter de bo qua): ").strip()
            picks = [int(t) for t in pick.split() if t.isdigit()]
            if picks:
                _add_to_manifest(root, rows, picks, "douyin")
            return
    print("\nDouyin can cookies chong bot. Cach xử lý:")
    print("  1. Tat trinh duyet roi chay: --cookies-from-browser edge")
    print("  2. Hoac mo video douyin, copy URL '/video/<id>' dan thang vao clip-manifest.json")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--q", required=True)
    ap.add_argument("--site", choices=["youtube", "douyin", "bilibili"], default="youtube")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--cookies-from-browser", default=None)
    args = ap.parse_args()
    root = os.path.abspath(args.case)
    search(root, args.q, args.site, args.n, args.cookies_from_browser)


if __name__ == "__main__":
    main()
