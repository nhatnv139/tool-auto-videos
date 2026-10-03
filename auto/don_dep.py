# -*- coding: utf-8 -*-
"""don_dep.py — video nao da ra thanh pham thi xoa sach file may tu sinh.

Luat:
  GIU  — dau vao va thu de nguoi doc lai: script/, references.json,
         clip-manifest.json, config.json, meta.json, publish.md, sources.md,
         cac file *-credit(s).json (KB, de dung nguon).
  XOA  — moi thu may tu tao ra trong luc dung: assets/ (nhac, sfx, clip tai ve),
         build/tmp|shots|trim|voice, cac file .mp3/.wav/.sh/.log trong build.
  VIDEO CUOI — chi giu MOT ban. Neu OUTBOX da co ban sao dung kich thuoc thi
         xoa build/final/video-1.mp4; neu chua co thi giu nguyen tai cho.

Chay:
    python auto\\don_dep.py                 xem se xoa nhung gi (khong dong vao dia)
    python auto\\don_dep.py --that          xoa that
    python auto\\don_dep.py --slug abc      chi mot muc
    python auto\\don_dep.py --hong --that   don ca case chay hong (chua ra video)

Case HONG: mac dinh de nguyen (so xoa mat cai dang cho nguoi xem lai). Nhung
neu khong ai don thi build cua no nam lai mai — mot case 20 phut chet o buoc
assemble bo lai ~4 GB. Runner tu goi --hong sau khi ghi log loi: giu script/ +
config nen chay lai van resume duoc, chi bo phan sinh lai duoc.
"""
import argparse
import io
import os
import shutil
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEOS = os.path.join(KIT, "videos")
OUTBOX = os.path.join(KIT, "OUTBOX")

def _stdout_utf8():
    """Chi goi khi chay truc tiep. Boc lai stdout luc IMPORT se dong mat stdout
    cua tien trinh goi (runner da tu boc roi) -> 'I/O operation on closed file'."""
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")

# thu muc bo di ca cum
DIR_XOA = ["assets",
           "build/tmp", "build/shots", "build/trim",
           "build/voice", "build/voice-edge-backup"]
# file rac ngay trong build/ va trong thu muc case
DUOI_XOA = (".mp3", ".wav", ".sh", ".log", ".err", ".bak")
FINAL = ("build", "final", "video-1.mp4")


def co_kich_thuoc(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def nang(d):
    """tong byte cua mot thu muc"""
    t = 0
    for dirpath, _, files in os.walk(d):
        for fn in files:
            t += co_kich_thuoc(os.path.join(dirpath, fn))
    return t


def ban_sao_outbox(slug, final_path):
    """OUTBOX co ban sao dung kich thuoc cua video cuoi khong?"""
    if not os.path.isdir(OUTBOX):
        return None
    n = co_kich_thuoc(final_path)
    if not n:
        return None
    for d in sorted(os.listdir(OUTBOX)):
        if not d.endswith("-" + slug):
            continue
        p = os.path.join(OUTBOX, d, "video.mp4")
        if co_kich_thuoc(p) == n:
            return p
    return None


def don_mot_case(case, that=False, im=False, ke_ca_hong=False, giu=()):
    """Tra ve (so_byte_don, ghi_chu). ghi_chu != '' nghia la bo qua.
    im=True: khong in tung dong (dung khi goi tu runner).
    ke_ca_hong=True: don ca case CHUA ra video (case chay hong giua chung).
        Van giu script/, references.json, config.json... nen chay lai duoc tu
        buoc dang do; chi bo phan may tu sinh von se sinh lai duoc.
    giu: cac muc trong DIR_XOA khong duoc dung toi, viet nhu trong DIR_XOA
        ("build/voice"). Dung cho case HONG: giong doc la thu dat nhat de sinh
        lai (mot video 20 phut ton ~12 phut goi API va chet neu API dang down)
        nhung lai nhe nhat tren dia (vai chuc MB so voi vai GB cua shots/trim)."""
    slug = os.path.basename(case.rstrip("\\/"))
    final_path = os.path.join(case, *FINAL)
    ngoai = ban_sao_outbox(slug, final_path)
    if not os.path.exists(final_path) and not ngoai and not ke_ca_hong:
        return 0, "chua ra video — de nguyen"

    giu = set(giu)
    giu_tuyet_doi = {os.path.normcase(os.path.join(case, *g.split("/")))
                     for g in giu}
    muc = []  # (duong dan, la_thu_muc, byte)
    for sub in DIR_XOA:
        if sub in giu:
            continue
        d = os.path.join(case, *sub.split("/"))
        if os.path.isdir(d):
            muc.append((d, True, nang(d)))
    for goc in (case, os.path.join(case, "build")):
        if not os.path.isdir(goc):
            continue
        if os.path.normcase(goc) in giu_tuyet_doi:
            continue
        for fn in os.listdir(goc):
            p = os.path.join(goc, fn)
            if os.path.isfile(p) and fn.lower().endswith(DUOI_XOA):
                muc.append((p, False, co_kich_thuoc(p)))
    if ngoai and os.path.exists(final_path):
        muc.append((final_path, False, co_kich_thuoc(final_path)))

    tong = sum(m[2] for m in muc)
    for p, la_dir, n in muc:
        if not im:
            print(f"  - {os.path.relpath(p, KIT)}  ({n / 1e6:.1f} MB)")
        if that:
            if la_dir:
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError as e:
                    print(f"      (khong xoa duoc: {e})")
    if that:
        fin_dir = os.path.dirname(final_path)
        if os.path.isdir(fin_dir) and not os.listdir(fin_dir):
            os.rmdir(fin_dir)
    if not ngoai and os.path.exists(final_path) and not im:
        print(f"  = giu video cuoi (OUTBOX chua co ban sao): "
              f"{os.path.relpath(final_path, KIT)}")
    return tong, ""


def byte_trong(duong_dan=KIT):
    """So byte con trong tren o chua duong_dan."""
    try:
        return shutil.disk_usage(duong_dan).free
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--that", action="store_true", help="xoa that (mac dinh chi xem)")
    ap.add_argument("--slug", default=None)
    ap.add_argument("--hong", action="store_true",
                    help="don ca case chua ra video (case chay hong bo lai build)")
    a = ap.parse_args()

    cases = []
    for d in sorted(os.listdir(VIDEOS)):
        p = os.path.join(VIDEOS, d)
        if os.path.isdir(p) and (not a.slug or d == a.slug):
            cases.append(p)
    if not cases:
        raise SystemExit("khong thay case nao")

    if not a.that:
        print(">> XEM TRUOC — khong xoa gi. Them --that de xoa that.\n")
    tong = 0
    for c in cases:
        slug = os.path.basename(c)
        n, ghi_chu = don_mot_case(c, that=a.that, ke_ca_hong=a.hong)
        if ghi_chu:
            print(f"[bo qua] {slug}: {ghi_chu}")
        else:
            print(f"[{'da don' if a.that else 'se don'}] {slug}: {n / 1e9:.2f} GB\n")
        tong += n
    print(f"--- tong cong: {tong / 1e9:.2f} GB "
          f"{'da giai phong' if a.that else 'se giai phong'}")


if __name__ == "__main__":
    _stdout_utf8()
    main()
