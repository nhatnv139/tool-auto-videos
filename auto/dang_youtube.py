"""Đăng video trong OUTBOX lên YouTube, hẹn giờ công khai + đặt thumbnail.

Mỗi thư mục OUTBOX/<ngày>-<slug>/ cần: video.mp4, youtube.json
({title, description, tags, publish_at, channel}), thumbnail.jpg (tuỳ chọn).
Kết quả ghi vào youtube_result.json; đã có id thì bỏ qua (chạy lại an toàn).

    python auto/dang_youtube.py OUTBOX/2026-10-03-bach-dang-ba-tran [...]
    python auto/dang_youtube.py --dry OUTBOX/...

Token OAuth dùng chung với video-autopilot (video-autopilot/yt_tokens/).
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

AUTOPILOT = Path("D:/dev/video-autopilot")
sys.path.insert(0, str(AUTOPILOT))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

import youtube_upload  # noqa: E402


def _yt(channel):
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    creds = youtube_upload._creds_for(channel)
    # 08/10/2026: token ghi "con han" toi 11:35 nhung Google da tu choi tu 10:13
    # (401) -> _creds_for khong refresh. Luon refresh truoc khi dang.
    if creds.refresh_token:
        creds.refresh(Request())
        tok = Path(youtube_upload.TOKENS_DIR) / f"{channel}.json"
        tok.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def dang(folder: Path, dry=False):
    meta = json.loads((folder / "youtube.json").read_text(encoding="utf-8"))
    out = folder / "youtube_result.json"
    res = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    at = dt.datetime.fromisoformat(meta["publish_at"]) if meta.get("publish_at") else None
    print(f"[{folder.name}] {meta['title']}\n  hẹn: {at or 'đăng ngay'}")
    if dry:
        return
    yt = _yt(meta["channel"])
    if not res.get("id"):
        from googleapiclient.http import MediaFileUpload
        status = {"selfDeclaredMadeForKids": False}
        if at and at > dt.datetime.now(at.tzinfo) + dt.timedelta(minutes=15):
            status.update(privacyStatus="private",
                          publishAt=at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        else:
            status["privacyStatus"] = "public"
        body = {"snippet": {"title": meta["title"][:100], "description": meta["description"][:5000],
                            "tags": meta.get("tags", []), "categoryId": "27",
                            "defaultLanguage": "vi", "defaultAudioLanguage": "vi"},
                "status": status}
        media = MediaFileUpload(str(folder / "video.mp4"), chunksize=32 * 1024 * 1024,
                                resumable=True, mimetype="video/mp4")
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            st, resp = req.next_chunk()
            if st:
                print(f"  upload {st.progress() * 100:.0f}%", flush=True)
        try:  # Windows: MediaFileUpload giu file mo -> khong xoa duoc video sau khi dang
            media.stream().close()
        except Exception:  # noqa: BLE001
            pass
        res = {"id": resp["id"], "url": f"https://youtu.be/{resp['id']}",
               "publish_at": status.get("publishAt"), "privacy": status["privacyStatus"]}
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  ->", res["url"])
    thumb = folder / "thumbnail.jpg"
    if thumb.exists() and not res.get("thumbnail"):
        try:
            youtube_upload.set_thumbnail(meta["channel"], res["id"], str(thumb))
            res["thumbnail"] = True
            res.pop("thumbnail_error", None)
            print("  thumbnail OK")
        except Exception as e:  # noqa: BLE001
            res["thumbnail_error"] = str(e)[:300]
            print("  thumbnail LỖI:", str(e)[:300])
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    # Da len YouTube (ke ca hen gio) -> xoa video + build cho nhe may (08/10/2026).
    if res.get("id"):
        import don_dep
        slug = folder.name[11:]  # bo "YYYY-MM-DD-"
        freed, _ = don_dep.xoa_da_dang(str(Path(don_dep.VIDEOS) / slug), that=True, im=True)
        if freed:
            print(f"  đã xoá {freed / 1e9:.2f} GB video/build trên máy")


def dang_chac(folder: Path, lan=3):
    """dang() kem thu lai: YouTube thinh thoang tra 401/410 du token vua refresh
    (08/10/2026). Moi lan thu lai deu lay token moi; da co id thi chi lam not
    phan con thieu (thumbnail)."""
    import time
    for i in range(1, lan + 1):
        try:
            dang(folder)
            r = json.loads((folder / "youtube_result.json").read_text(encoding="utf-8"))
            if r.get("id") and (r.get("thumbnail") or not (folder / "thumbnail.jpg").exists()):
                return r
            loi = r.get("thumbnail_error", "thieu thumbnail")
        except Exception as e:  # noqa: BLE001
            loi = str(e)[:200]
        print(f"  lan {i} chua xong: {loi} -> thu lai sau 60s")
        time.sleep(60)
    raise RuntimeError(f"dang khong xong sau {lan} lan: {loi}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    for f in a.folders:
        try:
            dang(Path(f), True) if a.dry else dang_chac(Path(f))
        except Exception as e:  # noqa: BLE001
            print(f"  LỖI {f}: {str(e)[:400]}")


if __name__ == "__main__":
    main()
