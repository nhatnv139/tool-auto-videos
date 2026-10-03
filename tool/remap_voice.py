"""remap_voice.py — Doi so hieu file giong khi cell bi danh so lai.

Chen them cell vao giua script (vi du 7 diem ngat chuong) lam moi cell phia sau
doi id. File giong dat ten theo id (cell-<id>.mp3) nen bong nhien lech het: cell
8 doc loi cua cell 7. Chay lai tts thi mat ca tieng dong ho sinh lai y het cai
da co.

Tool nay ghep lai theo HASH VAN BAN trong <cell>.words.json — dung cach tts.py
tinh — roi doi ten cho khop id moi. Chi dung file nao hash khop; cell nao khong
tim duoc nguon thi bao ra de chay tts bu.

  python tool/remap_voice.py videos/<topic>            # xem truoc
  python tool/remap_voice.py videos/<topic> --apply    # lam that
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tts import PROSODY_VERSION      # noqa: E402


def text_hash(vo, voice):
    sig = f"{vo}|{voice}|p{PROSODY_VERSION}"
    return hashlib.md5(sig.encode("utf-8")).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--apply", action="store_true")
    # Hash cua tts.py gom ca ma giong; config khong luu no nen phai truyen vao.
    ap.add_argument("--voice", default="vi-VN-NamMinhNeural")
    args = ap.parse_args()

    root = os.path.abspath(args.case)
    vdir = os.path.join(root, "build", "voice")
    cfg = json.load(io.open(os.path.join(root, "config.json"), encoding="utf-8"))

    # hash -> id cu (doc tu chinh cac words.json dang co)
    have = {}
    for name in os.listdir(vdir):
        if not name.endswith(".words.json"):
            continue
        old_id = name[len("cell-"):-len(".words.json")]
        try:
            h = json.load(io.open(os.path.join(vdir, name), encoding="utf-8")).get("hash")
        except Exception:
            continue
        if h:
            have.setdefault(h, old_id)

    voice = args.voice
    moves, missing, ok = [], [], 0
    for c in cfg["cells"]:
        vo = c.get("vo")
        if not vo:
            continue
        h = text_hash(vo, voice)
        old = have.get(h)
        new = str(c["id"])
        if old is None:
            missing.append(new)
        elif old == new:
            ok += 1
        else:
            moves.append((old, new))

    print(f"dung cho: {ok} | can doi ten: {len(moves)} | khong co giong: {len(missing)}")
    if missing:
        print(f"  cell thieu giong: {missing[:15]}{' ...' if len(missing) > 15 else ''}")
    if not args.apply:
        for old, new in moves[:10]:
            print(f"  cell-{old} -> cell-{new}")
        if moves:
            print("  (xem truoc — them --apply de lam that)")
        return

    # Doi ten qua thu muc tam: doi truc tiep se de len file chua kip doc.
    tmp = os.path.join(vdir, "_remap")
    os.makedirs(tmp, exist_ok=True)
    for old, new in moves:
        for ext in (".mp3", ".words.json"):
            src = os.path.join(vdir, f"cell-{old}{ext}")
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(tmp, f"cell-{new}{ext}"))
    for name in os.listdir(tmp):
        shutil.move(os.path.join(tmp, name), os.path.join(vdir, name))
    os.rmdir(tmp)
    print(f"da doi ten {len(moves)} cell")


if __name__ == "__main__":
    main()
