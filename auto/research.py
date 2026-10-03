# -*- coding: utf-8 -*-
"""research.py — buoc RESEARCH truoc khi viet: gom du kien that + lap dan y.

Vi sao co buoc nay: 4 script tu sinh cu (can-long, tan-thuy-hoang,
chu-nguyen-chuong...) viet mot leo 20-30 phut tu tri nho cua model, khong co
tu lieu trong tay -> do duoc 3,3-5,1 chi tiet cu the / 150 am tiet va 41-54% loi
doc nam trong doan khong co mot ten rieng hay con so nao. Ban viet tay Vo Tac
Thien (co tra cuu) dat 10,4 chi tiet va 6% doan suong. Thieu tu lieu thi model
lap cho day bang van hoa my — nen phai dua tu lieu vao TRUOC.

Quy trinh:
  1. xac dinh bai Wikipedia VI + EN cua chu de (queue: wiki_vi / wiki_en de
     ep; khong co thi tim, khong ra thi hoi claude mot cau ngan).
  2. tai ban text VI + EN + vai bai lien quan nhat (API cong khai, khong key)
     -> script/research/*.txt
  3. mot lan `claude -p` KHONG tool: doc tu lieu -> JSON gom bang thuc the
     (ten VI + ten bai Wikipedia EN), danh sach su kien co nguon, va DAN Y
     tung chuong (moi chuong mot cau hoi + cac F-id cua no).
  4. python kiem ten bai EN bang API (theo redirect, chuan hoa), roi ghi:
     script/facts.json (may doc), FACTS.md, NOTE.md, bg.txt, references.json.

Chay tay:  python auto\\research.py videos\\<slug> --de-tai "..." --phut 3 --dang nhan-vat
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

UA = "ai-frontier-kit/1.0 (research; contact: local)"


# ---------------------------------------------------------------- wikipedia
def wiki_api(lang, **params):
    params.update(format="json", formatversion="2")
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    loi = None
    for lan in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:          # mang chap chon: thu lai 3 lan
            loi = e
            time.sleep(1.5 * (lan + 1))
    raise RuntimeError(f"wikipedia {lang} loi: {loi}")


def wiki_url(lang, title):
    return f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(
        title.replace(" ", "_"))


def chuan_hoa_tieu_de(lang, titles):
    """{ten goc: ten chuan} — theo redirect/normalize; bai khong ton tai -> None."""
    out = {}
    titles = [t for t in dict.fromkeys(t.strip() for t in titles if t and t.strip())]
    for i in range(0, len(titles), 50):
        lo = titles[i:i + 50]
        d = wiki_api(lang, action="query", titles="|".join(lo), redirects=1)
        q = d.get("query", {})
        doi = {}
        for k in ("normalized", "redirects"):
            for x in q.get(k, []):
                doi[x["from"]] = x["to"]
        ton_tai = {p["title"] for p in q.get("pages", []) if not p.get("missing")
                   and not p.get("invalid")}
        for t in lo:
            c = t
            for _ in range(3):
                c = doi.get(c, c)
            out[t] = c if c in ton_tai else None
    return out


def lay_bai(lang, title, max_chars=40000):
    d = wiki_api(lang, action="query", titles=title, redirects=1,
                 prop="extracts|langlinks|links", explaintext=1, lllang="en",
                 pllimit="max", plnamespace=0)
    p = d["query"]["pages"][0]
    if p.get("missing"):
        return None
    txt = p.get("extract", "")
    # bo phan duoi vo ich (tham khao, lien ket ngoai) — ton token ma khong co
    # tinh tiet nao
    for cat in ("\n== See also ==", "\n== References ==", "\n== Notes ==",
                "\n== Xem thêm ==", "\n== Tham khảo ==", "\n== Chú thích ==",
                "\n== Liên kết ngoài =="):
        k = txt.find(cat)
        if k > 2000:
            txt = txt[:k]
    return {"title": p["title"], "text": txt[:max_chars],
            "en": (p.get("langlinks") or [{}])[0].get("title"),
            "links": [l["title"] for l in p.get("links", [])]}


def tim_vi(query):
    d = wiki_api("vi", action="query", list="search", srsearch=query, srlimit=3)
    return [x["title"] for x in d.get("query", {}).get("search", [])]


# ---------------------------------------------------------------- claude
def _json_tu_text(out):
    """Lay object JSON dau tien -> cuoi cung trong output cua claude."""
    s = out.find("{")
    e = out.rfind("}")
    if s < 0 or e <= s:
        raise ValueError("khong thay JSON trong output claude")
    raw = out[s:e + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # dau phay thua truoc } ] — loi hay gap nhat khi model viet JSON dai
        return json.loads(re.sub(r",\s*([}\]])", r"\1", raw))


def xac_dinh_chu_de(de_tai, goc_nhin, v, log=print):
    """-> (ten bai VI | None, ten bai EN | None)."""
    from write_script import goi_claude
    vi = (v or {}).get("wiki_vi")
    en = (v or {}).get("wiki_en")
    if vi or en:
        return vi, en
    # de tai co dau: tim thang phan truoc dau '-' (vd "Hoa Than - tham quan...")
    ten = re.split(r"\s+[-–—:]\s+", de_tai)[0].strip()
    from check_script import bo_dau
    if ten != bo_dau(ten):
        for t in tim_vi(ten):
            if bo_dau(t).lower() in bo_dau(de_tai).lower():
                return t, None
    # queue.yml viet khong dau ("Cuoc doi Vo Tac Thien...") -> search Wikipedia
    # tra 0 ket qua (do 01/10/2026). Hoi claude mot cau, khong tool, ~10s.
    prompt = ("De tai video lich su: \"" + de_tai + "\"\nGoc nhin: \"" +
              (goc_nhin or "") + "\"\n"
              "Chu de chinh (nhan vat / su kien / phong tuc) la gi? Tra loi DUNG "
              "mot dong JSON, khong giai thich:\n"
              "{\"vi\": \"<ten bai Wikipedia tieng Viet chinh xac, CO DAU>\", "
              "\"en\": \"<ten bai English Wikipedia chinh xac>\"}")
    rc, out = goi_claude(prompt, timeout=180, tools=False, log=None)
    try:
        j = _json_tu_text(out)
        return j.get("vi"), j.get("en")
    except Exception as e:
        log(f"    (research) khong doc duoc ten chu de tu claude: {e}")
        return None, None


def tai_tu_lieu(case, vi, en, phut, log=print):
    """Tai text Wikipedia vao script/research/. Tra ve dict tom tat."""
    rdir = os.path.join(case, "script", "research")
    os.makedirs(rdir, exist_ok=True)
    bai = {}
    if vi:
        b = lay_bai("vi", vi)
        if b:
            bai["vi"] = b
            en = en or b.get("en")
    if en:
        b = lay_bai("en", en, max_chars=60000)
        if b:
            bai["en"] = b
    if not bai:
        raise RuntimeError(f"khong tim thay bai Wikipedia cho chu de (vi={vi!r}, "
                           f"en={en!r}) — ghi wiki_vi / wiki_en vao queue.yml")
    # bai lien quan: link cua bai EN duoc nhac nhieu lan nhat trong chinh bai
    # do (Heshen -> Qianlong Emperor, Jiaqing Emperor...). Video dai can nhieu
    # tinh tiet hon mot bai: 3 phut = 0 bai phu, 30 phut = 6 bai phu.
    phu = []
    so_phu = 0 if phut < 5 else min(6, int(phut // 5))
    if "en" in bai and so_phu:
        txt = bai["en"]["text"]
        dem = []
        for l in bai["en"]["links"]:
            if len(l) < 4 or ":" in l:
                continue
            n = txt.count(l)
            if n >= 2:
                dem.append((n, l))
        for _n, l in sorted(dem, reverse=True)[:so_phu]:
            b = lay_bai("en", l, max_chars=12000)
            if b:
                phu.append(b)
    for k, b in bai.items():
        open(os.path.join(rdir, f"{k}.txt"), "w", encoding="utf-8").write(
            f"# {b['title']}\n{wiki_url(k, b['title'])}\n\n{b['text']}")
    for i, b in enumerate(phu, 1):
        open(os.path.join(rdir, f"en-phu-{i}.txt"), "w", encoding="utf-8").write(
            f"# {b['title']}\n{wiki_url('en', b['title'])}\n\n{b['text']}")
    links = bai.get("en", {}).get("links", [])
    open(os.path.join(rdir, "links_en.txt"), "w", encoding="utf-8").write(
        "\n".join(links))
    log(f"    (research) tu lieu: " + ", ".join(
        f"{k}:{b['title']} ({len(b['text'])} ky tu)" for k, b in bai.items())
        + (f" + {len(phu)} bai phu" if phu else ""))
    return {"bai": bai, "phu": phu, "links": links}


# ---------------------------------------------------------------- dan y
def so_chuong(phut, dang):
    from check_script import la_nhan_vat
    if phut < 2:
        return 0                      # video ngan: chi mot phan duy nhat
    if la_nhan_vat(dang):
        # skill su-nhan-vat: chuong 4-5 phut; 20 phut = 4 chuong
        return max(2, min(8, round(phut / 4.5)))
    return max(2, min(8, round(phut / 5)))


def ke_hoach_do_dai(phut, wpm, dang):
    """[(loai, am_tiet)] — python chia do dai, KHONG de model tu chia.

    Model tu chia thi hook phinh ra 2-3 phut (can-long: hook 480 am tiet).
    """
    from check_script import la_nhan_vat
    tong = int(phut * wpm)
    n = so_chuong(phut, dang)
    if n == 0:
        return [("ngan", tong)]
    # hook: nhan-vat 45-50s, van-hoa 40s (spec hai skill)
    hook = int(wpm * (0.8 if la_nhan_vat(dang) else 0.68))
    hook = min(hook, tong // 3)
    moi = (tong - hook) // n
    return [("hook", hook)] + [("chuong", moi)] * n


PROMPT_FACTS = """Ban la nguoi nghien cuu tu lieu cho kenh YouTube ke su tieng Viet.
Lam viec im lang. CHI dung tu lieu ben duoi (Wikipedia VI + EN). KHONG bia.

