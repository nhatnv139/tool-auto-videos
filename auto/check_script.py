# -*- coding: utf-8 -*-
"""check_script.py — cham script.md truoc khi dung.

Ban tong quat hoa tu videos/chu-nguyen-chuong-tam-luoi/check.py: nhan muc tieu
do dai (phut) tu queue thay vi hard-code, va tra ve ket qua dang dict de runner
tu quyet dinh viet lai hay di tiep.

Dung truc tiep:  python auto\\check_script.py videos\\<slug> --phut 20
"""
import json
import os
import re
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "tool"))

from tts import strip_marks  # noqa: E402

MARKER_LINE = re.compile(r"^\[\[.+\]\]$")


def read_vo(raw):
    """Tach rieng loi doc — DUNG luat cua script2config.

    script2config chi bo qua dong rong va dong bat dau bang '#'. Moi dong con
    lai khong phai marker deu thanh LOI DOC. Cham theo dung luat do thi moi
    thay duoc rac (ghi chu style, dong '---') truoc khi may doc to len.
    """
    vo = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if MARKER_LINE.match(s):
            continue
        vo.append(s)
    return strip_marks(" ".join(vo))


def tim_rac(raw):
    """Dong khong phai loi doc nhung se bi doc to len."""
    rac = []
    thay_marker = False
    for i, line in enumerate(raw.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if MARKER_LINE.match(s):
            thay_marker = True
            continue
        if set(s) <= set("-=*_ ") or s.startswith(">"):
            rac.append((i, s[:60], "dong ke/trich dan"))
        elif not thay_marker:
            rac.append((i, s[:60], "van xuoi truoc marker dau tien"))
    return rac


def la_nhan_vat(dang):
    return str(dang or "").strip().lower() in ("nhan-vat", "nhan_vat", "nhanvat")


# =========================================================================
# CHAM TAP TRUNG — may do do "lan man", khong chi nhac trong prompt.
#
# Benh do tren videos/can-long-sau-muoi-nam (01/10/2026): ca doan "Ong nhin
# thay chien thang. Nhin thay su giau co. Nhin thay nhung cung dien..." — cau
# thay ten vua nao vao cung dung. Bon phep do duoi day bat dung benh do:
#   1. mat do CHI TIET: ten rieng KHAC nhan vat chinh + con so, tren 150 am
#      tiet. Ten nhan vat chinh khong tinh — "Can Long da nhin thay tat ca"
#      co ten ma van rong.
#   2. doan SUONG: doan >= 25 am tiet khong co mot chi tiet nao.
#   3. LAP CAU TRUC: >= 3 cau lien nhau mo bang cung mot tu ("Nhin thay...",
#      "Khong phai...", "Co nguoi...", "Hoc...").
#   4. doan BAM: doan co nhac nhan vat chinh hoac mot thuc the trong FACTS.
# Cong them cham MARKER HINH theo hop dong moi [[stock:"..."|ent="..."]].
# =========================================================================

MARKER_HINH = re.compile(
    r'^\[\[(stock|wiki):"([^"]*)"((?:\|[^\]]*)?)\]\]$')
ENT_OPT = re.compile(r'\|\s*ent\s*=\s*"([^"]+)"')

# tu mo cau pho bien — dung dau cau thi viet hoa nhung KHONG phai ten rieng
TU_MO_CAU = set("""ong ba cau co chang ho no han nguoi nhung va khi nam khong
mot do day ngay sau trong vi boi neu the tuy luc hay chi ma cac nhung ca rot
vay du tu voi tat con chinh ai dieu cho den tai o tren duoi giua sau truoc
roi lai cung da dang se moi nhieu it hon bon hai ba nam sau bay tam chin muoi
thay tien quan dan vua chua hoang tuong phan chuong luc bay gio hom nay thoi
suot tung gan hau rat qua dung hoac chac co le""".split())
# dai tu lam chu ngu — lap "Ong ... Ong ... Ong" la chuyen binh thuong khi ke,
# nen voi nhom nay phai trung ca HAI tu dau moi tinh la lap cau truc
DAI_TU = set("ong ba cau ho no han nguoi chang co anh em toi chung".split())
# tu khoa hinh TRUU TUONG — khong chup duoc, API anh tra ve thu vo nghia
TRUU_TUONG = set("""power glory everything wanted want wants loneliness lonely
burden destiny fate ambition legacy success failure concept idea symbol
symbolic greatness truth meaning thinking thought thoughts mystery secret
emotion emotions hope fear pride honor honour dream dreams future past history
change changing era peak decline rise fall value values freedom control
influence authority wisdom genius""".split())


def bo_dau(s):
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


_HOA = re.compile(r"^[A-ZÀ-ỸĐ][a-zà-ỹđ]*$")


def _hoa(tok):
    return bool(_HOA.match(tok)) and tok[:1] == tok[:1].upper() and tok[:1].isalpha()


def tach_cau(text):
    return [c.strip() for c in re.split(r"(?<=[.!?…:;])\s+", text) if c.strip()]


def ten_rieng(cau):
    """Cac cum ten rieng trong mot cau (cum tu viet hoa lien nhau).

    Tu dau cau: bo neu la tu mo cau thong dung ("Nhung Can Long" -> "Can Long",
    "Ong" -> bo). Cum 1 tu o dau cau cung bo — khong phan biet duoc ten rieng.
    """
    toks = [re.sub(r"[^\wÀ-ỹđĐ]", "", t) for t in cau.split()]
    out, i = [], 0
    while i < len(toks):
        if toks[i] and _hoa(toks[i]):
            j = i
            while j < len(toks) and toks[j] and _hoa(toks[j]):
                j += 1
            cum = toks[i:j]
            if i == 0:
                while cum and bo_dau(cum[0]).lower() in TU_MO_CAU:
                    cum = cum[1:]
                if len(cum) < 2 and j - i == len(cum):
                    cum = []           # mot tu viet hoa dung dau cau: mo ho
            if cum:
                out.append(" ".join(cum))
            i = j
        else:
            i += 1
    return out


def doc_facts(case_dir):
    """facts.json (may doc) do auto/research.py ghi. Khong co thi tra None."""
    p = os.path.join(case_dir, "script", "facts.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _ten_chinh(facts, dem_ten, tieu_de=""):
    """Tap ten (da bo dau, thuong) chi nhan vat/chu de chinh."""
    ten = set()
    if facts and facts.get("nhan_vat_chinh"):
        nv = facts["nhan_vat_chinh"]
        for t in [nv.get("vi", "")] + list(nv.get("goi_khac") or []):
            if t:
                ten.add(bo_dau(t).lower())
    if not ten and dem_ten:
        # script cu khong co facts: ten rieng >= 2 tu, uu tien ten co trong
        # dong tieu de video. Chi lay "nhac nhieu nhat" thi can-long ra dung
        # nhung vo-tac-thien ra "Cao Tong", chu-nguyen-chuong ra "Trung Hoa".
        td = bo_dau(tieu_de).lower()
        top = sorted(((v, k) for k, v in dem_ten.items() if len(k.split()) >= 2),
                     reverse=True)
        trong_td = [k for _v, k in top if k in td]
        if trong_td:
            ten.add(trong_td[0])
        elif top:
            ten.add(top[0][1])
    return ten


def doan_loi_doc(raw):
    """[(marker_truoc, text_loi_doc)] — moi dong loi doc la mot doan."""
    out, mk = [], None
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if MARKER_LINE.match(s):
            mk = s
            continue
        out.append((mk, strip_marks(s)))
    return out


def cham_tap_trung(raw, facts=None, dang=""):
    """Tra ve {"so": {...}, "loi": [...], "canh_bao": [...], "doan_hong": [...]}.

    Nguong dat tu so do (01/10/2026), xem bang trong bao cao — ban viet tay
    vo-tac-thien la chuan tren, can-long la chuan duoi:
      chi_tiet_150  (ten khac + so / 150 am tiet)   vtt 10,4 | can-long 3,6
      doan_suong    (% am tiet nam trong doan rong)  vtt 6%   | can-long 41%
      lap_cau_truc  (chuoi >=3 cau cung mo)          vtt 1    | can-long 18
      doan_bam      (% doan nhac nv chinh/thuc the)  vtt 83%  | can-long 65%
    (tan-thuy-hoang 5,1 | 43% | 4 | 51% ; chu-nguyen-chuong 3,3 | 54% | 1 | 28%)
    Diem: vtt 84, tan-thuy-hoang 48, chu-nguyen-chuong 38, can-long 35 — ca
    bon deu 0% marker co ent vi hop dong ent moi co tu 01/10/2026.
    """
    nhan_vat = la_nhan_vat(dang)
    doan = doan_loi_doc(raw)
    # --- ten rieng toan bai ---
    dem = {}
    cau_all = []
    for _mk, t in doan:
        for c in tach_cau(t):
            cau_all.append(c)
            for n in ten_rieng(c):
                k = bo_dau(n).lower()
                dem[k] = dem.get(k, 0) + 1
    tieu_de = next((l.lstrip("#").strip() for l in raw.splitlines()
                    if l.strip().startswith("#")), "")
    chinh = _ten_chinh(facts, dem, tieu_de)
    ten_facts = set()
    if facts:
        for e in facts.get("the") or []:
            if e.get("vi"):
                ten_facts.add(bo_dau(e["vi"]).lower())

    def la_chinh(k):
        return any(k == c or k in c or c in k for c in chinh) if chinh else False

    tong_at = chi_tiet = at_suong = so_doan_bam = so_doan_dem = 0
    doan_hong = []
    for idx, (_mk, t) in enumerate(doan):
        at = len(t.split())
        if not at:
            continue
        tong_at += at
        so = len(re.findall(r"\d+", t))
        khac = [n for c in tach_cau(t) for n in ten_rieng(c)
                if not la_chinh(bo_dau(n).lower())]
        ct = so + len(khac)
        chi_tiet += ct
        t_kd = bo_dau(t).lower()
        bam = any(c in t_kd for c in chinh) or any(f in t_kd for f in ten_facts) \
            or bool(khac)
        if at >= 25:
            so_doan_dem += 1
            if bam:
                so_doan_bam += 1
            if ct == 0:
                at_suong += at
                doan_hong.append(t[:90])

    # --- lap cau truc ---
    chuoi = 0
    cau_lap = []
    i = 0
    while i < len(cau_all):
        def mo(c, n):
            w = [bo_dau(x).lower().strip(",.") for x in c.split()[:n]]
            return tuple(w)
        w1 = mo(cau_all[i], 1)
        khoa_n = 2 if (w1 and w1[0] in DAI_TU) else 1
        k = mo(cau_all[i], khoa_n)
        j = i + 1
        while j < len(cau_all) and mo(cau_all[j], khoa_n) == k:
            j += 1
        if j - i >= 3 and k:
            chuoi += 1
            cau_lap.append(" / ".join(c[:40] for c in cau_all[i:i + 3]))
        i = j

    # --- cau khai quat suong dai: >= 22 am tiet, khong ten, khong so ---
    dai_suong = [c for c in cau_all if len(c.split()) >= 22
                 and not re.search(r"\d", c)
                 and not [n for n in ten_rieng(c) if not la_chinh(bo_dau(n).lower())]]

    # --- marker hinh ---
    mks = [m for m, _ in doan if m]
    mk_all = [l.strip() for l in raw.splitlines() if MARKER_HINH.match(l.strip())]
    n_mk = len(mk_all)
    co_ent = ent_sai = truu = ac = 0
    ent_hop_le = set()
    if facts:
        for e in facts.get("the") or []:
            if e.get("en") and e.get("hop_le", True):
                ent_hop_le.add(e["en"].strip().lower())
        nv = facts.get("nhan_vat_chinh") or {}
        if nv.get("en"):
            ent_hop_le.add(nv["en"].strip().lower())
    ent_la = []
    kw_truu = []
    for m in mk_all:
        g = MARKER_HINH.match(m)
        loai, kw, opt = g.group(1), g.group(2), g.group(3)
        e = kw if loai == "wiki" else (ENT_OPT.search(opt).group(1)
                                       if ENT_OPT.search(opt) else "")
        if e:
            co_ent += 1
            if ent_hop_le and e.strip().lower() not in ent_hop_le:
                ent_sai += 1
                ent_la.append(e)
        if loai == "stock":
            ws = re.findall(r"[a-z]+", kw.lower())
            if kw.lower().startswith("ancient chinese"):
                ac += 1
            if len(ws) < 2 or sum(1 for w in ws if w in TRUU_TUONG) >= 1 and \
                    sum(1 for w in ws if w not in TRUU_TUONG) < 3:
                truu += 1
                kw_truu.append(kw)
    del mks

    per150 = chi_tiet / tong_at * 150 if tong_at else 0
    ty_suong = at_suong / tong_at if tong_at else 0
    ty_bam = so_doan_bam / so_doan_dem if so_doan_dem else 0
    ty_ent = co_ent / n_mk if n_mk else 0
    ty_ac = ac / n_mk if n_mk else 0
    lap_1000 = chuoi / tong_at * 1000 if tong_at else 0

    # diem 0-100: 30 chi tiet + 25 khong suong + 15 khong lap + 15 bam + 15 marker
    s1 = min(1.0, per150 / 6.0)
    s2 = 1 - min(1.0, ty_suong / 0.30)
    s3 = 1 - min(1.0, lap_1000 / 4.0)
    s4 = min(1.0, ty_bam / 0.90)
    s5 = (min(1.0, ty_ent / 0.40) * 0.6 +
          (1 - min(1.0, truu / n_mk / 0.2 if n_mk else 1)) * 0.2 +
          (1 - min(1.0, max(0.0, ty_ac - 0.3) / 0.4)) * 0.2) if n_mk else 0
    diem = round(30 * s1 + 25 * s2 + 15 * s3 + 15 * s4 + 15 * s5)

    loi, canh = [], []
    # dang van-hoa it ten rieng hon (tuc le, do vat) nen nguong thap hon 1 bac
    nguong = 4.5 if nhan_vat else 3.5
    if per150 < nguong:
        loi.append(f"LAN MAN: chi {per150:.1f} chi tiet cu the / 150 am tiet "
                   f"(ten nguoi/dia danh/su kien KHAC nhan vat chinh + con so; "
                   f"dich >= {nguong:g}, ban viet tay Vo Tac Thien dat 10,4). Lay them "
                   f"tinh tiet trong FACTS, bo cau binh luan chung chung")
    if ty_suong > 0.12:
        loi.append(f"LAN MAN: {ty_suong*100:.0f}% loi doc nam trong doan KHONG co "
                   f"mot ten rieng hay con so nao (dich <= 12%). Vi du: "
                   + " | ".join(f'\"{d}\"' for d in doan_hong[:3]))
    if chuoi > max(1, tong_at // 1500):
        loi.append(f"VAN DON: {chuoi} chuoi >= 3 cau lien nhau mo bang cung mot "
                   f"tu (kieu 'Nhin thay... Nhin thay... Nhin thay...'). Vi du: "
                   + " || ".join(cau_lap[:3]))
    if len(dai_suong) > max(2, len(cau_all) // 25):
        canh.append(f"{len(dai_suong)} cau dai >= 22 am tiet ma khong co ten/so "
                    f"(khai quat suong). Vi du: \"{dai_suong[0][:80]}\"")
    if so_doan_dem and ty_bam < 0.75:
        loi.append(f"LAC DE: chi {ty_bam*100:.0f}% doan nhac nhan vat chinh hoac "
                   f"thuc the trong FACTS (dich >= 75%)")
    if n_mk:
        if nhan_vat and ty_ent < 0.40:
            loi.append(f"MARKER: chi {ty_ent*100:.0f}% marker hinh co ent=\"<bai "
                       f"Wikipedia EN>\" (dich >= 40% cho dang nhan vat). Doan "
                       f"noi ve nguoi/dia danh/su kien/hien vat cu the phai co ent")
        if ent_sai:
            loi.append(f"MARKER: {ent_sai} ent khong co trong FACTS (bang thuc the): "
                       + ", ".join(sorted(set(ent_la))[:6]))
        if truu > max(1, n_mk // 20):
            loi.append(f"MARKER: {truu} tu khoa hinh truu tuong/khong chup duoc: "
                       + ", ".join(f'\"{k}\"' for k in kw_truu[:5]))
        if ty_ac > 0.30:
            canh.append(f"{ty_ac*100:.0f}% tu khoa mo bang 'ancient Chinese' — "
                        f"viet thang vat/noi/hanh dong cu the")

    return {
        "so": {"diem_tap_trung": diem,
               "chi_tiet_150": round(per150, 1),
               "doan_suong_pct": round(ty_suong * 100),
               "lap_cau_truc": chuoi,
               "cau_suong_dai": len(dai_suong),
               "doan_bam_pct": round(ty_bam * 100),
               "marker_ent_pct": round(ty_ent * 100),
               "marker_truu_tuong": truu,
               "ancient_chinese_pct": round(ty_ac * 100),
               "nhan_vat_chinh": sorted(chinh)},
        "loi": loi, "canh_bao": canh, "doan_hong": doan_hong,
    }


def check(case_dir, phut, wpm=187.0, sec_per_img=None, tol=0.18, dang=""):
    """`wpm` o day la AM TIET MOI PHUT VIDEO, khong phai toc do doc.

    Do that 13/09/2026 tren ca ba video 20 phut vua dung (Vbee, rate -18%):
    2649 am tiet -> 14,31 phut | 2721 -> 14,72 | 2631 -> 13,74.
    Tuc 185-191 am tiet moi phut VIDEO. Ban truoc de 130 nen dat 20 phut chi
    ra 14 phut, ma cham van bao "du dai" -> khong ai bat duoc loi.
    """
    nhan_vat = la_nhan_vat(dang)
    if sec_per_img is None:
        # Dang nhan vat giu hinh lau hon: do tren kenh BattleCry la ~18s mot lan
        # cat canh cung. Anh tinh nhay 4-5s/lan gay met mat ma van khong "song".
        sec_per_img = (10.0, 20.0) if nhan_vat else (5.0, 10.0)
    path = os.path.join(case_dir, "script", "script.md")
    if not os.path.exists(path):
        return {"ok": False, "loi": [f"thieu {path}"], "so": {}}

    raw = open(path, encoding="utf-8").read()
    vo_text = read_vo(raw)
    words = len(vo_text.split())
    n_img = len(re.findall(r"\[\[(?:stock|wiki|card|quote|broll|clip):", raw))
    n_break = len(re.findall(r"\[\[black\|pause=", raw))
    mins = words / wpm
    dich = phut * wpm

    loi, canh_bao = [], []
    for dong, text, vi in tim_rac(raw):
        loi.append(f"dong {dong} se bi MAY DOC TO LEN ({vi}): \"{text}\" — "
                   f"bo han khoi script.md hoac chuyen sang NOTE.md")
    if words < dich * (1 - tol):
        loi.append(f"script NGAN: {words} am tiet, can >= {int(dich * (1 - tol))} "
                   f"(~{phut} phut video @ {wpm:g} am tiet/phut video)")
    elif words > dich * (1 + tol):
        loi.append(f"script DAI: {words} am tiet, can <= {int(dich * (1 + tol))}")

    if n_img == 0:
        loi.append("khong co marker hinh nao ([[stock:]]/[[card:]])")
    else:
        spi = words / n_img / wpm * 60.0
        if spi < sec_per_img[0]:
            canh_bao.append(f"{spi:.1f}s/anh — hinh doi qua nhanh (dich "
                            f"{sec_per_img[0]:g}-{sec_per_img[1]:g}s)")
        elif spi > sec_per_img[1]:
            loi.append(f"{spi:.1f}s/anh — hinh dung qua lau, them marker hinh "
                       f"(dich {sec_per_img[0]:g}-{sec_per_img[1]:g}s)")

    # loi doc khong duoc chua dau gach dai: prep_vo_text doi thanh dau cham
    for i, line in enumerate(raw.splitlines(), 1):
        s = line.strip()
        if s and not s.startswith(("#", "[[", "---", ">")) and "—" in s:
            canh_bao.append(f"dong {i} co dau '—' trong loi doc — doi thanh dau cham/phay")
            break

    # --- dang nhan vat: bon phep dem bat dung benh cua ban script dau tien ---
    # (6 chuong x 2 phut, 10 nhan vat, 0,9 con so/phut, 55% cau cut)
    n_chuong = so_nguoi = so_so = 0
    if nhan_vat:
        tieu_de = [l.strip().lstrip("#").strip() for l in raw.splitlines()
                   if l.strip().startswith("#")]
        # bo dong tieu de video (dong '#' dau tien) va cac muc HOOK/KET
        n_chuong = len([t for t in tieu_de[1:] if t])
        dich_chuong = max(2, min(8, round(phut / 4.5)))
        if n_chuong > dich_chuong + 2:
            loi.append(f"{n_chuong} chuong cho {phut:g} phut = {phut/max(1,n_chuong):.1f} "
                       f"phut/chuong. Chuong ngan khong kip dung canh nen xem xong "
                       f"khong dong gi. Gop lai con ~{dich_chuong} chuong, moi chuong 4-5 phut")

        # con so that: dem chu so trong LOI DOC (khong tinh trong marker)
        so_so = len(re.findall(r"\d+", vo_text))
        mat_do = so_so / mins if mins else 0
        if mat_do < 3.0:
            loi.append(f"chi {mat_do:.1f} con so that moi phut (dich >= 4). Day la "
                       f"dau hieu CHUA TRA DU TU LIEU — quay lai tra nam, quan so, "
                       f"tuoi, khoang cach; dung viet van hoa my de bu vao")

        # nhan vat co ten: cum 2-3 tu Hoa toan chu cai dau viet hoa
        hoa = re.findall(r"\b(?:[A-ZÀ-Ỹ][a-zà-ỹ]+)(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+){1,2}\b",
                         vo_text)
        dem = {}
        for h in hoa:
            dem[h] = dem.get(h, 0) + 1
        so_nguoi = len([k for k, v in dem.items() if v >= 4])
        if so_nguoi > 6:
            canh_bao.append(f"{so_nguoi} ten rieng duoc nhac >= 4 lan — dich toi da "
                            f"4 nhan vat. Nhieu qua thi nguoi xem khong nho ai la ai")

        # chat vun: ty le cau ngan
        cau = [c.strip() for c in re.split(r"[.!?]+", vo_text) if c.strip()]
        if cau:
            cut = sum(1 for c in cau if len(c.split()) <= 10) / len(cau)
            if cut > 0.50:
                loi.append(f"{cut*100:.0f}% cau ngan duoi 10 am tiet (dich ~39%). "
                           f"Dang chat vun thanh chuoi caption — viet thanh doan "
                           f"lien mach 3-5 cau, xen cau dai 25-40 am tiet")

    ref = os.path.join(case_dir, "references.json")
    if not os.path.exists(ref):
        canh_bao.append("thieu references.json")
    else:
        try:
            data = json.load(open(ref, encoding="utf-8"))
            if not data:
                canh_bao.append("references.json rong")
        except Exception as e:
            loi.append(f"references.json hong: {e}")

    # --- tap trung: chi tiet that, khong van don, bam nhan vat, marker ent ---
    tt = cham_tap_trung(raw, doc_facts(case_dir), dang)
    loi += tt["loi"]
    canh_bao += tt["canh_bao"]

    return {
        "ok": not loi,
        "loi": loi,
        "canh_bao": canh_bao,
        "tap_trung": tt["so"],
        "so": {"am_tiet": words, "phut_video": round(mins, 2), "marker_hinh": n_img,
               "s_moi_anh": round(words / n_img / wpm * 60.0, 1) if n_img else 0,
               "ngat_chuong": n_break,
               **({"chuong": n_chuong, "nhan_vat": so_nguoi,
                   "so_moi_phut": round(so_so / mins, 1) if mins else 0}
                  if nhan_vat else {})},
    }


def dang_tu_queue(case_dir):
    """Lay `dang` cua slug trong queue.yml — de goi tay khoi phai nho --dang."""
    try:
        import yaml
        q = yaml.safe_load(open(os.path.join(KIT, "queue.yml"), encoding="utf-8"))
        slug = os.path.basename(os.path.normpath(case_dir))
        for v in q.get("videos") or []:
            if v.get("slug") == slug:
                return v.get("dang") or (q.get("defaults") or {}).get("dang", "")
    except Exception:
        pass
    f = doc_facts(case_dir)
    return (f or {}).get("dang", "")


def main():
    # Console Windows mac dinh cp1252: in loi co dau tieng Viet la vang
    # UnicodeEncodeError ngay giua bao cao (gap 03/10/2026).
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--phut", type=float, required=True)
    ap.add_argument("--wpm", type=float, default=187.0,
                    help="am tiet moi PHUT VIDEO (mac dinh 187, do thuc)")
    ap.add_argument("--dang", default=None,
                    help="nhan-vat | (trong) = van hoa. Bo trong = doc queue.yml")
    ap.add_argument("--json", action="store_true", help="in ca ket qua JSON")
    a = ap.parse_args()
    case = os.path.abspath(a.case)
    dang = dang_tu_queue(case) if a.dang is None else a.dang
    r = check(case, a.phut, a.wpm, dang=dang)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        tt = r.get("tap_trung", {})
        print(f"== {os.path.basename(case)}  (dang: {dang or 'van-hoa'})")
        print(f"DIEM TAP TRUNG: {tt.get('diem_tap_trung', '?')}/100")
        for k, v in tt.items():
            if k != "diem_tap_trung":
                print(f"  {k:20s} {v}")
        print("  " + json.dumps(r["so"], ensure_ascii=False))
        for e in r["loi"]:
            print("  LOI  " + e)
        for c in r.get("canh_bao", []):
            print("  (cb) " + c)
        print("OK" if r["ok"] else "CHUA DAT")
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
