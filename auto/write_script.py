# -*- coding: utf-8 -*-
"""write_script.py — viet script bang `claude -p`: RESEARCH -> DAN Y -> TUNG PHAN.

Day la buoc DUY NHAT trong day chuyen can den AI. Moi buoc khac chi la
subprocess goi tool/run.py.

Vi sao khong viet mot leo nua (ban cu, sao luu o .backup-2026-10-01/auto/):
  - CHET TIMEOUT: mot lan `claude -p` viet ca 20-30 phut + tu tra cuu + tu dem
    -> het 2400s (han-cao-to), 3430s (can-long). Chet la mat trang.
  - LAN MAN: khong co tu lieu trong tay thi model don van hoa my. Do 01/10/2026
    bang check_script.cham_tap_trung: can-long 3,6 chi tiet/150 am tiet, 41%
    loi doc nam trong doan khong ten khong so, 18 chuoi cau lap cau truc;
    ban viet tay Vo Tac Thien: 10,4 | 6% | 1.
Ban moi:
  1. research.chuan_bi(): Wikipedia VI+EN -> facts.json/FACTS.md + dan y
     (moi phan: 1 cau hoi + cac F-id rieng + nhan vat). Python chia do dai.
  2. moi phan mot lan `claude -p` KHONG tool (chi sinh chu, ~1-3 phut), chay
     song song 3 phan. Moi phan CHI thay tinh tiet cua no -> khong lan duoc.
  3. may cham tung phan (check_script.cham_tap_trung + luat rieng) -> truot
     thi viet lai DUNG phan do, khong viet lai ca bai.
  4. ghep: tieu de + hook + [# chuong + [[black]] + ten chuong + than chuong].

Cach goi (runner tu goi qua steps.step_script):
    python auto\\write_script.py videos\\<slug> --de-tai "..." --phut 20 --dang nhan-vat
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_script import (check, cham_tap_trung, la_nhan_vat, bo_dau,  # noqa: E402
                          strip_marks, MARKER_LINE, tach_cau)


def claude_bin():
    """Tim launcher chay duoc tu subprocess.

    Tren Windows `claude` trong PATH la .ps1 — subprocess khong chay truc tiep
    duoc, phai lay ban .cmd.
    """
    for name in ("claude.cmd", "claude.exe", "claude"):
        p = shutil.which(name)
        if p and not p.lower().endswith(".ps1"):
            return p
    p = shutil.which("claude")
    if p and p.lower().endswith(".ps1"):
        cmd = p[:-4] + ".cmd"
        if os.path.exists(cmd):
            return cmd
    raise SystemExit("khong tim thay claude CLI trong PATH")


def _env():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # Neu runner duoc goi TU BEN TRONG mot phien Claude Code thi cac bien nay bi
    # ke thua va phien con chay nhu phien long nhau — bo di cho no la mot phien
    # doc lap.
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT",
              "CLAUDE_CODE_SESSION_ID", "CLAUDE_AGENT_ID"):
        env.pop(k, None)
    return env


def goi_claude(prompt, timeout=900, tools=False, model=None, log=None,
               add_dir=None):
    """Mot lan `claude -p`, prompt qua STDIN. tools=False -> `--tools ""`:
    chi sinh chu, khong doc file/khong tra web — do 01/10/2026 mot cau hoi
    ngan tra ve sau 6s, khong ton vong tool nao.

    Het gio -> (124, "") thay vi nem loi, de vong viet lai xu ly.
    """
    cmd = [claude_bin(), "-p", "--output-format", "text"]
    if tools:
        cmd += ["--permission-mode", "bypassPermissions"]
        if add_dir:
            cmd += ["--add-dir", add_dir]
    else:
        cmd += ["--tools", ""]
    if model:
        cmd += ["--model", str(model)]
    try:
        r = subprocess.run(cmd, cwd=KIT, env=_env(), input=prompt,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        if log:
            log(f"het {timeout}s")
        return 124, ""
    out = r.stdout or ""
    if r.returncode != 0 and log:
        log((out + (r.stderr or "")).strip()[-1500:])
    return r.returncode, out


def run_claude(prompt, case, timeout=2400, log=None):
    """Giu cho step_publish: claude -p CO tool (doc/ghi file trong case).

    Prompt di qua STDIN, khong qua argv: tren Windows launcher la claude.cmd,
    prompt nhieu dong truyen bang argv bi cmd.exe cat o dong dau.
    """
    rc, out = goi_claude(prompt, timeout=timeout, tools=True, add_dir=case)
    if log:
        log(out.strip()[-3000:])
    return rc, out


# =========================================================================
# PROMPT VIET MOT PHAN
# =========================================================================
PROMPT_PHAN = """Ban viet MOT PHAN trong kich ban video YouTube ke su bang tieng Viet
(may TTS doc to tung chu). Tra ve CHI noi dung phan nay: khong loi dan, khong
giai thich, khong code fence, khong tieu de.