DE TAI: {de_tai}
GOC NHIN XUONG SONG: {goc_nhin}
DANG: {dang_mo_ta}
VIDEO: {phut:g} phut, {tong} am tiet loi doc, chia thanh {so_phan} phan:
{ke_hoach}

NHIEM VU: tra ve DUNG MOT object JSON (khong markdown, khong loi dan) dang:
{{
  "nhan_vat_chinh": {{"vi": "<ten goi trong loi doc, co dau>", "en": "<ten bai English Wikipedia>",
                      "goi_khac": ["<ten khac/nien hieu/ten huy, co dau>"]}},
  "the": [ {{"vi": "<ten tieng Viet co dau dung trong loi doc>", "en": "<ten bai English Wikipedia CHINH XAC>",
             "loai": "nguoi|dia_danh|su_kien|hien_vat|to_chuc"}} ],
  "facts": [ {{"id": "F01", "nam": "<nam hoac khoang nam, '' neu khong ro>",
               "noi_dung": "<1-2 cau tieng Viet co dau: AI lam GI, O DAU, bao nhieu — co ten, so>",
               "the": ["<ten bai EN cua cac thuc the lien quan>"],
               "nguon": "<URL wikipedia cua bai chua du kien nay>"}} ],
  "dan_y": {{
    "tieu_de": "<tieu de video, co dau, IN HOA>",
    "cau_hoi_trung_tam": "<cau hoi ca video tra loi>",
    "phan": [ {{"loai": "hook|chuong|ngan", "ten": "<ten chuong: nhan danh gia, 3-7 chu, '' cho hook>",
                "cau_hoi": "<MOT cau hoi chuong nay tra loi>",
                "facts": ["F01", "F02"], "nhan_vat": ["<ten bai EN>"],
                "y_chinh": "<1-2 cau: chuong nay ke gi, ket o dau>"}} ]
  }}
}}

