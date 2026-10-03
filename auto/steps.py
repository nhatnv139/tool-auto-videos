# -*- coding: utf-8 -*-
"""steps.py — cac buoc san xuat mot video, co resume.

Moi buoc ghi trang thai vao auto/state/<slug>.json. Chay lai runner thi buoc
da xong duoc bo qua, chi lam tiep tu cho dang do.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTO = os.path.join(KIT, "auto")
sys.path.insert(0, AUTO)

STATE_DIR = os.path.join(AUTO, "state")
LOG_DIR = os.path.join(AUTO, "logs")
OUTBOX = os.path.join(KIT, "OUTBOX")

# buoc hong nhung khong chan video ra lo
MEM = {"khong_chan": {"sources", "publish", "thumb"}}

# buoc luon chay lai du da 'done' — re, va phai bat duoc file sinh sau (vd
# publish.md viet o buoc sau outbox lan truoc).
LUON_CHAY = {"outbox"}


# ------------------------------------------------------------------ state
def state_path(slug):
    return os.path.join(STATE_DIR, f"{slug}.json")


def load_state(slug):
    p = state_path(slug)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"slug": slug, "status": "pending", "steps": {}}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(st["slug"]), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ chay lenh
class Runner:
    def __init__(self, slug, case, quiet=False):
        self.slug, self.case, self.quiet = slug, case, quiet
        os.makedirs(LOG_DIR, exist_ok=True)
        self.logfile = os.path.join(LOG_DIR, f"{slug}.log")

    def log(self, msg, echo=True):
        line = str(msg)
        with open(self.logfile, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if echo and not self.quiet:
            print(line, flush=True)

    def sh(self, args, timeout=7200, step=""):
        """Goi tool/run.py (hoac lenh khac), do stdout vao log."""
        self.log(f"    $ {' '.join(str(a) for a in args)}", echo=False)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        r = subprocess.run(args, cwd=KIT, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        self.log(out.rstrip(), echo=False)
        if r.returncode != 0:
            tail = "\n".join(out.rstrip().splitlines()[-12:])
            raise RuntimeError(f"{step or args[-1]} rc={r.returncode}\n{tail}")
        return out

    def kit(self, *cmd, timeout=7200, step=""):
        rel = os.path.relpath(self.case, KIT).replace("\\", "/")
        return self.sh([sys.executable, "tool/run.py", "--case", rel, *cmd],
                       timeout=timeout, step=step or cmd[0])


# ------------------------------------------------------------------ cac buoc
def step_scaffold(R, v):
    os.makedirs(os.path.join(R.case, "script"), exist_ok=True)
    os.makedirs(os.path.join(R.case, "assets", "music"), exist_ok=True)
    meta = {k: v[k] for k in ("slug", "de_tai", "goc_nhin", "do_dai", "wpm",
                              "provider", "anh") if k in v}
    meta["tao_luc"] = datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(R.case, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    ref = os.path.join(R.case, "references.json")
    if not os.path.exists(ref):
        open(ref, "w", encoding="utf-8").write("[]\n")


def step_script(R, v):
    if v.get("no_ai"):
        p = os.path.join(R.case, "script", "script.md")
        if not os.path.exists(p):
            raise RuntimeError("--no-ai nhung khong co script/script.md san")
        R.log("    (--no-ai) dung script.md co san")
        return
    import write_script as WS
    # LUU Y: hai con so khac nhau.
    #   wpm (196)                = toc do DOC, truyen cho buoc tts.
    #   am_tiet_phut_video (130) = so am tiet lam day MOT PHUT VIDEO, dung de
    #                              dat do dai script. Do thuc tren ban test.
    res = WS.write(R.case, v["de_tai"], v.get("goc_nhin", ""),
                   float(v["do_dai"]), float(v.get("am_tiet_phut_video", 187)),
                   max_vong=int(v.get("so_vong_viet", 3)), log=R.log,
                   timeout=int(v.get("timeout_script", 2400)),
                   dang=v.get("dang", ""), v=v)
    # v: write_script doc them wiki_vi / wiki_en (ep bai Wikipedia khi de tai
    # viet khong dau), model_script, song_song (so phan viet cung luc, mac dinh
    # 3), timeout_phan (han MOT lan goi, mac dinh 900s). Ban cu viet mot leo ca
    # bai trong mot lan goi nen chet o 2400s/3430s.
    if not res or not res["ok"]:
        raise RuntimeError("script khong dat chuan sau khi viet lai: "
                           + "; ".join(res["loi"] if res else ["khong co ket qua"]))
    R.log(f"    script OK: {res['so']['am_tiet']} am tiet "
          f"(~{res['so']['phut_video']} phut video), "
          f"{res['so']['marker_hinh']} marker hinh, {res['so']['s_moi_anh']}s/anh, "
          f"diem tap trung {res.get('tap_trung', {}).get('diem_tap_trung', '?')}/100, "
          f"viet het {res.get('thoi_gian_s', '?')}s")


def step_duyet(R, v):
    """Chan lai neu queue ghi duyet: tay."""
    if str(v.get("duyet", "auto")).lower().startswith("tay"):
        raise Pause("script viet xong — dang cho nguoi duyet (duyet: tay). "
                    "Duyet xong doi thanh 'duyet: auto' roi chay lai runner.")


def step_config(R, v):
    R.kit("script2config", timeout=300, step="script2config")


def _co_ent(case):
    """config.json co cell nao mang ent= khong."""
    try:
        with open(os.path.join(case, "config.json"), encoding="utf-8") as f:
            return any(c.get("ent") for c in json.load(f).get("cells", []))
    except Exception:
        return False


def step_images(R, v):
    """Nguon hinh cho video. queue.yml: `anh: <che do>`.

      bg     1 anh nen duy nhat (Wikipedia VN) — nhe nhat
      wiki   moi keyword vai anh tu lieu Wikimedia (khong can key)
      photo  anh Unsplash/Pexels/Pixabay -> Ken Burns (can key, anh dep + net)
      stock  video Pexels/Pixabay/Coverr (can key)

    Ghep duoc bang dau phay: `anh: photo,stock` = anh dep + b-roll dong, khong
    dung Wikimedia. Hai bi danh co san: mix = wiki,photo | full = wiki,photo,stock.
    """
    che_do = str(v.get("anh", "wiki")).strip().lower()
    per = str(v.get("anh_per", 3))
    if che_do == "bg":
        # mot anh nen duy nhat cho ca video — nhe nhat, nhanh nhat
        import bg_image
        bg_image.dung_bg(R.case, v.get("anh_bg"), log=R.log)
        return

    BI_DANH = {"mix": "wiki,photo", "full": "wiki,photo,stock"}
    nguon = [x.strip() for x in BI_DANH.get(che_do, che_do).split(",") if x.strip()]
    la = {"wiki", "photo", "stock"}
    if not nguon or set(nguon) - la:
        raise RuntimeError(f"khong biet che do anh: {che_do} "
                           f"(chon trong {sorted(la)}, bg, mix, full — "
                           f"ghep bang dau phay)")
    R.log(f"    nguon hinh: {', '.join(nguon)}")
    # Wikimedia full-text search chi dung cho marker `ent=` (tu lieu that). Cho
    # keyword CANH KHONG KHI no la rac: do 03/10/2026 tren demo Bach Dang,
    # "Vietnam river mist dawn wooden boats" ra thanh pho Da Nang ban dem,
    # "fire smoke on water dusk" ra phao hoa, "museum wooden stakes" ra phong
    # hoc gia Trung Hoa — ma vi no chay TRUOC va lap day dinh muc (kw_demand)
    # nen photo/stock khong tai gi nua. Nen co photo/stock thi wiki chi lam ent.
    if "wiki" in nguon and not ({"photo", "stock"} & set(nguon)):
        R.kit("wiki", "--per", per, timeout=5400, step="wiki")
    elif _co_ent(R.case):
        # Marker ent= la lenh "canh nay phai la tu lieu THAT cua thuc the" — no
        # khong phu thuoc che do anh. Chi tai phan ent, khong full-text search.
        rel = os.path.relpath(R.case, KIT).replace("\\", "/")
        R.sh([sys.executable, "tool/wiki_images.py", rel, "--ent-only"],
             timeout=5400, step="wiki-ent")
    # Dinh muc (kw_demand) dung chung cho moi kho, kho nao chay truoc thi lap
    # day truoc. Ban cu photo chay truoc stock: demo Bach Dang 03/10 ra 29 anh
    # tinh + 3 clip dong — video gan nhu khong co gi chuyen dong. Nay video
    # dong (stock) lay truoc, anh tinh (photo) lap phan con thieu;
    # `anh_uu_tien: anh` trong queue.yml de quay lai thu tu cu.
    thu_tu = ["photo", "stock"] if str(v.get("anh_uu_tien", "video")) == "anh"         else ["stock", "photo"]
    for kho in thu_tu:
        if kho == "photo" and "photo" in nguon:
            R.kit("photo", "--per", str(v.get("anh_photo_per", per)),
                  timeout=5400, step="photo")
        if kho == "stock" and "stock" in nguon:
            R.kit("stock", timeout=5400, step="stock")
    _don_tmp_anh(R)


def _don_tmp_anh(R):
    """Bo anh goc da tai ve (build/tmp/photo|wiki) ngay sau buoc hinh.

    Chung chi la nguyen lieu de dung shot Ken Burns — shot da nam trong kho
    chung assets/stock (bam theo kho|keyword|idx) nen chay lai buoc hinh cung
    khong can chung. Case Can Long 30 phut de lai 691 MB o day den het case.
    """
    tong = 0
    for sub in ("photo", "wiki"):
        d = os.path.join(R.case, "build", "tmp", sub)
        if os.path.isdir(d):
            import don_dep
            tong += don_dep.nang(d)
            shutil.rmtree(d, ignore_errors=True)
    if tong:
        R.log(f"    bo anh goc tam {tong / 1e6:.0f} MB (shot da vao kho chung)")


def step_tts(R, v):
    """Theo spec skill truyen-van-hoa-giong.

    Vbee la mac dinh cua kenh: giong nguoi that, chay o --rate=-18%. Luu y
    `--rate=-18%` PHAI viet lien dau bang, roi argparse hieu '-18%' la mot co khac.
    """
    prov = str(v.get("provider", "vbee"))
    # nhip: he so nhan moi khoang lang. 1.0 = spec kenh, 0.7 = go bot im lang.
    if v.get("nhip") is not None:
        os.environ["TTS_GAP_MUL"] = str(v["nhip"])
        R.log(f"    nhip nghi x{v['nhip']}")
    # kieu dung giong: doan (mac dinh tu 01/10/2026, doc ca doan mot lan goi)
    # | cau (kieu cu, goi tung cau). Nam trong hash cache nen doi la sinh lai.
    if v.get("tts_mode"):
        os.environ["TTS_MODE"] = str(v["tts_mode"])
        R.log(f"    kieu giong: {v['tts_mode']}")
    args = ["tts", "--provider", prov, "--wpm", str(v.get("wpm", 196))]
    if v.get("voice"):
        args += ["--edge-voice", str(v["voice"])]
    args += [f"--rate={v.get('rate', '-25%')}"]
    R.kit(*args, timeout=7200, step="tts")

    # Keo nhip ve dung dich — AP DUNG THAT, khong con --dry-run.
    #
    # Ban cu chi do roi ghi log, voi ly do "skill noi thuong da dat". Dieu do
    # dung khi giong la hn_male_manhdung_full_24k-st: do 26/09 tren mau 35 am
    # tiet, no doc 241 am tiet/phut o rate -18%, nen voi nhip 0.15 ra 232 —
    # sat dich 223. Doi sang hn_male_phuthang_stor_24k-stl thi khong con dung:
    # giong nay BAO HOA o 275 am tiet/phut (0.70 va 0.60 deu ra 275), khong co
    # gia tri speed_rate nao dua no ve 231 duoc. De nguyen --dry-run thi runner
    # in ra "nhip lech 19%" roi van dung video nhanh hon spec 19%.
    #
    # slow_voice tu bo qua khi he so >= 0.995, nen voi giong da dat dich day la
    # lenh khong lam gi. Tat bang `keo_cham: false` trong queue.yml.
    rel = os.path.relpath(R.case, KIT).replace("\\", "/")
    cmd = [sys.executable, "tool/slow_voice.py", rel,
           "--wpm", str(v.get("wpm", 196))]
    if v.get("keo_cham") is False:
        cmd.append("--dry-run")
    try:
        out = R.sh(cmd, timeout=1800, step="slow_voice")
        for line in out.strip().splitlines()[-3:]:
            R.log(f"    nhip: {line.strip()}")
    except Exception as e:
        R.log(f"    (bo qua) khong do duoc nhip: {e}")


def step_render(R, v):
    R.kit("render", timeout=10800, step="render")


def step_music(R, v):
    bed = os.path.join(R.case, "assets", "music", "bed.wav")
    if os.path.exists(bed):
        return
    out = R.kit("plan", timeout=600, step="plan")
    m = re.search(r"tong:\s*([\d.]+)s", out)
    dur = float(m.group(1)) + 10 if m else float(v.get("do_dai", 10)) * 60 + 30
    if m:
        that = float(m.group(1)) / 60.0
        dich = float(v.get("do_dai", 0) or 0)
        R.log(f"    do dai THAT: {that:.1f} phut (dich {dich:g} phut)")
        if dich and that > dich * 1.35:
            R.log(f"    (canh bao) dai hon dich {that / dich:.2f} lan — khoang lang "
                  f"({'//'}, [[black|pause=]]) dang an nhieu thoi luong")
    # Nen am thanh — queue.yml `nhac:`:
    #   ambience (MAC DINH) = gio + drone tram tu ambience_bed.py; `nhac_lop:`
    #                         chon lop (vd "gio-trong,song-nuoc" cho canh song)
    #   sine                = 3 song sine cu (music.py) — chi de test pipeline
    #   <duong dan file>    = nhac that cua ban (mp3/wav), lap cho du dai
    # Video Can Long 03/10 ra voi sine: nghe la tieng u u cua may, khong phai nhac.
    nhac = str(v.get("nhac", "ambience")).strip()
    if nhac == "sine":
        R.kit("music", "--dur", f"{dur:.0f}", timeout=900, step="music")
    elif nhac == "ambience":
        cmd = [sys.executable, "tool/ambience_bed.py",
               os.path.relpath(R.case, KIT).replace("\\", "/"),
               "--dur", f"{dur:.0f}", "--drone", str(v.get("nhac_drone", "Dm"))]
        if v.get("nhac_lop"):
            cmd += ["--layers", str(v["nhac_lop"])]
        R.log(f"    nen: ambience ({v.get('nhac_lop') or 'gio'})")
        R.sh(cmd, timeout=900, step="ambience")
    else:
        src = nhac if os.path.isabs(nhac) else os.path.join(KIT, nhac)
        if not os.path.exists(src):
            raise RuntimeError(f"nhac: khong thay file {src}")
        R.log(f"    nen: nhac that {os.path.basename(src)}")
        R.sh(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", src,
              "-t", f"{dur:.0f}", "-af", "afade=t=in:d=3,afade=t=out:st="
              f"{max(0, dur - 4):.0f}:d=4", "-ar", "48000", "-ac", "2",
              "-c:a", "pcm_s16le", bed], timeout=900, step="music-file")


def step_assemble(R, v):
    # Dich loudness cua kenh di thang vao assemble: chuan MOT LAN o stage4.
    # Ban cu assemble chuan ve -14 + AAC 256k roi chuan_tieng lai loudnorm ve
    # -19,7 va encode AAC lan hai (video 20 phut mat 100s).
    out = R.kit("assemble", f"--lufs={v.get('lufs', -19.7)}",
                f"--lra={v.get('lra', 3)}", f"--tp={v.get('tp', -2.5)}",
                timeout=14400, step="assemble")
    final = os.path.join(R.case, "build", "final", "video-1.mp4")
    if not os.path.exists(final):
        raise RuntimeError("assemble xong nhung khong thay build/final/video-1.mp4")
    R.log(f"    final: {os.path.getsize(final) / 1e6:.0f} MB")
    # Bo build/trim NGAY, dung doi buoc cleanup o cuoi: trim la ban day du do
    # dai cua ca video (CRF 16) nen no nang xap xi video cuoi. Giu lai thi tu
    # day den het case tren dia luc nao cung co 3 ban cua cung mot video
    # (shots + trim + final) — do la luc dia vo. Xoa duoc vi khong buoc nao sau
    # assemble doc trim, va chay lai assemble se dung shots dung lai trim.
    if not v.get("giu_build"):
        trim = os.path.join(R.case, "build", "trim")
        if os.path.isdir(trim):
            import don_dep
            n = don_dep.nang(trim)
            shutil.rmtree(trim, ignore_errors=True)
            R.log(f"    bo build/trim ({n / 1e9:.2f} GB) — dung lai duoc tu shots")


def step_chuan_tieng(R, v):
    """Chuan loudness theo skill truyen-van-hoa-giong: -19,7 LUFS, LRA 3, TP -2,5.

    Do la so do tu kenh Viet Su Ky Su. Khong lam buoc nay thi video nghe nho hon
    han kenh doi thu tren cung mot nac am luong.
    """
    final = os.path.join(R.case, "build", "final", "video-1.mp4")
    if not os.path.exists(final):
        raise RuntimeError("chua co video de chuan tieng")
    tmp = final.replace(".mp4", "-norm.mp4")
    I = v.get("lufs", -19.7)
    LRA = v.get("lra", 3)
    TP = v.get("tp", -2.5)
    # assemble moi da chuan dung dich va ghi marker -> khong encode AAC lan hai.
    # Chi final cu (assemble truoc 01/10/2026, hoac dich trong queue doi sau
    # khi assemble) moi phai loudnorm lai o day.
    marker = os.path.splitext(final)[0] + ".loudness.json"
    da_chuan = False
    try:
        mk = json.load(open(marker, encoding="utf-8"))
        da_chuan = (abs(float(mk["I"]) - float(I)) < 0.05
                    and abs(float(mk["LRA"]) - float(LRA)) < 0.05
                    and abs(float(mk["TP"]) - float(TP)) < 0.05
                    and os.path.getmtime(marker) >= os.path.getmtime(final) - 5)
    except Exception:
        da_chuan = False
    if da_chuan:
        R.log("    audio da chuan ngay o assemble — chi do lai")
    else:
        R.sh(["ffmpeg", "-y", "-v", "error", "-i", final,
              "-af", f"loudnorm=I={I}:LRA={LRA}:TP={TP}",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", tmp],
             timeout=3600, step="loudnorm")
        os.replace(tmp, final)
    # doc lai de chac. -vn: chi giai ma audio — ban cu giai ma ca video 1080p
    # chi de do am luong (phan lon trong 100s cua buoc nay).
    out = R.sh(["ffmpeg", "-v", "info", "-i", final, "-vn", "-af", "ebur128=peak=true",
                "-f", "null", "-"], timeout=3600, step="ebur128")
    # ebur128 in mot dong MOI KHUNG (t: ... I: -70.0 LUFS) roi moi den phan
    # "Summary" o cuoi. Lay match DAU se doc trung khung dau tien — luc do chua
    # co du lieu nen luon la -70 LUFS / LRA 0, trong nhu video bi cam tieng.
    Is = re.findall(r"I:\s*(-?[\d.]+) LUFS", out)
    LRAs = re.findall(r"LRA:\s*(-?[\d.]+) LU", out)
    if Is and LRAs:
        R.log(f"    loudness sau chuan: I={Is[-1]} LUFS, LRA={LRAs[-1]} LU "
              f"(dich I={I}, LRA<=4)")


def step_sources(R, v):
    R.kit("sources", timeout=600, step="sources")


def step_publish(R, v):
    """Goi claude -p viet publish.md (tieu de + mo ta + moc chuong)."""
    if v.get("no_ai"):
        return
    import write_script as WS
    prompt = (
        f"Doc {R.case}\\script\\script.md va {R.case}\\references.json.\n"
        f"Ghi file {R.case}\\publish.md gom:\n"
        "## Tieu de (3 phuong an, khuyen nghi 1 cai, moi cai <= 70 ky tu)\n"
        "## Mo ta (4-6 doan, co muc NOI DUNG voi moc thoi gian va muc NGUON)\n"
        "## Tag (15 tag, phan cach bang dau phay)\n"
        "Tieng Viet co dau. Khong bia so lieu ngoai script. "
        "Viet xong tra loi dung mot tu: DONE.")
    rc, _ = WS.run_claude(prompt, R.case, timeout=900,
                          log=lambda s: R.log("    | " + s[-800:], echo=False))
    if rc != 0:
        raise RuntimeError(f"publish claude rc={rc}")


def step_outbox(R, v):
    day = datetime.now().strftime("%Y-%m-%d")
    dest = os.path.join(OUTBOX, f"{day}-{R.slug}")
    os.makedirs(dest, exist_ok=True)
    pairs = [
        (os.path.join(R.case, "build", "final", "video-1.mp4"), "video.mp4"),
        (os.path.join(R.case, "publish.md"), "publish.md"),
        (os.path.join(R.case, "build", "sources.md"), "sources.md"),
        (os.path.join(R.case, "script", "script.md"), "script.md"),
        (os.path.join(R.case, "build", "thumb.jpg"), "thumb.jpg"),
    ]
    got = []
    for src, name in pairs:
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dest, name))
            got.append(name)
    R.log(f"    OUTBOX: {dest}  ({', '.join(got)})")
    return dest


def step_cleanup(R, v):
    """Xong roi thi chi giu dau vao + video cuoi. Luat o auto/don_dep.py."""
    if v.get("giu_build"):
        return
    import don_dep
    freed, ghi_chu = don_dep.don_mot_case(R.case, that=True, im=True)
    if ghi_chu:
        R.log(f"    khong don ({ghi_chu})")
    elif freed:
        R.log(f"    don {freed / 1e9:.2f} GB file may tu sinh")


STEPS = [
    ("scaffold", step_scaffold),
    ("script", step_script),
    ("duyet", step_duyet),
    ("config", step_config),
    ("images", step_images),
    ("tts", step_tts),
    ("render", step_render),
    ("music", step_music),
    ("assemble", step_assemble),
    ("chuan_tieng", step_chuan_tieng),
    ("sources", step_sources),
    ("publish", step_publish),
    ("outbox", step_outbox),
    ("cleanup", step_cleanup),
]
STEP_NAMES = [n for n, _ in STEPS]


class Pause(Exception):
    """Dung co chu dich (cho nguoi duyet) — khong phai loi."""


class HetDia(Exception):
    """Dia khong con du cho de lam mot case — dung ca hang doi."""


# Dinh dia cua mot case, do 01/10/2026 tren case test 5 phut roi nhan 6 cho
# video 30 phut:
#   truoc: shots CRF14 2,0 + lo 2,0 + trim/video.mp4 2,0 + 16 file giong doc
#          PCM dai bang ca video 5,5 + audio_raw 0,5 + tmp anh 0,7 + _seg 0,3
#          -> ~13 GB + final 2 GB (vi vay Can Long chet het dia voi 12 GB trong)
#   sau:   shots CRF18 0,5 + lo 1,5 + audio FLAC 0,25 + final 1,5 + ban copy
#          OUTBOX 1,5 -> ~5,3 GB (tmp anh, _seg, video.mp4 khong con)
# Chua 6 GB cho mot case 30 phut + du phong kho stock phinh them khi tai anh.
CAN_TRONG_GB = 7


def kiem_dia(R):
    """Du cho lam mot case khong? Thieu thi don rac truoc, van thieu thi dung."""
    import don_dep
    trong = don_dep.byte_trong(KIT)
    if trong is None:
        return
    if trong >= CAN_TRONG_GB * 1e9:
        R.log(f"    dia con {trong / 1e9:.1f} GB")
        return
    R.log(f"    dia chi con {trong / 1e9:.1f} GB (< {CAN_TRONG_GB} GB) — don rac truoc")
    freed = don_rac_cu(R, tru_slug=R.slug)
    trong = don_dep.byte_trong(KIT) or 0
    R.log(f"    don duoc {freed / 1e9:.2f} GB -> con {trong / 1e9:.1f} GB")
    if trong < CAN_TRONG_GB * 1e9:
        raise HetDia(
            f"con {trong / 1e9:.1f} GB, can it nhat {CAN_TRONG_GB} GB. "
            f"Kho dung chung assets/stock thuong la thu phinh nhat — go bot bang:\n"
            f"       python tool/run.py --case . stock --prune --prune-yes")


def don_case_hong(R, v):
    """Case chet giua chung: bo phan may tu sinh, giu script/ + config de chay
    lai van resume duoc. Khong lam viec nay thi moi lan hong bo lai vai GB —
    dem 15/09/2026 mot case chet o assemble de lai 3,9 GB, gop lai lam day o D
    va keo theo ca loat case sau chet lay vi het cho."""
    if v.get("giu_build"):
        return
    import don_dep
    try:
        # GIU build/voice. Do la thu dat nhat trong ca case: mot video 20 phut
        # ton ~12 phut goi Vbee, va dung luc API down thi khong sinh lai duoc
        # bang bat cu gia nao. Tren dia no chi vai chuc MB, trong khi cai lam
        # day o D la shots/trim co GB. Dem 25/09/2026 mot cu 504 cua Vbee da
        # keo theo 723 giay TTS bi xoa sach vi cho nay don ca luot.
        n, _ = don_dep.don_mot_case(R.case, that=True, im=True, ke_ca_hong=True,
                                    giu=("build/voice",))
    except Exception as e:          # don dep hong thi cung khong duoc nuot loi goc
        R.log(f"    (khong don duoc: {type(e).__name__}: {e})")
        return
    if n:
        R.log(f"    don {n / 1e9:.2f} GB file may tu sinh (giu script + config "
              f"de chay lai)")


def don_rac_cu(R, tru_slug=None):
    """Don build cua MOI case khac dang nam trong videos/ — ca case da xong lan
    case chay hong. Tra ve so byte da giai phong."""
    import don_dep
    goc = os.path.join(KIT, "videos")
    if not os.path.isdir(goc):
        return 0
    tong = 0
    for ten in sorted(os.listdir(goc)):
        if ten == tru_slug:
            continue
        case = os.path.join(goc, ten)
        if not os.path.isdir(case):
            continue
        n, _ = don_dep.don_mot_case(case, that=True, im=True, ke_ca_hong=True)
        if n:
            R.log(f"      don {ten}: {n / 1e9:.2f} GB")
            tong += n
    return tong


# ------------------------------------------------------------------ chay 1 case
def run_case(v, force_from=None, only_steps=None, quiet=False):
    slug = v["slug"]
    case = os.path.join(KIT, "videos", slug)
    os.makedirs(case, exist_ok=True)
    R = Runner(slug, case, quiet=quiet)
    st = load_state(slug)
    st["case"] = os.path.relpath(case, KIT)
    st["status"] = "running"
    save_state(st)

    R.log("")
    R.log(f"=== {slug} | {v.get('de_tai', '')} "
          f"| {v.get('do_dai')} phut | {datetime.now():%H:%M:%S} ===")

    started = time.time()
    kiem_dia(R)          # nem HetDia -> runner dung ca hang doi
    force_idx = STEP_NAMES.index(force_from) if force_from else None
    for i, (name, fn) in enumerate(STEPS):
        if only_steps and name not in only_steps:
            continue
        forced = (force_idx is not None and i >= force_idx) or name in LUON_CHAY
        if st["steps"].get(name, {}).get("status") == "done" and not forced:
            R.log(f"  - {name:<9} bo qua (da xong)")
            continue
        t0 = time.time()
        R.log(f"  > {name} ...")
        try:
            fn(R, v)
        except Pause as e:
            st["steps"][name] = {"status": "pause", "msg": str(e)}
            st["status"] = "pause"
            save_state(st)
            R.log(f"  || DUNG: {e}")
            return "pause"
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            st["steps"][name] = {"status": "fail", "msg": msg[:2000],
                                 "luc": datetime.now().isoformat(timespec="seconds")}
            if name in MEM["khong_chan"]:
                R.log(f"  ! {name} hong nhung khong chan: {msg.splitlines()[0]}")
                save_state(st)
                continue
            st["status"] = "fail"
            st["error"] = msg[:2000]
            save_state(st)
            R.log(f"  XX {name} HONG sau {time.time() - t0:.0f}s")
            R.log(f"     {msg}")
            don_case_hong(R, v)
            return "fail"
        st["steps"][name] = {"status": "done", "giay": round(time.time() - t0, 1),
                             "luc": datetime.now().isoformat(timespec="seconds")}
        save_state(st)
        R.log(f"  v {name} xong ({time.time() - t0:.0f}s)")

    st["status"] = "done"
    st["tong_giay"] = round(time.time() - started, 1)
    save_state(st)
    R.log(f"=== XONG {slug} sau {(time.time() - started) / 60:.1f} phut ===")
    return "done"