VIDEO: {tieu_de} | {phut:g} phut | dang: {dang_mo_ta}
CAU HOI TRUNG TAM: {cau_hoi_tt}
GOC NHIN XUONG SONG: {goc_nhin}
NHAN VAT / CHU DE CHINH: {nv_vi}{nv_khac}

DAN Y CA VIDEO (de biet phan nao ke gi — KHONG lan sang phan khac):
{dan_y}

==> PHAN CUA BAN: so {so}/{tong_phan} [{loai}] {ten}
Cau hoi phan nay tra loi: {cau_hoi}
Y chinh: {y_chinh}
Do dai: ~{am_tiet} am tiet loi doc = DUNG {n_doan} doan loi doc, moi doan
{doan_lo}-{doan_hi} am tiet (1 am tiet = 1 chu tieng Viet).

TINH TIET CUA PHAN NAY (chat lieu duy nhat — ke lai bang loi cua ban):
{facts}

BANG THUC THE (ten doc trong loi -> ent cho marker hinh):
{bang_the}

LUAT BAM DE — may cham tung doan, vi pham la phan nay bi viet lai:
1. Moi doan phai chua it nhat 2 CHI TIET CU THE lay tu tinh tiet tren: ten
   nguoi (khac {nv_vi}), dia danh, nam, con so, ten van ban/hien vat/chuc quan.
   Dich >= 5 chi tiet moi 150 am tiet. Moi tinh tiet tren phai duoc ke ra.
2. Moi doan phai noi ve {nv_vi} hoac mot thuc the trong bang. Khong ke boi canh
   chung ve trieu dai, ve "cuoc song hoang gia", ve "quyen luc", ve "con nguoi".
3. CAM cau khai quat suong — cau ma thay ten mot vi vua/nhan vat khac vao van
   dung. Vi du CAM: "Ong nhin thay chien thang. Nhin thay su giau co.";
   "Cau khong phai lo chuyen kiem song."; "Ngai vang la mot chiec ghe co doc.";
   "Co nguoi trung thanh. Co nguoi tham vong." Thay bang: AI lam GI, O DAU,
   NAM NAO, BAO NHIEU.
4. CAM 3 cau lien nhau mo dau bang cung mot tu ("Nhin thay... Nhin thay...",
   "Khong phai... Khong phai...", "Mot... Mot... Mot..."). CAM chuoi cau hoi
   tu tu liet ke ("Mot minh quan? Mot bao chua? Mot nha tho?").
5. Khong nhac ten nguon trong loi doc ("Wikipedia", "tu lieu", "bai viet") —
   noi "su chep", "cac su gia". Nguon da nam o FACTS.md.
6. Chi ke tinh tiet cua phan nay. Khong ke truoc chuyen cua phan sau, khong tom
   tat lai phan truoc. Khong bia ten, so, cau noi ngoai danh sach tren.
7. Thieu chuyen thi DAO SAU tinh tiet dang co (hoan canh cu the, con so, he qua,
   phan ung cua nguoi trong cuoc) — khong don bang binh luan hay dao ly.

