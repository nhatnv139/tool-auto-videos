# -*- coding: utf-8 -*-
"""runner.py — mot lenh, lam het hang doi video.

    python auto\\runner.py                    lam moi muc chua xong trong queue.yml
    python auto\\runner.py --only 1           chi lam 1 video dau tien
    python auto\\runner.py --slug test-1-phut chi lam dung muc nay
    python auto\\runner.py --from render      chay lai tu buoc render tro di
    python auto\\runner.py --step tts render  chi chay dung may buoc nay
    python auto\\runner.py --no-ai            khong goi claude, dung script.md co san
    python auto\\runner.py --list             xem trang thai hang doi
    python auto\\runner.py --reset <slug>     xoa trang thai de lam lai tu dau
    python auto\\runner.py --lam-lai --from images   dung lai HET tu buoc hinh
                                             (giu script da viet, chi doi hinh/tieng)

Ket qua cuoi nam o OUTBOX\\<ngay>-<slug>\\video.mp4
"""
import argparse
import io
import json
import os
import sys
from datetime import datetime

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "auto"))

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import steps as S  # noqa: E402

QUEUE = os.path.join(KIT, "queue.yml")


def load_queue(path=QUEUE):
    import yaml
    if not os.path.exists(path):
        raise SystemExit(f"khong thay {path}")
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    defaults = data.get("defaults") or {}
    out = []
    for v in (data.get("videos") or []):
        item = dict(defaults)
        item.update(v)
        if not item.get("slug"):
            raise SystemExit(f"muc thieu 'slug': {v}")
        out.append(item)
    return out


def trang_thai(slug):
    st = S.load_state(slug)
    return st.get("status", "pending"), st


def cmd_list(items):
    print(f"{'slug':<24} {'trang thai':<10} {'buoc cuoi':<12} de tai")
    print("-" * 90)
    for v in items:
        stt, st = trang_thai(v["slug"])
        done = [n for n in S.STEP_NAMES
                if st.get("steps", {}).get(n, {}).get("status") == "done"]
        last = done[-1] if done else "-"
        print(f"{v['slug']:<24} {stt:<10} {last:<12} {v.get('de_tai', '')[:44]}")
    out = S.OUTBOX
    if os.path.isdir(out):
        n = len([d for d in os.listdir(out) if os.path.isdir(os.path.join(out, d))])
        print(f"\nOUTBOX: {n} thu muc -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=QUEUE)
    ap.add_argument("--only", type=int, default=0, help="chi lam N video dau")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--from", dest="from_step", default=None,
                    choices=S.STEP_NAMES, help="chay lai tu buoc nay")
    ap.add_argument("--step", nargs="+", default=None, choices=S.STEP_NAMES,
                    help="chi chay dung nhung buoc nay")
    ap.add_argument("--no-ai", action="store_true", help="khong goi claude")
    ap.add_argument("--giu-build", action="store_true", help="khong don file trung gian")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--reset", default=None, metavar="SLUG")
    ap.add_argument("--lam-lai", action="store_true", dest="lam_lai",
                    help="lam ca nhung muc da 'done' (dung chung voi --from)")
    a = ap.parse_args()

    items = load_queue(a.queue)

    if a.reset:
        p = S.state_path(a.reset)
        if os.path.exists(p):
            os.remove(p)
            print(f"da xoa trang thai {a.reset}")
        else:
            print(f"khong co trang thai cho {a.reset}")
        return

    if a.list:
        cmd_list(items)
        return

    if a.slug:
        items = [v for v in items if v["slug"] == a.slug]
        if not items:
            raise SystemExit(f"khong co muc slug={a.slug} trong queue")
    elif not a.lam_lai:
        items = [v for v in items if trang_thai(v["slug"])[0] != "done"]
    if a.only:
        items = items[:a.only]

    if not items:
        print("khong con viec — moi muc trong queue deu xong.")
        return

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] hang doi: "
          f"{', '.join(v['slug'] for v in items)}")

    ket_qua = []
    for v in items:
        # Co dong lenh CONG voi field trong queue.yml, khong ghi de. Ban cu gan
        # thang a.no_ai (mac dinh False) nen mot muc dat `no_ai: true` trong
        # queue van bi goi claude viet de len script da duyet — mat script ma
        # khong co canh bao nao.
        v["no_ai"] = a.no_ai or bool(v.get("no_ai"))
        v["giu_build"] = a.giu_build or bool(v.get("giu_build"))
        try:
            r = S.run_case(v, force_from=a.from_step, only_steps=a.step)
        except KeyboardInterrupt:
            print("\ndung theo yeu cau (Ctrl-C). Chay lai runner de tiep tuc.")
            raise SystemExit(130)
        except S.HetDia as e:
            # Het cho thi case sau cung chet y het — di tiep chi ton them vai
            # tieng ffmpeg de roi bao 'No space left on device'. Dung han.
            print(f"\n!! DUNG HANG DOI — het dung luong: {e}")
            con_lai = [x["slug"] for x in items[items.index(v):]]
            print(f"   chua lam: {', '.join(con_lai)}")
            ket_qua.append((v["slug"], "het-dia"))
            break
        except Exception as e:  # loi ngoai du kien: ghi nhan, di tiep video sau
            r = "fail"
            print(f"  XX {v['slug']} loi ngoai du kien: {type(e).__name__}: {e}")
        ket_qua.append((v["slug"], r))

    print("\n--- tong ket ---")
    for slug, r in ket_qua:
        bieu = {"done": "OK  ", "fail": "HONG", "pause": "CHO ",
                "het-dia": "DIA "}.get(r, r)
        extra = ""
        if r == "done":
            st = S.load_state(slug)
            if st.get("steps", {}).get("outbox", {}).get("status") == "done":
                day = datetime.now().strftime("%Y-%m-%d")
                extra = f"-> OUTBOX\\{day}-{slug}\\video.mp4"
            else:
                extra = "(chay tung buoc — chua ra OUTBOX)"
        elif r == "fail":
            extra = f"-> auto\\logs\\{slug}.log"
        elif r == "het-dia":
            extra = "chua bat dau — het dung luong o dia"
        print(f"{bieu} {slug:<24} {extra}")
    if any(r in ("fail", "het-dia") for _, r in ket_qua):
        sys.exit(1)


if __name__ == "__main__":
    main()