LUAT:
1. facts: it nhat {min_facts} muc, xep theo thoi gian. Moi muc la mot TINH TIET
   CU THE (su viec + ten + nam/con so), khong phai nhan dinh chung ("ong la
   nguoi tai gioi" la CAM). Uu tien chi tiet la, co con so, co hanh dong,
   co cau noi duoc ghi lai. Bam GOC NHIN: phai co du tinh tiet de chung minh no.
2. the: moi nguoi/dia danh/su kien/hien vat co ten xuat hien trong facts. Truong
   "en" PHAI la ten bai co that tren en.wikipedia.org (vd "Qianlong Emperor",
   "Heshen", "Macartney Embassy", "Siku Quanshu", "Forbidden City"). Neu ten
   co trong danh sach LINK BAI EN ben duoi thi chep dung chinh ta do. Toi da
   25 thuc the. Khong chac ten bai thi bo, dung doan.
3. dan_y.phan: DUNG {so_phan} phan, dung thu tu loai: {thu_tu}.
   - Moi phan nhan 3-8 facts RIENG (mot F-id chi thuoc MOT phan, tru hook duoc
     muon lai 1-2 F-id gay soc nhat). Phan dai hon nhan nhieu facts hon:
     khoang 1 fact cho moi 60 am tiet.
   - Chuong di theo thoi gian; moi chuong co cau_hoi rieng, khong trung nhau.
   - nhan_vat cua moi phan: toi da 4 ten bai EN, lay tu "the".
{luat_dang}
TU LIEU:
{tu_lieu}

LINK BAI EN (ten bai hop le de dung cho "en"):
{links}
"""

LUAT_NHANVAT = """   - Dang NHAN VAT (skill su-nhan-vat): chuong ten la NHAN DANH GIA ("Van vo
     toan tai", "Canh bac o Nhiet Ha"), khong trung tinh ("Giai doan cai tri").
     Chuong cuoi la chuong PHAN TICH "Tai sao nen co su nay": facts cua no la
     cac nguyen nhan (khach quan / chu quan). Toan video toi da 4 nhan vat
     phu duoc nhac nhieu.
   - Hook: facts gay soc nhat + dieu nguoi xem hay nghi sai ve nhan vat.
"""
LUAT_VANHOA = """   - Dang VAN HOA (skill truyen-van-hoa): giai phau co che, moi chuong MOT CAU
     HOI (khong phai mot moc thoi gian). Chuong cuoi la KET: tra loi thang cau
     hoi trung tam.
   - Hook: vat quen thuoc + nghich ly that.
"""


def lap_facts(case, de_tai, goc_nhin, phut, wpm, dang, tu_lieu, log=print,
              timeout=1500, model=None):
    from check_script import la_nhan_vat
    from write_script import goi_claude
    kh = ke_hoach_do_dai(phut, wpm, dang)
    tong = sum(a for _l, a in kh)
    parts = []
    for b in [tu_lieu["bai"].get("vi"), tu_lieu["bai"].get("en")] + tu_lieu["phu"]:
        if b:
            lang = "vi" if b is tu_lieu["bai"].get("vi") else "en"
            parts.append(f"===== {wiki_url(lang, b['title'])} =====\n{b['text']}")
    prompt = PROMPT_FACTS.format(
        de_tai=de_tai, goc_nhin=goc_nhin or "(tu chon)",
        dang_mo_ta=("nhan vat — ke doi mot con nguoi" if la_nhan_vat(dang)
                    else "van hoa — giai phau mot phong tuc/hien tuong"),
        phut=phut, tong=tong, so_phan=len(kh),
        ke_hoach="\n".join(f"   {i}. {l} ~{a} am tiet" for i, (l, a) in
                           enumerate(kh, 1)),
        thu_tu=", ".join(l for l, _a in kh),
        min_facts=max(10, int(tong / 60)),
        luat_dang=LUAT_NHANVAT if la_nhan_vat(dang) else LUAT_VANHOA,
        tu_lieu="\n\n".join(parts),
        links=", ".join(tu_lieu["links"][:500]))
    log(f"    (research) claude lap FACTS + dan y ({len(prompt)} ky tu prompt) ...")
    t0 = time.time()
    rc, out = goi_claude(prompt, timeout=timeout, tools=False, model=model)
    log(f"    (research) xong sau {time.time() - t0:.0f}s, rc={rc}")
    try:
        f = _json_tu_text(out)
    except Exception as e:
        open(os.path.join(case, "script", "research", "facts_raw.txt"), "w",
             encoding="utf-8").write(out)
        raise RuntimeError(f"claude khong tra JSON facts hop le: {e}")

    # --- ep so phan dung ke hoach, gan am tiet do python chia ---
    phan = (f.get("dan_y") or {}).get("phan") or []
    if len(phan) != len(kh):
        log(f"    (research) dan y co {len(phan)} phan, ke hoach {len(kh)} — can lai")
        while len(phan) < len(kh):
            phan.append({"loai": "chuong", "ten": "", "cau_hoi": "", "facts": [],
                         "nhan_vat": [], "y_chinh": ""})
        if len(phan) > len(kh):
            du = phan[len(kh):]
            phan = phan[:len(kh)]
            for p in du:
                phan[-1]["facts"] = list(phan[-1].get("facts", [])) + list(p.get("facts", []))
    for p, (loai, at) in zip(phan, kh):
        p["loai"] = loai
        p["am_tiet"] = at
    f.setdefault("dan_y", {})["phan"] = phan
    return f


def kiem_ten_bai(f, log=print):
    """Kiem truong 'en' cua moi thuc the bang API — ent sai = anh sai."""
    ten = [e.get("en", "") for e in f.get("the", [])]
    nv = f.get("nhan_vat_chinh") or {}
    ten.append(nv.get("en", ""))
    chuan = chuan_hoa_tieu_de("en", ten)
    sai = 0
    for e in f.get("the", []):
        c = chuan.get((e.get("en") or "").strip())
        e["hop_le"] = bool(c)
        if c:
            e["en"] = c
        else:
            sai += 1
    if nv.get("en") and chuan.get(nv["en"].strip()):
        nv["en"] = chuan[nv["en"].strip()]
    # dong bo ten trong facts/dan y theo ten chuan
    doi = {k: v for k, v in chuan.items() if v}
    for x in f.get("facts", []):
        x["the"] = [doi.get(t, t) for t in x.get("the", [])]
    for p in f.get("dan_y", {}).get("phan", []):
        p["nhan_vat"] = [doi.get(t, t) for t in p.get("nhan_vat", [])]
    log(f"    (research) {len(f.get('the', []))} thuc the, {sai} ten bai EN khong "
        f"ton tai (bi loai khoi ent)")
    return f


# ---------------------------------------------------------------- ghi file
def ghi_file(case, f, de_tai):
    sdir = os.path.join(case, "script")
    json.dump(f, open(os.path.join(sdir, "facts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    nv = f.get("nhan_vat_chinh") or {}
    L = [f"# FACTS — {de_tai}", "",
         f"Nhan vat / chu de chinh: **{nv.get('vi', '')}** "
         f"(ent=\"{nv.get('en', '')}\") — {wiki_url('en', nv.get('en', ''))}", ""]
    if nv.get("goi_khac"):
        L.append("Ten khac: " + ", ".join(nv["goi_khac"]))
        L.append("")
    L += ["## Bang thuc the (ent dung trong marker hinh)", "",
          "| Ten VI | ent (Wikipedia EN) | loai | hop le |", "|---|---|---|---|"]
    for e in f.get("the", []):
        L.append(f"| {e.get('vi', '')} | {e.get('en', '')} | {e.get('loai', '')} | "
                 f"{'x' if e.get('hop_le') else 'KHONG'} |")
    L += ["", "## Dong thoi gian / tinh tiet", "",
          "| id | nam | tinh tiet | thuc the | nguon |", "|---|---|---|---|---|"]
    for x in f.get("facts", []):
        L.append(f"| {x.get('id')} | {x.get('nam', '')} | "
                 f"{x.get('noi_dung', '').replace('|', '/')} | "
                 f"{', '.join(x.get('the', []))} | {x.get('nguon', '')} |")
    open(os.path.join(sdir, "FACTS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    dy = f.get("dan_y", {})
    N = [f"# NOTE — {dy.get('tieu_de', de_tai)}", "",
         f"Cau hoi trung tam: {dy.get('cau_hoi_trung_tam', '')}", "",
         "## Dan y (sinh tu auto/research.py — moi phan chi dung facts cua no)", ""]
    for i, p in enumerate(dy.get("phan", []), 1):
        N += [f"### {i}. [{p['loai']}] {p.get('ten', '')} (~{p['am_tiet']} am tiet)",
              f"- Cau hoi: {p.get('cau_hoi', '')}",
              f"- Y chinh: {p.get('y_chinh', '')}",
              f"- Facts: {', '.join(p.get('facts', []))}",
              f"- Nhan vat: {', '.join(p.get('nhan_vat', []))}", ""]
    N += ["## Con so phai giu dung (kem nguon)", ""]
    for x in f.get("facts", []):
        if re.search(r"\d", x.get("noi_dung", "")):
            N.append(f"- {x['id']}: {x['noi_dung']} — {x.get('nguon', '')}")
    open(os.path.join(sdir, "NOTE.md"), "w", encoding="utf-8").write("\n".join(N) + "\n")

    # bg.txt: bai VI cua chu de chinh co anh dai dien dung nhat
    open(os.path.join(sdir, "bg.txt"), "w", encoding="utf-8").write(
        f"vi: {f.get('_wiki_vi') or nv.get('vi', '')}\n"
        f"en: {nv.get('en', '')} painting\n")

    # references.json: moi bai wiki da dung + nguon cua facts
    refs, thay = [], set()
    for lang, t in (("vi", f.get("_wiki_vi")), ("en", nv.get("en"))):
        if t:
            u = wiki_url(lang, t)
            thay.add(u)
            refs.append({"title": f"{t} — Wikipedia ({lang})", "url": u,
                         "note": "bai tong quan chu de; nguon chinh cua FACTS.md"})
    for x in f.get("facts", []):
        u = (x.get("nguon") or "").strip()
        if u.startswith("http") and u not in thay:
            thay.add(u)
            ten = urllib.parse.unquote(u.rsplit("/", 1)[-1]).replace("_", " ")
            refs.append({"title": f"{ten} — Wikipedia", "url": u,
                         "note": f"du kien {x['id']}"})
    for e in f.get("the", []):
        if e.get("hop_le"):
            u = wiki_url("en", e["en"])
            if u not in thay:
                thay.add(u)
                refs.append({"title": f"{e['en']} — Wikipedia", "url": u,
                             "note": f"thuc the '{e.get('vi', '')}' (ent marker hinh)"})
    json.dump(refs, open(os.path.join(os.path.dirname(sdir), "references.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=2)


def khoa(de_tai, goc_nhin, phut, wpm, dang):
    s = json.dumps([de_tai, goc_nhin, float(phut), float(wpm), str(dang)])
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]


def chuan_bi(case, de_tai, goc_nhin, phut, wpm, dang="", v=None, log=print,
             timeout=1500):
    """Tra ve dict facts (co dan_y). Dung lai facts.json neu cung khoa — chay
    lai sau khi chet giua chung khong phai research lai (~3-5 phut)."""
    v = v or {}
    os.makedirs(os.path.join(case, "script"), exist_ok=True)
    k = khoa(de_tai, goc_nhin, phut, wpm, dang)
    p = os.path.join(case, "script", "facts.json")
    if os.path.exists(p):
        try:
            f = json.load(open(p, encoding="utf-8"))
            if f.get("_khoa") == k and f.get("dan_y", {}).get("phan"):
                log(f"    (research) dung lai facts.json co san ({len(f.get('facts', []))} "
                    f"facts) — xoa file nay neu muon research lai")
                return f
        except Exception:
            pass
    t0 = time.time()
    vi, en = xac_dinh_chu_de(de_tai, goc_nhin, v, log)
    if vi:
        c = chuan_hoa_tieu_de("vi", [vi]).get(vi)
        vi = c
    if en:
        en = chuan_hoa_tieu_de("en", [en]).get(en)
    log(f"    (research) chu de: vi={vi!r} en={en!r}")
    tl = tai_tu_lieu(case, vi, en, phut, log)
    f = lap_facts(case, de_tai, goc_nhin, phut, wpm, dang, tl, log,
                  timeout=timeout, model=v.get("model_script"))
    f = kiem_ten_bai(f, log)
    f["_khoa"] = k
    f["_wiki_vi"] = tl["bai"].get("vi", {}).get("title")
    f["dang"] = dang
    ghi_file(case, f, de_tai)
    log(f"    (research) xong {time.time() - t0:.0f}s: {len(f.get('facts', []))} facts, "
        f"{len(f['dan_y']['phan'])} phan -> script/FACTS.md")
    return f


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--de-tai", required=True, dest="de_tai")
    ap.add_argument("--goc-nhin", default="", dest="goc_nhin")
    ap.add_argument("--phut", type=float, required=True)
    ap.add_argument("--wpm", type=float, default=187.0)
    ap.add_argument("--dang", default="")
    a = ap.parse_args()
    chuan_bi(os.path.abspath(a.case), a.de_tai, a.goc_nhin, a.phut, a.wpm, a.dang)


if __name__ == "__main__":
    main()