DINH DANG (script2config doc MOI dong khong phai marker thanh loi doc):
- Chi 2 loai dong: dong MARKER HINH (chiem tron mot dong) va dong LOI DOC.
  Khong dong '#', khong '---', khong dong '>', khong ghi chu, khong so thu tu.
- Dong dau tien la marker. Moi doan loi doc nam tren MOT dong, co DUNG mot
  marker ngay tren no. Mot dong trong giua cac khoi.
- MARKER HINH, hai dang:
    [[stock:"<canh tieng Anh cu the>"|ent="<ten bai Wikipedia EN>"]]
        -> doan noi ve nguoi/dia danh/su kien/hien vat co trong BANG THUC THE:
           BAT BUOC co ent, chep DUNG chuoi ent trong bang (vd ent="{vd_ent}").
    [[stock:"<canh tieng Anh cu the>"]]
        -> chi cho doan chuyen canh/khong khi.
  It nhat {pct_ent}% marker co ent. Khong dung ent nao ngoai bang.
  Tu khoa stock: 3-7 tu tieng Anh, la thu CHUP/VE duoc: vat, noi chon, hanh
  dong, dung thoi dai (vd "Qing official kneeling in throne hall", "silver
  ingots stacked in treasury", "Chengde mountain resort lake"). CAM tu truu
  tuong (power, glory, destiny, ambition, loneliness, legacy, everything,
  wanted, burden, greatness...). Toi da 1/4 tu khoa mo bang "ancient Chinese" —
  ghi thang trieu dai / dia danh / do vat.
- Loi doc:
  * Nam va con so viet bang chu so: "nam 1750", "800 trieu lang bac".
  * KHONG dung dau gach dai '—' trong loi doc (may doc thanh dau cham).
  * Ky tu ngat nghi dat THUA TAY ngay trong loi doc: '//' lang 0,8s (het y),
    '///' lang 1,5s (chuyen y lon), '^' dau cau dau tien cua phan, '*cau*' cho
    dung mot cau chot. {lieu_ngat}
  * Viet thanh doan lien mach 3-5 cau, xen cau dai 20-35 am tiet voi cau ngan.
    Khong chat moi cau mot dong. Toi da 45% so cau duoi 10 am tiet.
{luat_loai}"""

# ---- luat theo loai phan x dang (rut tu skill su-nhan-vat / truyen-van-hoa) ----
NV_CHUNG = ("- Xung ho: goi nhan vat la \"ong\"/\"ba\", goi nguoi xem la \"cac ban\". "
            "KHONG dung \"chung ta\".\n"
            "- Tu noi dao chieu (nhung, tuy nhien, the nhung, dau vay) khoang 1 lan "
            "moi phut — moi lan la mot cu be lai.\n")
LUAT = {
    ("nhan-vat", "hook"): NV_CHUNG + (
        "- HOOK 45-50 giay, 5 nhip lien nhau: (1) mot cau chao kenh ngan; (2) neo "
        "dieu nguoi xem DA BIET ve nhan vat; (3) them mot net gai; (4) LAT: cau "
        "tuyen bo \"Tuy nhien, neu cac ban nghi rang [X], thi cac ban da mac mot "
        "sai lam to lon.\" — tuyen bo, khong hoi; (5) hua: ten that + tam voc "
        "viec lam, co con so.\n"
        "- Moi nhip phai co ten hoac so that, khong chao hoi dai dong.\n"),
    ("nhan-vat", "chuong"): NV_CHUNG + (
        "- CANH TRUOC, HO SO SAU: cau dau tien cua phan PHAI mo bang NAM (chu so) "
        "-> noi chon -> viec dang dien ra -> mot khoanh khac. Xong roi moi toi "
        "chuc tuoc/ho so. Cam mo bang dinh nghia hay du lieu kho.\n"
        "- Cau cuoi phan: mot cau chot ngan hoac mot moc dan sang chuong sau "
        "(khong ke truoc noi dung chuong sau).\n"),
    ("nhan-vat", "chuong_cuoi"): NV_CHUNG + (
        "- Day la CHUONG PHAN TICH NGUYEN NHAN. Viet nhu bai luan danh so: "
        "\"Nguyen nhan dau tien, ve mat khach quan, ...\", \"Tuy nhien ly do o phan "
        "chu quan moi giai thich vi sao ...\", \"Sai lam chu quan thu ba ...\". "
        "Moi nguyen nhan gan voi mot tinh tiet cu the (ten, nam, so) da co.\n"
        "- KHONG ket bang cam than hay cau hoi moi binh luan. Cau cuoi cung tha "
        "mot mat xich lich su sang de tai khac (nhan vat/su kien ke tiep).\n"),
    ("nhan-vat", "chao_lai"): (
        "- Phan nay nam o GIUA video: mo bang khoi ~40 giay chao lai khan gia "
        "(\"Chao mung cac ban quay tro lai voi kenh...\") + tom tat bang mot cum "
        "lap 3-4 lan lam nhip trong, moi lan gan mot tinh tiet that da ke / sap "
        "ke. Roi moi vao canh mo chuong.\n"),
    ("van-hoa", "hook"): (
        "- HOOK 40 giay, 5 nhip: (1) neo: thoi gian lon + vat quen thuoc, vao "
        "thang; (2) phu dinh: noi cai no KHONG phai; (3) nghich ly: hai cuc canh "
        "nhau; (4) ba cau hoi don dap, cau sau hep hon, cau cuoi A-hay-B; (5) mot "
        "cau hua co dong tu manh + \"ngay sau day\".\n"
        "- Xung \"chung ta\", khong \"toi/minh\". Khong chao, khong logo.\n"),
    ("van-hoa", "chuong"): (
        "- Mo phan bang MOT cau hoi dan, roi boc lop: vo de thay -> \"Nhung neu "
        "xuyen thau vao...\" -> loi co che. Moi lop gan voi tinh tiet cu the.\n"
        "- Xung \"chung ta\". Dong phan bang teaser hoac mot cau chot <= 10 am tiet.\n"),
    ("van-hoa", "chuong_cuoi"): (
        "- Day la KET, 3 lop: (1) tong ket + TRA LOI THANG cau hoi trung tam; "
        "(2) nang tam len dan toc/nhan sinh; (3) mot cau hoi ca nhan hoa moi "
        "binh luan + \"Hen gap lai cac ban o nhung chu de tiep theo.\"\n"
        "- Xung \"chung ta\".\n"),
    ("*", "ngan"): (
        "- Video rat ngan: mot cau mo nghich ly co ten/so that, 1-2 tinh tiet "
        "chung minh, mot cau chot. Khong chao.\n"),
}


def _dang(dang):
    return "nhan-vat" if la_nhan_vat(dang) else "van-hoa"


def _loai_luat(f, idx, dang):
    phan = f["dan_y"]["phan"]
    p = phan[idx]
    d = _dang(dang)
    if p["loai"] == "ngan":
        return [("*", "ngan")]
    if p["loai"] == "hook":
        return [(d, "hook")]
    keys = []
    if p.get("chao_lai"):
        keys.append((d, "chao_lai"))
    keys.append((d, "chuong_cuoi" if idx == len(phan) - 1 else "chuong"))
    return keys


def _bang_the(f):
    """{en_lower: vi} chi gom ten bai EN da kiem la ton tai."""
    out = {}
    nv = f.get("nhan_vat_chinh") or {}
    if nv.get("en"):
        out[nv["en"]] = nv.get("vi", "")
    for e in f.get("the", []):
        if e.get("hop_le") and e.get("en"):
            out[e["en"]] = e.get("vi", "")
    return out


def _facts_cua(f, idx):
    ids = f["dan_y"]["phan"][idx].get("facts") or []
    by = {x.get("id"): x for x in f.get("facts", [])}
    return [by[i] for i in ids if i in by]


def _doan_cfg(am_tiet, dang, wpm):
    # nhan-vat: marker giu 12-18s -> doan ~ 15s loi doc; van-hoa 6-9s
    giay = 15.0 if la_nhan_vat(dang) else 8.0
    tb = max(25, int(wpm * giay / 60))
    n = max(1, round(am_tiet / tb))
    return n, int(tb * 0.75), int(tb * 1.3)


def build_prompt_phan(f, idx, de_tai, goc_nhin, phut, wpm, dang,
                      ban_cu="", loi_cu=None):
    dy = f["dan_y"]
    phan = dy["phan"]
    p = phan[idx]
    nv = f.get("nhan_vat_chinh") or {}
    bang = _bang_the(f)
    facts = _facts_cua(f, idx)
    # thuc the lien quan phan nay len dau bang — model chep ent tu day
    lien = set(p.get("nhan_vat") or [])
    for x in facts:
        lien.update(x.get("the") or [])
    lien.add(nv.get("en", ""))
    thu_tu = sorted(bang.items(), key=lambda kv: (kv[0] not in lien, kv[0]))
    dong_dy = []
    for i, q in enumerate(phan):
        mui = "   <== BAN VIET PHAN NAY" if i == idx else ""
        dong_dy.append(f"  {i + 1}. [{q['loai']}] {q.get('ten') or '(hook)'} — "
                       f"{q.get('cau_hoi', '')}{mui}")
    n_doan, lo, hi = _doan_cfg(p["am_tiet"], dang, wpm)
    luat = "".join(LUAT.get(k, "") for k in _loai_luat(f, idx, dang))
    lieu = ("Dang nay ke lien tuc (im lang ~3,5%): ca phan chi 1-3 dau '//', "
            "toi da 1 dau '///'." if la_nhan_vat(dang) else
            "Moi 5 phut chi 3-5 dau '//' va 1-2 dau '///'.")
    vd_ent = thu_tu[0][0] if thu_tu else "Heshen"
    prompt = PROMPT_PHAN.format(
        tieu_de=dy.get("tieu_de", de_tai), phut=phut,
        dang_mo_ta=("nhan vat (skill su-nhan-vat)" if la_nhan_vat(dang)
                    else "van hoa (skill truyen-van-hoa)"),
        cau_hoi_tt=dy.get("cau_hoi_trung_tam", ""), goc_nhin=goc_nhin or "(tu chon)",
        nv_vi=nv.get("vi", de_tai),
        nv_khac=(" (goi khac: " + ", ".join(nv["goi_khac"]) + ")")
        if nv.get("goi_khac") else "",
        dan_y="\n".join(dong_dy), so=idx + 1, tong_phan=len(phan),
        loai=p["loai"], ten=p.get("ten", ""), cau_hoi=p.get("cau_hoi", ""),
        y_chinh=p.get("y_chinh", ""), am_tiet=p["am_tiet"], n_doan=n_doan,
        doan_lo=lo, doan_hi=hi,
        facts="\n".join(f"  {x.get('id')} [{x.get('nam', '')}] {x.get('noi_dung', '')}"
                        f"  (thuc the: {', '.join(x.get('the') or [])})"
                        for x in facts) or "  (khong co — dung tinh tiet trong dan y)",
        bang_the="\n".join(f"  {vi} -> ent=\"{en}\"" for en, vi in thu_tu),
        vd_ent=vd_ent, pct_ent=50 if la_nhan_vat(dang) else 30,
        lieu_ngat=lieu, luat_loai=luat)
    if ban_cu and loi_cu:
        prompt += ("\n\nBAN TRUOC CUA PHAN NAY bi may cham TRUOT:\n<<<\n" + ban_cu +
                   "\n>>>\nLOI CAN SUA:\n- " + "\n- ".join(loi_cu) +
                   "\nViet lai TOAN BO phan nay, sua dung cac loi tren, giu nhung "
                   "doan da dat.\n")
    return prompt


# =========================================================================
# CHAM MOT PHAN
# =========================================================================
def lam_sach(out):
    """Bo code fence / loi dan model lo tay them vao dau-cuoi."""
    lines = []
    for l in (out or "").replace("\r", "").splitlines():
        s = l.strip()
        if s.startswith("```"):
            continue
        lines.append(l.rstrip())
    # bo moi dong truoc marker dau tien (loi dan kieu "Day la phan 2:")
    for i, l in enumerate(lines):
        if MARKER_LINE.match(l.strip()):
            lines = lines[i:]
            break
    return "\n".join(lines).strip() + "\n"


def am_tiet(text):
    vo = [l.strip() for l in text.splitlines()
          if l.strip() and not l.strip().startswith("#")
          and not MARKER_LINE.match(l.strip())]
    return len(strip_marks(" ".join(vo)).split())


def cham_phan(text, f, idx, dang, wpm):
    """-> (loi[], so{}) cho MOT phan. Luat giong check_script nhung o cap phan,
    de viet lai dung phan hong."""
    p = f["dan_y"]["phan"][idx]
    loi = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return ["phan rong (claude khong tra noi dung / het gio)"], {}
    if not MARKER_LINE.match(lines[0]):
        loi.append("dong dau tien phai la marker hinh")
    for l in lines:
        if l.startswith("#") or l.startswith(">") or set(l) <= set("-=*_ "):
            loi.append(f"dong khong hop le (se bi doc to hoac lam lech chuong): \"{l[:50]}\"")
            break
    prev_vo = False
    for l in lines:
        la_mk = bool(MARKER_LINE.match(l))
        if not la_mk and prev_vo:
            loi.append(f"hai dong loi doc lien nhau khong co marker o giua: \"{l[:50]}\"")
            break
        prev_vo = not la_mk
    at = am_tiet(text)
    dich = p["am_tiet"]
    tol = 0.3 if p["loai"] in ("hook", "ngan") else 0.2
    if at < dich * (1 - tol):
        loi.append(f"phan NGAN: {at} am tiet, can ~{dich} (>= {int(dich * (1 - tol))}). "
                   f"Dao sau tinh tiet dang co, khong don binh luan")
    elif at > dich * (1 + tol):
        loi.append(f"phan DAI: {at} am tiet, can ~{dich} (<= {int(dich * (1 + tol))})")
    if any("—" in l for l in lines if not MARKER_LINE.match(l)):
        loi.append("co dau '—' trong loi doc — doi thanh dau phay/cham")

    tt = cham_tap_trung(text, f, dang)
    loi += tt["loi"]

    vo = strip_marks(" ".join(l for l in lines if not MARKER_LINE.match(l)))
    # facts cua phan co duoc ke ra khong: moi fact can >= 1 con so (>= 2 chu so)
    # hoac 1 ten thuc the (khong phai nhan vat chinh) xuat hien trong loi doc
    ten_vi = {e.get("en"): e.get("vi", "") for e in f.get("the", [])}
    nv_en = (f.get("nhan_vat_chinh") or {}).get("en")
    vo_kd = bo_dau(vo).lower()
    facts = _facts_cua(f, idx)
    dung = 0
    for x in facts:
        so = re.findall(r"\d{2,}", x.get("noi_dung", "") + " " + str(x.get("nam", "")))
        ten = [bo_dau(ten_vi.get(t, "")).lower() for t in x.get("the") or []
               if t != nv_en and ten_vi.get(t)]
        if any(s in vo for s in so) or any(t and t in vo_kd for t in ten):
            dung += 1
    if facts and p["loai"] != "hook" and dung < max(1, round(len(facts) * 0.5)):
        loi.append(f"chi ke {dung}/{len(facts)} tinh tiet duoc giao — phai ke it "
                   f"nhat {max(1, round(len(facts) * 0.5))}, dung tinh tiet thay cho binh luan")

    # test 12 phut 01/10: "Wikipedia tieng Viet danh gia thuyet ay..." lot vao
    # loi doc vi model thay nhan nguon trong tu lieu
    if re.search(r"wikipedia", vo, re.I):
        loi.append("loi doc nhac 'Wikipedia' — noi 'su chep'/'cac su gia', bo ten nguon")

    if la_nhan_vat(dang):
        if re.search(r"\bchúng ta\b", vo, re.I):
            loi.append("dang nhan vat khong dung \"chung ta\" — goi nguoi xem la \"cac ban\"")
        cau = tach_cau(vo)
        if cau:
            cut = sum(1 for c in cau if len(c.split()) <= 10) / len(cau)
            if cut > 0.5:
                loi.append(f"{cut*100:.0f}% cau ngan duoi 10 am tiet (toi da 45%) — "
                           f"gop thanh cau dai 20-35 am tiet")
        la_cuoi = idx == len(f["dan_y"]["phan"]) - 1
        if p["loai"] == "chuong" and not la_cuoi and not p.get("chao_lai"):
            dau = " ".join(vo.split()[:30])
            if not re.search(r"\d{3,4}", dau):
                loi.append("chuong phai mo bang CANH co NAM (chu so) trong cau dau "
                           "tien: nam -> noi chon -> viec dang dien ra")
    return loi, dict(tt["so"], am_tiet=at, facts_dung=f"{dung}/{len(facts)}")


# =========================================================================
# VIET + GHEP
# =========================================================================
SO_CHU_VI = ["một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười"]


def ghep(f, texts, dang):
    dy = f["dan_y"]
    out = [f"# {dy.get('tieu_de', '').strip() or 'KICH BAN'}", ""]
    pause = "2.5" if la_nhan_vat(dang) else "5.0"
    so = 0
    for p, t in zip(dy["phan"], texts):
        if p["loai"] == "chuong":
            ten = (p.get("ten") or "").strip().rstrip(".")
            chu = SO_CHU_VI[so] if so < len(SO_CHU_VI) else str(so + 1)
            so += 1
            out += [f"# CHƯƠNG {so} — {ten.upper()}", "",
                    f"[[black|pause={pause}]]",
                    f"Chương {chu}. // {ten[:1].upper() + ten[1:]}.", ""]
        out.append(t.strip())
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def write(case, de_tai, goc_nhin, phut, wpm=187.0, max_vong=3, log=print,
          timeout=2400, dang="", v=None):
    """Research -> dan y -> viet tung phan song song -> cham -> ghep.

    Tra ve ket qua check() cua ca bai (+ 'thoi_gian_s').
    """
    import research
    v = v or {}
    t0 = time.time()
    sdir = os.path.join(case, "script")
    pdir = os.path.join(sdir, "phan")
    os.makedirs(pdir, exist_ok=True)
    model = v.get("model_script")
    # han cho MOT lan goi — mot phan 900 am tiet do ra ~2-4 phut; 2400s cu la
    # han cho ca bai viet mot leo
    han = int(min(timeout, v.get("timeout_phan", 900)))

    f = research.chuan_bi(case, de_tai, goc_nhin, phut, wpm, dang, v, log,
                          timeout=int(min(timeout, 1800)))
    phan = f["dan_y"]["phan"]
    # chao lai giua video (skill su-nhan-vat, video > 20 phut)
    if la_nhan_vat(dang) and phut > 20:
        chuong = [i for i, p in enumerate(phan) if p["loai"] == "chuong"]
        if len(chuong) >= 3:
            phan[chuong[len(chuong) // 2]]["chao_lai"] = True
    n = len(phan)
    khoa = f.get("_khoa", "")

    def file_phan(i):
        return os.path.join(pdir, f"{i + 1:02d}-{khoa}.md")

    texts = [""] * n
    loi_phan = [None] * n
    # dung lai phan da viet cua lan chay truoc (cung khoa) neu con dat
    for i in range(n):
        if os.path.exists(file_phan(i)):
            texts[i] = open(file_phan(i), encoding="utf-8").read()
            loi_phan[i], _ = cham_phan(texts[i], f, i, dang, wpm)

    def viet(i, vong):
        t1 = time.time()
        prompt = build_prompt_phan(f, i, de_tai, goc_nhin, phut, wpm, dang,
                                   ban_cu=texts[i] if loi_phan[i] else "",
                                   loi_cu=loi_phan[i])
        rc, out = goi_claude(prompt, timeout=han, tools=False, model=model,
                             log=lambda s: log(f"    | phan {i + 1}: {s}"))
        txt = lam_sach(out) if rc == 0 else ""
        loi, so = cham_phan(txt, f, i, dang, wpm)
        return i, txt, loi, so, time.time() - t1, rc

    song_song = int(v.get("song_song", 3))
    for vong in range(1, max_vong + 1):
        can = [i for i in range(n) if loi_phan[i] is None or loi_phan[i]]
        if not can:
            break
        log(f"    vong {vong}/{max_vong}: viet {len(can)}/{n} phan "
            f"({', '.join(str(i + 1) for i in can)}), song song {song_song}")
        with ThreadPoolExecutor(max_workers=song_song) as ex:
            for i, txt, loi, so, dt, rc in ex.map(lambda i: viet(i, vong), can):
                # ban moi te hon ban cu (rong/het gio/nhieu loi hon) thi giu ban cu
                cu = loi_phan[i]
                if not texts[i].strip() or (txt.strip() and
                                            (cu is None or len(loi) <= len(cu))):
                    texts[i], loi_phan[i] = txt, loi
                    if txt.strip():
                        open(file_phan(i), "w", encoding="utf-8").write(txt)
                log(f"    phan {i + 1} [{phan[i]['loai']}] {dt:.0f}s rc={rc}: "
                    f"{so.get('am_tiet', 0)}/{phan[i]['am_tiet']} am tiet, "
                    f"diem {so.get('diem_tap_trung', '?')}, chi tiet/150 "
                    f"{so.get('chi_tiet_150', '?')}, ent {so.get('marker_ent_pct', '?')}%, "
                    f"facts {so.get('facts_dung', '?')}"
                    + ("" if not loi else " -> TRUOT: " + " | ".join(e[:120] for e in loi)))

    if any(not t.strip() for t in texts):
        raise RuntimeError("co phan khong viet duoc (het gio/loi claude): " +
                           ", ".join(str(i + 1) for i, t in enumerate(texts) if not t.strip()))
    open(os.path.join(sdir, "script.md"), "w", encoding="utf-8").write(
        ghep(f, texts, dang))

    res = check(case, phut, wpm, dang=dang)
    log(f"    cham ca bai: {json.dumps(res['so'], ensure_ascii=False)}")
    log(f"    tap trung: {json.dumps(res.get('tap_trung', {}), ensure_ascii=False)}")
    for c in res.get("canh_bao", []):
        log(f"    (canh bao) {c}")
    for e in res["loi"]:
        log(f"    LECH: {e}")

    if not res["ok"]:
        # Phan nao con loi sau het vong -> ghi ro; con lai la lech do dai tong
        # 20-40% thi van dung duoc (video dai/ngan hon chut khong hong), con
        # rac/lan man thi KHONG tha.
        chi_do_dai = all(("script DAI" in e or "script NGAN" in e or "s/anh" in e)
                         for e in res["loi"])
        ty_le = (res["so"].get("phut_video") or 0) / phut if phut else 9
        if chi_do_dai and 0.7 <= ty_le <= 1.4:
            log(f"    (chap nhan) script ra {ty_le:.2f} lan muc tieu — van dung "
                f"duoc, di tiep")
            res = dict(res, ok=True, chap_nhan_lech=True)
        else:
            con = [i + 1 for i in range(n) if loi_phan[i]]
            if con:
                res["loi"].append(f"phan con truot sau {max_vong} vong: {con} "
                                  f"(xem script/phan/)")
    res["thoi_gian_s"] = round(time.time() - t0)
    log(f"    tong thoi gian viet: {res['thoi_gian_s']}s")
    return res


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--de-tai", required=True, dest="de_tai")
    ap.add_argument("--goc-nhin", default="", dest="goc_nhin")
    ap.add_argument("--phut", type=float, required=True)
    ap.add_argument("--wpm", type=float, default=187.0,
                    help="am tiet moi PHUT VIDEO (mac dinh 187, do thuc)")
    ap.add_argument("--dang", default="")
    a = ap.parse_args()
    r = write(os.path.abspath(a.case), a.de_tai, a.goc_nhin, a.phut, a.wpm,
              dang=a.dang)
    sys.exit(0 if r and r["ok"] else 1)


if __name__ == "__main__":
    main()
