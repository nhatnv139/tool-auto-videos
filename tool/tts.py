"""
tts.py — Sinh VO cho tung cell co 'vo' trong config.

    python tool/run.py --case videos/<topic> tts --provider edge          # free test
    python tool/run.py --case videos/<topic> tts --provider elevenlabs    # can ELEVENLABS_API_KEY

Output: build/voice/cell-<id>.mp3 + build/voice/manifest.json
edge-tts: Microsoft neural, mien phi, khong can key.
ElevenLabs: can ELEVENLABS_API_KEY, giong tu nhien hon.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys

API = "https://api.elevenlabs.io"
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"  # Rachel
DEFAULT_MODEL = "eleven_multilingual_v2"

# Giong edge mac dinh. Christopher thuoc lop "News, Novel" — giong doc ban tin
# the he cu, cadence deu, gan nhu khong co ngu dieu hoi thoai. Andrew thuoc lop
# "Conversation" moi, am va tu nhien hon han cho video binh luan.
EDGE_VOICE = "en-US-AndrewMultilingualNeural"

TICKS = 10_000_000      # edge-tts tra offset/duration theo 100ns

# Cat khoang lang edge-tts tu chen o dau (~0.15s) va cuoi (~0.35-0.90s) moi cau.
TRIM_AF = ("silenceremove=start_periods=1:start_duration=0:"
           "start_threshold=-45dB:detection=peak,areverse,"
           "silenceremove=start_periods=1:start_duration=0:"
           "start_threshold=-45dB:detection=peak,areverse")

# Khoang lang CHU DONG sau moi cau, theo dau ket cau. edge-tts phan ung rat yeu
# voi dau cau (do thuc te: chenh lech chi ~0.3s giua co va khong co dau), nen
# nhip phai do minh chen chu khong the trong cho TTS tu ngat.
#
# Bang cu (". " = 0.32s) do duoc 12% im lang / median pause 0.31s — dich cua
# style ke chuyen la 24% va 0.5-0.6s. Nghe ra thanh mot dai lien khong cho ai
# kip ngam. Bang duoi la muc nen, con nhan them theo VAI TRO cau (ROLE_PROSODY).
GAP_BY_PUNCT = {"?": 0.55, "!": 0.48, ".": 0.50, ":": 0.45, ";": 0.42, ",": 0.26}
GAP_DEFAULT = 0.40
GAP_CLAUSE = 0.24       # nghi giua hai ve cua mot cau dai (tach o dau phay)
GAP_CELL_END = 0.55     # nghi cuoi cell — ranh gioi canh, phai nghe thay

# Nghi THEM truoc cau chot / cau don. Do lam kich tinh nam o khoang lang TRUOC
# don chu khong phai sau: nguoi ke ngung lai, roi moi ha cau. Bang cu chi co
# nghi SAU (ROLE_PROSODY gap_mul) nen don roi xuong khong co da.
#
# Ba so nay cong THEM vao tong im lang nen phai kiem lai nhip: do tren doan mau
# 10 cau, bo (0.22 / 0.028 / 0.24) cho 26% im lang va 195 am tiet/phut — sat
# chuan kenh (24% / 196). Day len 0.30 thi thanh 27% va tut con 194.
GAP_PRE_ROLE = {"punch": 0.22, "verdict": 0.19, "question": 0.10}

# Cau cang dai, tai cang can thoi gian tieu hoa. Cong them theo so tu vuot 12.
GAP_PER_WORD = 0.028
GAP_LEN_CAP = 0.24

# Gap co dinh tuyet doi la mot dang metronome khac: tai bat duoc chu ky. Nhan
# nhe theo chu ky le (7 phan tu) de nhip tho khong tron ven lap lai.
GAP_JITTER = [1.00, 1.09, 0.93, 1.05, 0.96, 1.11, 0.91]

# Tang so nay moi khi doi cach tinh prosody: no di vao hash cache cua cell nen
# doi nghia la lan chay sau sinh lai giong, khong an nham ban cu.
# 4 = nhip chuan doi thu: ha bien do ROLE_PROSODY, chan cong don rate, khoa tong
#     im lang ve 24% theo do dai giong THAT (xem khoa_im_lang).
# 5 = TTS_MODE=doan: doc ca DOAN (tu ky tu // nay toi // kia) trong mot lan goi,
#     bo nhay rate/pitch theo vai tro, gian khoang lang NOI TAI cua engine thay
#     vi chen lang giua cac cau goi rieng (xem doan_render_cell).
PROSODY_VERSION = 5

# Cach dung giong. "doan" (mac dinh tu 01/10/2026) = mot lan goi TTS cho moi
# manh giua hai ky tu ngat viet tay; "cau" = kieu cu, goi tung cau/ve roi ghep.
# Do 01/10 tren cung doan mau 3 cell Can Long (xem OUTBOX/test-giong-2026-10-01):
# kieu "cau" co 11-13 cho noi / 3 cell, moi cau reset ngu dieu tu dau, lang
# giua cau bi khoa chung mot he so -> nghe roi rac kieu may.
def tts_mode():
    m = os.environ.get("TTS_MODE", "doan").strip().lower()
    return m if m in ("doan", "cau") else "doan"

# ---------------------------------------------------------- ky tu ngat nghi viet tay
# Vbee KHONG co duong nao de dieu khien khoang lang tu ben trong: do that
# 2026-09-12 tren hn_male_manhdung_full_24k-st —
#   input_type / text_type / emotion / style / pitch / volume / silence_ms /
#   break_time  -> 400 "not allowed"
#   <break time="1500ms"/>  -> audio dai them 3.56s (doc to len ten the, khong
#                              phai lang); boc trong <speak> con te hon (+6.1s)
#   speed_rate  -> BAO HOA ngoai [0.7, 1.2]: 0.5/0.6/0.7 deu ra 148-151 am
#                  tiet/phut, 1.2/1.5 deu ra 197.
# Nen moi khoang lang phai do ta chen o hau ky. Bang duoi la cac ky tu NGUOI
# VIET dat thang trong truong "vo"; chung bi BOC sach truoc khi goi TTS va
# truoc khi ve phu de, nen may khong bao gio doc chung.
#
#   //     lang them 0,8s   (het mot y, chua het doan)
#   ///    lang them 1,5s   (chuyen y — cho nguoi nghe kip ngam)
#   ////   lang them 2,4s   (chuyen chuong)
#   |      ngat hoi 0,16s   (tach cum giua cau ma khong can dau phay)
#   ^      hit mot hoi nghe thay ngay truoc cau do
#   *      ca cau doc cham hon 8% va nghi sau dai gap 1,4 lan (cau can nhan)
MARK_LANG = {"////": 2.40, "///": 1.50, "//": 0.80}
MARK_MICRO = 0.16
NHAN_DR = -8.0
NHAN_GAP_MUL = 1.40

# ---------------------------------------------------------------- tieng hit hoi
# Khac biet lon nhat giua nguoi ke va may doc khong nam o giong ma o CHO KHONG
# CO GIONG: nguoi ke hit hoi truoc cau dai, va tieng hit do bao cho tai biet
# "sap co mot y moi". Vbee tra ve audio da cat sach hoi, nen phai chen lai.
# Hoi duoc dung tu nhieu hong loc (khong phai mau thu am) de khong phu thuoc
# file ngoai va de doi mau sac theo giong.
BREATH_AFTER_GAP = 0.75   # chi hit sau khoang lang tu ngan nay tro len
BREATH_MIN_WORDS = 16     # ... hoac khi cau sap doc dai tu ngan nay tro len
BREATH_DUR = 0.34
BREATH_DB = -26.0         # so voi giong da chuan hoa; du nghe, khong at loi

_MARK_RE = re.compile(r'/{2,4}|\|')
_MARK_ANY_RE = re.compile(r'/{2,4}|[|^*]')


def strip_marks(t):
    """Boc het ky tu ngat nghi khoi van ban — dung cho phu de va cho log."""
    return re.sub(r"\s{2,}", " ", _MARK_ANY_RE.sub(" ", t or "")).strip()


def split_marks(text):
    """Cat van ban tai cac diem ngat nghi viet tay.

    Tra ve list dict {text, extra_gap, breath, nhan}. `extra_gap` la khoang lang
    dat SAU manh do; `breath` = manh nay mo dau bang mot hoi hit vao; `nhan` =
    ca manh doc cham hon.
    """
    out = []
    pos = 0
    for m in _MARK_RE.finditer(text):
        chunk = text[pos:m.start()]
        gap = MARK_MICRO if m.group() == "|" else MARK_LANG[m.group()]
        out.append({"text": chunk, "extra_gap": gap})
        pos = m.end()
    out.append({"text": text[pos:], "extra_gap": 0.0})

    res = []
    for p in out:
        t = p["text"]
        breath = False
        # '^' dung o dau manh (sau khi da bo khoang trang thua)
        if t.lstrip().startswith("^"):
            breath = True
            t = t.lstrip()[1:]
        nhan = "*" in t
        t = t.replace("^", " ").replace("*", " ")
        t = re.sub(r"\s{2,}", " ", t).strip()
        if not t:
            # Manh rong (vi du dong chi co '///') -> don khoang lang vao manh truoc.
            if res:
                res[-1]["extra_gap"] = round(res[-1]["extra_gap"] + p["extra_gap"], 3)
            continue
        res.append({"text": t, "extra_gap": p["extra_gap"],
                    "breath": breath, "nhan": nhan})
    return res or [{"text": strip_marks(text), "extra_gap": 0.0,
                    "breath": False, "nhan": False}]

# Bien thien toc do nhe giua cac cau — pha nhip metronome. Co dinh (khong random)
# de build lai cho ket qua giong nhau.
RATE_JITTER = [0.0, 3.0, -2.0, 2.0, -3.0, 1.0]

# Chu HOA tieng Viet — [A-Z] cua Python KHONG bao gom D/A/O/U co dau, nen ban cu
# khong tach duoc cau bat dau bang "Day", "Do", "De", "Ong"... Ca doan bi doc lien
# thanh mot utterance, mat het khoang nghi do GAP_BY_PUNCT chen.
_VN_UPPER = ("A-Z"
             "À-ÖØ-Þ"        # À-Ö, Ø-Þ (Latin-1 hoa)
             "ĂĐĨŨƠƯ"   # Ă Đ Ĩ Ũ Ơ Ư
             "ẠẢẤẦẨẪẬẮẰẲ"
             "ẴẶẸẺẼẾỀỂỄỆ"
             "ỈỊỌỎỐỒỔỖỘỚ"
             "ỜỞỠỢỤỦỨỪỬỮ"
             "ỰỲỴỶỸ")
SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=["“(]?[' + _VN_UPPER + r'0-9])')


def prep_vo_text(t):
    """Chuan hoa text truoc khi doc: dash/ellipsis -> ranh gioi cau that.

    Doi dash thanh cau moi la cach duy nhat lay duoc khoang nghi co kiem soat,
    vi edge-tts gan nhu bo qua chinh cac dau do.
    """
    t = t.replace("—", ". ").replace("–", ". ")
    t = re.sub(r"\s+-\s+", ". ", t)
    t = t.replace("…", ". ").replace("...", ". ")
    t = (t.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"'))
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text):
    """Tach theo CAU (khong tach o dau phay: moi utterance edge-tts co ngu dieu
    ket cau rieng, tach nho qua se nghe roi rac)."""
    return [s.strip() for s in SENT_SPLIT.split(" ".join(text.split())) if s.strip()]


def gap_after(sent):
    return GAP_BY_PUNCT.get(sent.rstrip()[-1:], GAP_DEFAULT)


def sentence_rate(i, n, base_pct, sent):
    """Cau mo dau tu ton, cau cuoi ha canh, cau hoi keo ra — cong jitter nhe."""
    adj = base_pct + RATE_JITTER[i % len(RATE_JITTER)]
    if n > 1 and i == 0:
        adj -= 3.0
    if n > 1 and i == n - 1:
        adj -= 5.0
    if sent.rstrip().endswith("?"):
        adj -= 4.0
    return f"{int(round(max(-40.0, min(60.0, adj)))):+d}%"


# ------------------------------------------------------------- ngu dieu theo noi dung
# Giong khong deu deu la nho tung cau DANG LAM GI trong doan, khong phai nho
# jitter ngau nhien. Moi vai tro co bo ba: (lech toc do %, cao do Hz, he so nghi).
#   - cau chot va cau don danh: tram xuong, cham lai, nghi that lau sau do —
#     day la "diem trong tam" nguoi nghe bam vao de hieu doan vua roi.
#   - cau hoi: nhinh cao o cuoi, nghi lau cho khan gia tu tra loi trong dau.
#   - cau co con so: cham lai de tai kip bat, khong can tram.
#
# Do lai 2026-09-12 tren kenh doi thu (spec skill truyen-van-hoa-giong):
# 195-200 am tiet/phut, ~20 pause/phut, median pause 0,5-0,6s, im lang ~24%.
# Bo he so cu (punch 1.9, verdict 1.8) cho median gap 0,95s — gap doi chuan,
# va cong don rate (-5% nen, -6% vai tro, -3% cau cuoi, -8% dau '*') keo giong
# xuong -19%. Bang duoi giu nguyen HINH DANG ngu dieu, chi ha bien do: chenh
# lech giua cac vai tro van nghe ro, nhung khong con lam lech nhip tong.
ROLE_PROSODY = {
    "question": (-3.0,  +8.0, 1.20),
    "verdict":  (-4.0, -12.0, 1.30),
    "punch":    (-3.0,  -6.0, 1.25),
    "fact":     (-2.0,  -4.0, 1.10),
    "opener":   (-2.0,  -8.0, 1.10),
    "narrate":  (0.0,    0.0, 1.00),
}

# Cau chot thuong mo bang mot trong may tu noi ket nay, hoac chua mot cum
# khang dinh tuyet doi. Do la cho phai ha giong xuong chu khong keo tuot qua.
_VERDICT_OPEN = re.compile(
    r'^(vì|bởi|bởi vì|cho nên|vậy nên|thế nên|nghĩa là|tức là|đó là|đây là|'
    r'rốt cuộc|cuối cùng|kết cục|và đó|nhưng đó)\b', re.IGNORECASE)
_VERDICT_CUE = re.compile(
    r'(chính là|chưa bao giờ|không bao giờ|tuyệt đối không|duy nhất|'
    r'không một ai|chẳng ai)', re.IGNORECASE)
_HAS_NUM = re.compile(r'\d')


def sentence_role(sent, i, n, is_cell_start):
    """Doan vai tro cua cau trong doan de chon ngu dieu."""
    s = sent.strip()
    if s.endswith("?"):
        return "question"
    if _VERDICT_OPEN.match(s) or _VERDICT_CUE.search(s):
        return "verdict"
    if len(s.split()) <= 8 and s.endswith((".", "!")):
        return "punch"
    if _HAS_NUM.search(s):
        return "fact"
    if is_cell_start and i == 0 and n > 1:
        return "opener"
    return "narrate"


def ha_nhan(roles):
    """Cai gi cung la cau chot thi khong con cau chot nao.

    `sentence_role` goi moi cau <= 8 chu ket bang dau cham la 'punch' — van ke
    chuyen toan cau ngan nen ca doan deu thanh cau chot, moi cau lai duoc nghi
    dai va doc cham, cong don ra nhip le the. Giu lai cau manh CUOI cung cua
    doan (cho tra bai), ha cac cau con lai ve 'narrate' khi ty le vuot 40%.
    """
    manh = [k for k, r in enumerate(roles) if r in ("punch", "verdict")]
    if len(roles) >= 2 and len(manh) > max(1, int(len(roles) * 0.4)):
        for k in manh[:-1]:
            roles[k] = "narrate"
    return roles


def split_clauses(sent, min_words=5, min_sent_words=12):
    """Tach cau DAI thanh cac ve o dau phay.

    Cau 20+ tu doc lien mot hoi la ly do chinh khien nguoi nghe duoi khong kip:
    edge-tts khong tu nghi giua cac ve. Nhung tach vun qua thi moi ve thanh mot
    utterance rieng, ngu dieu roi rac — nen chi tach khi cau du dai VA moi ve
    con it nhat `min_words` tu.
    """
    if "," not in sent or len(sent.split()) < min_sent_words:
        return [sent]
    parts = [p for p in re.split(r',\s+', sent) if p.strip()]
    out, buf = [], ""
    for p in parts:
        buf = f"{buf}, {p}" if buf else p
        if len(buf.split()) >= min_words:
            out.append(buf)
            buf = ""
    if buf:
        if out:
            out[-1] = f"{out[-1]}, {buf}"
        else:
            out = [buf]
    return out if len(out) > 1 else [sent]


# Cao do goc (F0) uoc luong cua giong nam Vbee. Dung de doi "lech bao nhieu Hz"
# cua ROLE_PROSODY sang ty le cho rubberband — Vbee khong co tham so cao do nen
# phan len xuong giong phai lam o hau ky.
VBEE_F0 = 120.0


def pitch_ratio(pitch_str, f0=VBEE_F0):
    """'-12Hz' -> 0.90. Tra None neu khong can dich."""
    try:
        hz = float(re.sub(r"[^\d.+-]", "", pitch_str) or 0.0)
    except ValueError:
        return None
    if abs(hz) < 0.5:
        return None
    return max(0.7, min(1.4, (f0 + hz) / f0))


# Chuan nhip cua kenh doi thu (spec skill truyen-van-hoa-giong, do 2026-09-12).
# Doi bang bien moi truong khi muon thu nhip khac — ca hai nam trong hash cache.
IM_LANG_DICH = max(0.05, min(0.45, float(os.environ.get("TTS_IM_LANG", "0.24"))))


def _gap_mul():
    """He so nhan cho moi khoang lang, doc tu TTS_GAP_MUL. Chan trong [0.4, 2.0]."""
    try:
        v = float(os.environ.get("TTS_GAP_MUL", "1") or 1)
    except ValueError:
        return 1.0
    return max(0.4, min(2.0, v))


def plan_units(text, base_pct=0.0, base_pitch_hz=0.0, is_cell_start=True,
               cell_end_gap=True, breath=None):
    """Chia text thanh don vi doc, moi don vi mang toc do / cao do / nghi rieng.

    Tra ve list dict {text, rate, pitch, gap, role, breath}. Day la cho duy nhat
    quyet dinh nhip; edge_render_cell va vbee_render_cell chi thi hanh.

    `breath=False` tat toan bo tieng hit hoi (ke ca dau '^' viet tay); de None
    thi theo bien moi truong TTS_BREATH (mac dinh bat).
    """
    if breath is None:
        breath = os.environ.get("TTS_BREATH", "1") != "0"
    pieces = split_marks(text)
    # Dem tong so cau trong CA cell truoc: vai tro cau ("cau dau", "cau cuoi
    # doan") phai tinh theo vi tri trong cell, khong phai trong tung manh —
    # neu khong thi moi dau '//' lai de ra mot "cau cuoi doan" gia.
    per_piece = [split_sentences(p["text"]) or [p["text"]] for p in pieces]
    n = sum(len(s) for s in per_piece)

    # Vai tro phai chot cho CA cell truoc khi dung unit: con phai biet trong doan
    # co bao nhieu cau chot moi quyet dinh duoc cau nao that su la cau chot.
    roles_all = ha_nhan([sentence_role(s, k, n, is_cell_start)
                         for k, s in enumerate(sum(per_piece, []))])

    units = []
    i = -1
    for p, sents in zip(pieces, per_piece):
        piece_start = len(units)
        for sent in sents:
            i += 1
            role = roles_all[i]
            d_rate, d_pitch, gap_mul = ROLE_PROSODY[role]
            if n >= 3 and i == n - 1:
                d_rate -= 3.0          # cau cuoi doan ha canh
            if p["nhan"]:
                d_rate += NHAN_DR
                gap_mul *= NHAN_GAP_MUL
            # Chan cong don: vai tro + cau cuoi + dau '*' de chong nhau thanh
            # -19%, giong bo xuong ~165 am tiet/phut trong khi chuan kenh la
            # 195-200. Nhan giong van nghe ro o muc -6%.
            d_rate = max(-6.0, min(2.0, d_rate))
            clauses = split_clauses(sent)
            n_words = len(sent.split())
            for j, cl in enumerate(clauses):
                last = j == len(clauses) - 1
                # Ve chua ket thuc: giu dau phay de TTS treo giong lung chung thay
                # vi ha xuong nhu het cau.
                txt = cl if last else cl.rstrip(" ,") + ","
                rate = base_pct + d_rate + RATE_JITTER[(i + j) % len(RATE_JITTER)]
                # Ve dau nhinh cao, ve cuoi ha — cau co duong cong thay vi mot muc.
                pitch = base_pitch_hz + d_pitch + (0.0 if last else 3.0)
                if not last:
                    gap = GAP_CLAUSE
                else:
                    gap = GAP_BY_PUNCT.get(sent.rstrip()[-1:], GAP_DEFAULT) * gap_mul
                    # Cau dai can them thoi gian cho nguoi nghe tieu hoa.
                    gap += min(GAP_LEN_CAP,
                               max(0, n_words - 12) * GAP_PER_WORD)
                    if i == n - 1:
                        gap = (max(gap, GAP_CELL_END * gap_mul)
                               if cell_end_gap else 0.0)
                units.append({
                    "text": txt, "role": role, "gap": round(gap, 3),
                    "breath": False,
                    "rate": f"{int(round(max(-40.0, min(60.0, rate)))):+d}%",
                    "pitch": f"{int(round(max(-40.0, min(40.0, pitch)))):+d}Hz",
                })
        # Lang viet tay ('//') roi vao ve CUOI cua manh vua xong.
        if p["extra_gap"] and units:
            units[-1]["gap"] = round(units[-1]["gap"] + p["extra_gap"], 3)
        if p["breath"] and len(units) > piece_start:
            units[piece_start]["breath"] = True

    # --- nghi TRUOC don: don vao gap cua ve dung ngay truoc ---
    for k in range(1, len(units)):
        if units[k]["role"] != units[k - 1]["role"]:
            pre = GAP_PRE_ROLE.get(units[k]["role"], 0.0)
            if pre:
                units[k - 1]["gap"] = round(units[k - 1]["gap"] + pre, 3)

    # --- hit hoi tu dong: sau moi khoang lang dai, va truoc cau that dai ---
    if breath:
        for k, u in enumerate(units):
            if u["breath"]:
                continue
            prev_gap = units[k - 1]["gap"] if k else (GAP_CELL_END if is_cell_start else 0.0)
            long_sent = len(u["text"].split()) >= BREATH_MIN_WORDS
            if prev_gap >= BREATH_AFTER_GAP and (long_sent or prev_gap >= 0.95):
                u["breath"] = True
    else:
        for u in units:
            u["breath"] = False

    # --- pha chu ky: nhan nhe tung gap theo mot chuoi le ---
    for k, u in enumerate(units):
        if u["gap"] > 0:
            u["gap"] = round(u["gap"] * GAP_JITTER[k % len(GAP_JITTER)], 3)

    return units


def breath_wav(tmp_dir, dur=BREATH_DUR, db=BREATH_DB):
    """Dung mot tieng hit hoi bang nhieu hong loc — khong can file mau ngoai.

    Hoi nguoi that la nhieu bang rong bi thanh quan loc con ~400-2400Hz, len
    nhanh roi tat dan. anoisesrc mau 'pink' co pho gan voi hoi tho nhat; hai
    tang fade tao dung duong len-xuong do. File duoc dung mot lan roi dung lai
    cho ca cell.
    """
    p = os.path.join(tmp_dir, f"_breath_{int(dur * 1000)}_{int(abs(db))}.wav")
    if os.path.exists(p):
        return p
    up = dur * 0.42
    af = (f"highpass=f=380,lowpass=f=2400,"
          f"afade=t=in:st=0:d={up:.3f}:curve=qsin,"
          f"afade=t=out:st={up:.3f}:d={dur - up:.3f}:curve=exp,"
          f"volume={db}dB")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t",
                    f"{dur:.3f}", "-i", "anoisesrc=c=pink:r=48000:a=0.9",
                    "-af", af, "-ac", "1", "-c:a", "pcm_s16le", p], check=True)
    return p


def khoa_im_lang(units, durs):
    """Keo tong khoang lang ve dung ty le chuan cua kenh (~24% thoi luong).

    Phai lam o day chu khong o `plan_units`: chi den luc nay moi biet giong doc
    THAT dai bao nhieu. Uoc theo so chu thi hong — do 2026-09-12 tren Vbee
    hn_male_manhdung: van ban 23 am tiet ra 5,3s tieng noi, tuc ~260 am tiet/phut
    luc dang phat am, khong phai 196. Con 196 la nhip TONG (da tinh ca ngat nghi):
    260 x (1 - 0,24) = 198. Uoc nham thanh 196 thi cap gap qua tay, video 121 wpm.

    Giu nguyen HINH DANG nhip — cho nghi lau van lau hon cho khac, ca cum chi
    duoc keo/gian cung mot he so.
    """
    lang = sum(u["gap"] for u in units)
    noi = sum(durs)
    if lang <= 0 or noi <= 0:
        return units
    # TTS_GAP_MUL noi vao DICH chu khong nhan roi de vong khoa xoa mat: 0.7 =
    # "chi 70% luong im lang chuan", 1.2 = ke thong tha hon chuan.
    can = noi * (IM_LANG_DICH / (1.0 - IM_LANG_DICH)) * _gap_mul()
    he_so = max(0.35, min(2.0, can / lang))
    for u in units:
        if u["gap"] > 0:
            u["gap"] = round(u["gap"] * he_so, 3)
    return units


def plan_track(units, wavs, durs, tmp_dir):
    """Xep thanh chuoi phat: [('a', file) | ('s', giay)].

    Tieng hit hoi duoc KHOET RA TU khoang lang co san (khong cong them), nen
    tong do dai — va do moc thoi gian tung tu — khong doi. Rieng hoi dat truoc
    cau dau tien thi phai cong them, ham tra ve so giay do o `lead`.
    """
    khoa_im_lang(units, durs)

    items, lead = [], 0.0
    if units and units[0].get("breath"):
        b = breath_wav(tmp_dir)
        lead = BREATH_DUR + 0.06
        items += [("a", b), ("s", 0.06)]
    for k, (u, wav) in enumerate(zip(units, wavs)):
        items.append(("a", wav))
        gap = u["gap"]
        nxt = units[k + 1] if k + 1 < len(units) else None
        if nxt is not None and nxt.get("breath") and gap >= BREATH_DUR + 0.18:
            # Hoi nam o CUOI khoang lang: nguoi ke im, roi hit, roi noi ngay.
            items.append(("s", round(gap - BREATH_DUR - 0.06, 3)))
            items.append(("a", breath_wav(tmp_dir)))
            items.append(("s", 0.06))
        elif gap > 0:
            items.append(("s", round(gap, 3)))
    return items, lead


def concat_track(items, tmp_dir, out_path, lufs=-16.0):
    """Ghep chuoi phat thanh mot file, chuan hoa loudness."""
    ins, fc, n = [], [], 0
    for kind, val in items:
        if kind == "a":
            ins += ["-i", val]
        else:
            if val <= 0:
                continue
            ins += ["-f", "lavfi", "-t", f"{val:.3f}", "-i",
                    "anullsrc=r=48000:cl=mono"]
        fc.append(f"[{n}:a]aresample=48000[x{n}]")
        n += 1
    fc.append("".join(f"[x{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1[cat]")
    joined = os.path.join(tmp_dir, "joined.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins,
                    "-filter_complex", ";".join(fc), "-map", "[cat]",
                    "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", joined],
                   check=True)
    _loudnorm_2pass(joined, out_path, lufs=lufs)


def _loudnorm_2pass(src, dst, lufs=-16.0, tp=-1.5, lra=11.0):
    """Chuan hoa loudness EBU R128. 2 pass + linear=true: chi dich gain, khong
    nen dong — giu nguyen nhip to-nho cua giong doc."""
    af = f"loudnorm=I={lufs}:TP={tp}:LRA={lra}"
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", src,
                        "-af", af + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = p.stderr or ""
    i = txt.rfind("{")
    if i >= 0:
        try:
            m = json.loads(txt[i:txt.rfind("}") + 1])
            # linear=true KHONG duoc dam bao: do 01/10/2026 ca 6/6 cell Vbee
            # (I -21, TP -0.5..-2.4) deu roi ve "normalization_type: dynamic"
            # vi +5dB day dinh qua TP -1.5 -> loudnorm thanh bo nen dong, LRA
            # con 2, cell ra -17.2 chu khong -16. Nen mac dinh: tang DUNG mot
            # gain co dinh (tru di I do duoc) roi alimiter chi cham dinh — giu
            # to-nho tu nhien va cac cell cung muc. TTS_LOUDNORM=loudnorm = cu.
            if os.environ.get("TTS_LOUDNORM", "gain") != "loudnorm":
                g = lufs - float(m["input_i"])
                lim = 10 ** (tp / 20.0)
                af = (f"volume={g:.2f}dB,alimiter=limit={lim:.4f}:attack=3"
                      f":release=60:level=false")
            else:
                af += (f":linear=true:measured_I={m['input_i']}"
                       f":measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                       f":measured_thresh={m['input_thresh']}"
                       f":offset={m['target_offset']}")
        except Exception:
            pass
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-af", af,
                    "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000",
                    "-ac", "1", dst], check=True)


# =============================================================== kieu "doan"
# Nguyen nhan "giong may" do duoc 01/10/2026 (doan mau 3 cell Can Long, 430 ky
# tu, cung giong, xem OUTBOX/test-giong-2026-10-01/README.md):
#   1. Kieu "cau" goi TTS rieng tung cau/ve -> moi cau engine lai "mo mieng"
#      nhu cau dau tien (cao do va luc len tu dau, ha het o cuoi), chuoi cau
#      thanh chuoi cau doc lap. Nguoi that doc mot mach, cau sau noi tiep cau
#      truoc. Gui CA DOAN mot lan de engine tu lam ngu dieu lien cau.
#   2. Lang giua cau do ta chen roi nhan chung mot he so (khoa_im_lang) -> cac
#      khoang lang gan bang nhau, tai bat duoc metronome. Kieu "doan" GIU khoang
#      lang engine tu dat (sau phay ngan, sau cham dai, bien thien tu nhien) va
#      chi GIAN chung ra cho du ty le im lang cua kenh.
#   3. Nhay rate/pitch theo vai tro cau (ROLE_PROSODY) + rubberband doi cao do
#      tren Vbee -> cau lien nhau khac giong nhau. Kieu "doan" bo het.
# Ky tu viet tay van dung: // /// //// cat doan + chen lang, ^ hit hoi, * cham.
# '|' khong cat nua ma doi thanh dau phay de engine tu ngat.
DOAN_PAUSE_MIN = 0.14     # ngan hon = khe tac am (p,t,c) trong tu, do edge 0.07-0.10s; gian vao la vo tu
DOAN_PAUSE_MAX = 1.20     # khong gian khoang lang noi tai qua muc nay
DOAN_SHRINK_MIN = 0.55    # nhip nhanh (nhip < 1) duoc rut lang noi tai toi day
DOAN_BREATH_GAP = 1.20    # hit hoi tu dong chi sau lang >= muc nay (///, ////)
DOAN_BREATH_MIN_WORDS = 10
NHAN_DR_DOAN = -5.0       # '*' trong kieu doan: ca manh cham 5%, khong nhay pitch
_PHRASE_SPLIT = re.compile(r'(?<=[,.;:!?])\s+')


def _hat(text):
    """Hat giong co dinh theo noi dung — build lai cho ket qua y het."""
    import random
    return random.Random(int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16))


def plan_pieces(text, base_pct=0.0, breath=None, cell_end_gap=True):
    """Chia cell thanh cac MANH doc mot lan goi (chi cat tai // /// ////).

    Tra ve list dict {text, rate_pct, gap, breath}. `gap` la lang CHEN SAU manh
    (ky tu viet tay + nghi cuoi cell), co bien thien nhe theo hat giong.
    """
    if breath is None:
        breath = os.environ.get("TTS_BREATH", "1") != "0"
    t = re.sub(r'([.,;:!?…])\s*\|', r'\1', text or "")
    t = re.sub(r'\s*\|\s*', ', ', t)
    rnd = _hat(t)
    out = []
    for p in split_marks(t):
        txt = prep_vo_text(p["text"])
        if not txt:
            continue
        gap = p["extra_gap"] * (NHAN_GAP_MUL if p["nhan"] else 1.0)
        out.append({"text": txt, "gap": gap, "breath": bool(p["breath"]),
                    "rate_pct": base_pct + (NHAN_DR_DOAN if p["nhan"] else 0.0)})
    if not out:
        return out
    if cell_end_gap:
        out[-1]["gap"] += GAP_CELL_END
    for k, u in enumerate(out):
        if u["gap"] > 0:
            u["gap"] = round(u["gap"] * rnd.uniform(0.92, 1.08), 3)
        if (breath and k and not u["breath"]
                and out[k - 1]["gap"] >= DOAN_BREATH_GAP
                and len(u["text"].split()) >= DOAN_BREATH_MIN_WORDS):
            u["breath"] = True
        if not breath:
            u["breath"] = False
    return out


def _read_pcm(path):
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.copy(), sr


def _write_pcm(path, x, sr):
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.astype("int16").tobytes())


def tim_lang(x, sr, min_dur=DOAN_PAUSE_MIN):
    """Tim khoang lang NOI TAI (khong tinh dau/cuoi) trong mot manh giong.

    Nguong tuong doi: 38 dB duoi muc khung to (p95), san -55 dBFS — raw Vbee va
    edge khong cung muc to nen nguong tuyet doi -40dB bat sai.
    """
    import numpy as np
    hop = int(sr * 0.01)
    n = len(x) // hop
    if n < 3:
        return []
    fr = x[:n * hop].astype(np.float64).reshape(n, hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) / 32768.0 + 1e-9)
    thr = max(-55.0, float(np.percentile(db, 95)) - 38.0)
    quiet = db < thr
    res, k = [], 0
    while k < n:
        if quiet[k]:
            j = k
            while j < n and quiet[j]:
                j += 1
            if k > 0 and j < n and (j - k) * 0.01 >= min_dur:
                res.append((k * 0.01, j * 0.01))
            k = j
        else:
            k += 1
    return res


def gian_lang(x, sr, pauses, new_lens):
    """Doi do dai tung khoang lang, cat/chen o GIUA khoang (vung lang nhat)."""
    import numpy as np
    parts, pos = [], 0
    for (s, e), nl in zip(pauses, new_lens):
        mid = int((s + e) / 2 * sr)
        delta = int(round((nl - (e - s)) * sr))
        parts.append(x[pos:mid])
        if delta >= 0:
            parts.append(np.zeros(delta, dtype=np.int16))
            pos = mid
        else:
            pos = mid - delta          # bo -delta mau o giua khoang lang
    parts.append(x[pos:])
    return np.concatenate(parts) if parts else x


def phan_lang(pieces_pauses, noi, co_dinh, hat):
    """Tinh do dai moi cho moi khoang lang noi tai de ca cell dat ty le im lang.

    Tong lang = lang noi tai + lang chen (ky tu viet tay, cuoi cell). Dich =
    IM_LANG_DICH x TTS_GAP_MUL nhu kieu cu, nhung chi GIAN lang noi tai — phan
    them chia theo p^1.5 nen lang cuoi cau (dai san) gian nhieu hon lang sau
    dau phay: giu dung hinh dang cua engine, khong ep ve mot muc. Them bien
    thien +-10% co hat giong de khong co hai khoang bang nhau.
    """
    allp = [e - s for pp in pieces_pauses for (s, e) in pp]
    P = sum(allp)
    can = noi * (IM_LANG_DICH / (1.0 - IM_LANG_DICH)) * _gap_mul() - co_dinh
    out = []
    if P <= 0:
        return [[e - s for (s, e) in pp] for pp in pieces_pauses]
    if can >= P:
        w = [p ** 1.5 for p in allp]
        W = sum(w) or 1.0
        new = [min(max(DOAN_PAUSE_MAX, p), p + (can - P) * wi / W)
               for p, wi in zip(allp, w)]
    else:
        k = max(DOAN_SHRINK_MIN, can / P)
        new = [max(0.06, p * k) for p in allp]
    new = [round(max(0.05, v * hat.uniform(0.9, 1.1)), 3) for v in new]
    i = 0
    for pp in pieces_pauses:
        out.append(new[i:i + len(pp)])
        i += len(pp)
    return out


def _moc_tu(text, spans, t0, words_raw=None, remap=None):
    """Moc tung tu cho mot manh.

    Co WordBoundary (edge) -> doi moc qua `remap`. Khong co (Vbee/Azure) -> neu
    so cum giua dau cau bang so doan dang noi thi gan cum nao vao doan nay (khop
    gan tuyet doi), khong thi chia theo so ky tu tren thoi gian DANG NOI (bo qua
    khoang lang) — van tot hon chia deu ca manh.
    """
    words = text.split()
    if words_raw:
        off = words_raw[0]["t"]
        res = []
        for w in words_raw:
            a = remap(w["t"] - off)
            b = remap(w["t"] - off + w["d"])
            res.append({"w": w["w"], "t": round(t0 + a, 3), "d": round(max(0.05, b - a), 3)})
        return res
    phrases = [p for p in _PHRASE_SPLIT.split(text) if p.strip()]
    res = []
    if len(phrases) == len(spans) and len(spans) > 1:
        for ph, (a, b) in zip(phrases, spans):
            ws = ph.split()
            per = (b - a) / max(1, len(ws))
            res += [{"w": w, "t": round(t0 + a + k * per, 3), "d": round(per, 3)}
                    for k, w in enumerate(ws)]
        return res
    tot = sum(b - a for a, b in spans) or 1e-3
    chars = sum(len(w) + 1 for w in words) or 1
    acc = 0.0
    for w in words:
        pos = acc / chars * tot
        # doi vi tri tren truc "dang noi" sang truc thoi gian that
        for a, b in spans:
            if pos <= (b - a):
                t = a + pos
                break
            pos -= (b - a)
        else:
            t = spans[-1][1] if spans else 0.0
        d = (len(w) + 1) / chars * tot
        res.append({"w": w, "t": round(t0 + t, 3), "d": round(d, 3)})
        acc += len(w) + 1
    return res


def doan_render_cell(text, out_path, synth, lufs=-16.0, base_pct=0.0,
                     workers=2, cell_end_gap=True):
    """Dung giong cho mot cell theo kieu "doan" — dung chung cho moi provider.

    `synth(text, rate_pct, raw_path)` goi TTS mot lan cho CA manh, tra list moc
    tu {t,d,w} (edge) hoac None. Tra ve (speech_dur, total_dur, word_timings).
    """
    from concurrent.futures import ThreadPoolExecutor
    from probe import duration

    pieces = plan_pieces(text, base_pct=base_pct, cell_end_gap=cell_end_gap)
    tmp_dir = os.path.join(os.path.dirname(out_path), "_seg",
                           os.path.splitext(os.path.basename(out_path))[0])
    os.makedirs(tmp_dir, exist_ok=True)

    def _one(iu):
        i, u = iu
        raw = os.path.join(tmp_dir, f"doan{i}.raw")
        wav = os.path.join(tmp_dir, f"doan{i}.wav")
        words = synth(u["text"], u["rate_pct"], raw)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw,
                        "-af", TRIM_AF + ",aresample=48000",
                        "-ac", "1", "-c:a", "pcm_s16le", wav], check=True)
        return wav, words

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        got = list(ex.map(_one, list(enumerate(pieces))))

    pcm, pauses, noi = [], [], 0.0
    for wav, _ in got:
        x, sr = _read_pcm(wav)
        pp = tim_lang(x, sr)
        pcm.append((x, sr))
        pauses.append(pp)
        noi += len(x) / sr - sum(e - s for s, e in pp)
    co_dinh = sum(u["gap"] for u in pieces)
    new_lens = phan_lang(pauses, noi, co_dinh, _hat(text + "|lang"))

    items, lead, timings, cursor, speech = [], 0.0, [], 0.0, 0.0
    for i, (u, (wav, words), (x, sr), pp, nl) in enumerate(
            zip(pieces, got, pcm, pauses, new_lens)):
        y = gian_lang(x, sr, pp, nl)
        wav2 = os.path.join(tmp_dir, f"doan{i}g.wav")
        _write_pcm(wav2, y, sr)

        def remap(t, pp=pp, nl=nl):
            sh = 0.0
            for (s, e), L in zip(pp, nl):
                if t > (s + e) / 2:
                    sh += L - (e - s)
            return t + sh
        # cac doan DANG NOI sau khi gian (de gan moc tu cho Vbee/Azure)
        spans, a = [], 0.0
        for (s, e), L in zip(pp, nl):
            spans.append((remap(a), remap(s)))
            a = e
        spans.append((remap(a), len(y) / sr))

        prev_gap = pieces[i - 1]["gap"] if i else 0.0
        if u["breath"]:
            b = breath_wav(tmp_dir)
            if i == 0:
                lead = BREATH_DUR + 0.06
                items += [("a", b), ("s", 0.06)]
                cursor += lead
            elif prev_gap >= BREATH_DUR + 0.18:
                # hoi khoet tu cuoi khoang lang truoc — khong doi tong do dai
                items[-1] = ("s", round(prev_gap - BREATH_DUR - 0.06, 3))
                items += [("a", b), ("s", 0.06)]
        timings += _moc_tu(u["text"], spans, cursor, words, remap)
        d = len(y) / sr
        items.append(("a", wav2))
        speech += d - sum(nl)
        cursor += d
        if u["gap"] > 0:
            items.append(("s", u["gap"]))
            cursor += u["gap"]

    concat_track(items, tmp_dir, out_path, lufs=lufs)
    return round(speech, 3), duration(out_path), timings


def edge_render_cell(text, out_path, voice, base_pct=0.0, pitch="+0Hz",
                     volume="+0%", lufs=-16.0, tries=3):
    """Doc TUNG CAU -> cat lang -> ghep lai voi khoang lang do ta quyet dinh.

    Tra ve (speech_dur, total_dur, word_timings). speech_dur khong tinh khoang
    lang — day moi la con so dung de do toc do doc.
    """
    import time
    import edge_tts
    from probe import duration

    if tts_mode() == "doan":
        async def _stream(t, rate_str, raw):
            c = edge_tts.Communicate(t, voice, rate=rate_str, pitch=pitch,
                                     volume=volume, boundary="WordBoundary")
            words, buf = [], bytearray()
            async for ch in c.stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append({"t": ch["offset"] / TICKS,
                                  "d": ch["duration"] / TICKS, "w": ch["text"]})
            with open(raw, "wb") as f:
                f.write(bytes(buf))
            return words

        def _synth(t, pct, raw):
            rs = f"{int(round(max(-40.0, min(60.0, pct)))):+d}%"
            for attempt in range(tries):
                try:
                    return asyncio.run(_stream(t, rs, raw))
                except Exception:
                    if attempt == tries - 1:
                        raise
                    time.sleep(2 + 2 * attempt)
        return doan_render_cell(text, out_path, _synth, lufs=lufs,
                                base_pct=base_pct, workers=1)

    base_pitch = float(re.sub(r"[^\d.+-]", "", pitch) or 0.0)
    units = plan_units(prep_vo_text(text), base_pct=base_pct,
                       base_pitch_hz=base_pitch)
    tmp_dir = os.path.join(os.path.dirname(out_path), "_seg",
                           os.path.splitext(os.path.basename(out_path))[0])
    os.makedirs(tmp_dir, exist_ok=True)

    async def _one(sent, rate_str, raw, pitch_str):
        # boundary mac dinh la SentenceBoundary -> khong co moc tung tu.
        c = edge_tts.Communicate(sent, voice, rate=rate_str, pitch=pitch_str,
                                 volume=volume, boundary="WordBoundary")
        words, buf = [], bytearray()
        async for ch in c.stream():
            if ch["type"] == "audio":
                buf += ch["data"]
            elif ch["type"] == "WordBoundary":
                words.append({"t": ch["offset"] / TICKS,
                              "d": ch["duration"] / TICKS, "w": ch["text"]})
        with open(raw, "wb") as f:
            f.write(bytes(buf))
        return words

    wavs, durs, all_words = [], [], []
    for i, u in enumerate(units):
        raw = os.path.join(tmp_dir, f"raw{i}.mp3")
        wav = os.path.join(tmp_dir, f"seg{i}.wav")
        for attempt in range(tries):
            try:
                words = asyncio.run(_one(u["text"], u["rate"], raw, u["pitch"]))
                break
            except Exception:
                if attempt == tries - 1:
                    raise
                time.sleep(2 + 2 * attempt)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw,
                        "-af", TRIM_AF + ",aresample=48000",
                        "-ac", "1", "-c:a", "pcm_s16le", wav], check=True)
        wavs.append(wav)
        durs.append(duration(wav))
        all_words.append(words)

    items, head = plan_track(units, wavs, durs, tmp_dir)
    timings, cursor, speech = [], head, 0.0
    for u, d, words in zip(units, durs, all_words):
        off = words[0]["t"] if words else 0.0   # WordBoundary tinh truoc khi trim
        for w in words:
            timings.append({"w": w["w"], "t": round(cursor + w["t"] - off, 3),
                            "d": round(w["d"], 3)})
        speech += d
        cursor += d + u["gap"]

    concat_track(items, tmp_dir, out_path, lufs=lufs)
    return round(speech, 3), duration(out_path), timings


def vbee_render_cell(text, out_path, voice, base_pct=0.0, lufs=-16.0,
                     workers=2):
    """Nhu edge_render_cell nhung doc bang Vbee (vbee.vn), giong tieng Viet that.

    Vbee chi nhan speed_rate (do that 2026-09-12: bao hoa ngoai [0.7, 1.2] —
    0.5/0.6/0.7 cho ra cung mot do dai) va KHONG tra moc tung tu. Nen:
      - nhip cau van do ta chen (GAP_BY_PUNCT), giong het duong edge;
      - moc tu duoc noi suy DEU trong tung CAU (khong phai deu ca cell) — sai so
        nho hon nhieu so voi chia deu toan cell ma assemble._caption_filter dung
        khi thieu moc.
    Tra ve (speech_dur, total_dur, word_timings).
    """
    from concurrent.futures import ThreadPoolExecutor

    import vbee
    from probe import duration

    if tts_mode() == "doan":
        def _synth(t, pct, raw):
            # Khong rubberband, khong doi rate giua cac cau — mot toc do cho ca manh.
            vbee.synth(t, raw, voice_code=voice,
                       speed_rate=1.0 + max(-30.0, min(20.0, pct)) / 100.0)
            return None
        return doan_render_cell(text, out_path, _synth, lufs=lufs,
                                base_pct=base_pct, workers=workers)

    units = plan_units(prep_vo_text(text), base_pct=base_pct)
    tmp_dir = os.path.join(os.path.dirname(out_path), "_seg",
                           os.path.splitext(os.path.basename(out_path))[0])
    os.makedirs(tmp_dir, exist_ok=True)

    def _one(i_unit):
        # Vbee khong nhan cao do -> dich cao do o hau ky bang rubberband, giu
        # nguyen do dai. Nho vay cau chot van tram xuong duoc nhu ben edge.
        i, u = i_unit
        pct = float(u["rate"].rstrip("%"))
        raw = os.path.join(tmp_dir, f"raw{i}.mp3")
        wav = os.path.join(tmp_dir, f"seg{i}.wav")
        vbee.synth(u["text"], raw, voice_code=voice,
                   speed_rate=1.0 + max(-30.0, min(20.0, pct)) / 100.0)
        af = TRIM_AF + ",aresample=48000"
        ratio = pitch_ratio(u["pitch"])
        if ratio:
            af += f",rubberband=pitch={ratio:.4f}"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw,
                        "-af", af, "-ac", "1", "-c:a", "pcm_s16le", wav],
                       check=True)
        return wav

    with ThreadPoolExecutor(max_workers=workers) as ex:
        wavs = list(ex.map(_one, list(enumerate(units))))

    durs = [duration(w) for w in wavs]
    items, head = plan_track(units, wavs, durs, tmp_dir)

    timings, cursor, speech = [], head, 0.0
    for u, wav, d in zip(units, wavs, durs):
        words = u["text"].split()
        per = d / max(1, len(words))
        for k, w in enumerate(words):
            timings.append({"w": w, "t": round(cursor + k * per, 3),
                            "d": round(per, 3)})
        speech += d
        cursor += d + u["gap"]

    concat_track(items, tmp_dir, out_path, lufs=lufs)
    return round(speech, 3), duration(out_path), timings


def _key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        raise SystemExit(
            "Thieu ELEVENLABS_API_KEY. Dat: $env:ELEVENLABS_API_KEY='...'")
    return k


def _eleven_call(path, headers, data=None):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(API + path, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"ElevenLabs loi {e.code}: {body}")


def generate_one(key, voice, model, text, out_path, stability=0.45, similarity=0.8):
    import json as _j
    body = _j.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability, "similarity_boost": similarity,
            "style": 0.2, "use_speaker_boost": True,
        },
    }).encode("utf-8")
    audio = _eleven_call(
        f"/v1/text-to-speech/{voice}",
        {"xi-api-key": key, "Content-Type": "application/json",
         "Accept": "audio/mpeg"}, data=body)
    with open(out_path, "wb") as f:
        f.write(audio)
    print(f"OK  {os.path.basename(out_path)}  ({len(audio)/1024:.0f} KB)")


def azure_render_cell(text, out_path, voice, base_pct=0.0, gap_scale=0.55,
                      lufs=-16.0):
    """Doc CA CELL bang mot khoi SSML — khong cat roi tung cau roi dan lai.

    Khac han duong edge: o day khoang nghi la <break> nam trong ban tong hop nen
    may thoi nhip lien mach, cho noi khong bi cung. Doi lai REST API khong tra
    moc tung tu, nen moc duoc suy ra: tru het break khoi tong thoi luong, phan
    con lai chia cho cac don vi theo so ky tu, roi chia deu trong tung don vi.
    Sai so du nho cho phu de vi moi cell chi ~8 giay.

    gap_scale: Azure da TU nghi o cuoi cau, cong them break cua ta thanh nghi
    chong nghi (do thuc te: 46.2s so voi 35.1s ben edge cho cung 10 cau). He so
    nay rut break lai cho khop.
    """
    import azure_tts as AZ
    from probe import duration

    if tts_mode() == "doan":
        def _synth(t, pct, raw):
            AZ.synth_ssml(AZ.build_ssml_doan(t, voice, rate_pct=pct), raw)
            return None
        return doan_render_cell(text, out_path, _synth, lufs=lufs,
                                base_pct=base_pct, workers=2)

    gap_scale = float(os.environ.get("AZURE_GAP_SCALE", gap_scale))
    units = plan_units(prep_vo_text(text), base_pct=base_pct)
    for u in units:
        u["gap"] = round(u["gap"] * gap_scale, 3)
    tmp = out_path + ".raw.mp3"
    AZ.synth_ssml(AZ.build_ssml(units, voice), tmp)
    _loudnorm_2pass(tmp, out_path, lufs=lufs)
    os.remove(tmp)

    total = duration(out_path)
    gaps = sum(u["gap"] for u in units)
    speech = max(0.01, total - gaps)
    chars = sum(max(1, len(u["text"])) for u in units)

    timings, cursor = [], 0.0
    for u in units:
        seg = speech * max(1, len(u["text"])) / chars
        words = u["text"].split()
        per = seg / max(1, len(words))
        for k, w in enumerate(words):
            timings.append({"w": w, "t": round(cursor + k * per, 3),
                            "d": round(per, 3)})
        cursor += seg + u["gap"]
    return round(speech, 3), round(total, 3), timings


def _speech_dur(path, db=-40.0, min_sil=0.12):
    """Thoi gian DANG NOI cua file = tong - khoang lang (silencedetect -40dB,
    cung cach do trong CLAUDE.md). Dung cho cache cu chua ghi 'speech'."""
    from probe import duration
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
                            f"silencedetect=noise={db}dB:d={min_sil}", "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        sil = sum(float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)",
                                                r.stderr or ""))
        tot = duration(path)
        return max(0.01, tot - sil) if tot > sil else None
    except Exception:
        return None


def generate_for_case(root, cfg, voice=DEFAULT_VOICE, model=DEFAULT_MODEL,
                      provider="edge", edge_voice=None, rate="+0%",
                      stability=0.45, similarity=0.8, skip_existing=True,
                      target_wpm=158.0, wpm_lo=145.0, wpm_hi=172.0,
                      fix_pace=True):
    out_dir = os.path.join(root, "build", "voice")
    os.makedirs(out_dir, exist_ok=True)
    cells = [c for c in cfg["cells"] if c.get("vo")]
    if not cells:
        print("config khong co cell nao co 'vo'")
        return []

    try:
        base_pct0 = float(str(rate).replace("%", "").replace("+", "") or 0.0)
    except ValueError:
        base_pct0 = 0.0

    if provider == "edge":
        voice = edge_voice or EDGE_VOICE
        key = None

        def generate(text, out_path, base_pct):
            return edge_render_cell(text, out_path, voice, base_pct=base_pct)
    elif provider == "azure":
        import azure_tts as AZ
        voice = edge_voice or AZ.DEFAULT_VOICE
        key = None

        def generate(text, out_path, base_pct):
            return azure_render_cell(text, out_path, voice, base_pct=base_pct)
    elif provider == "vbee":
        import vbee as VB
        voice = edge_voice or VB.DEFAULT_VOICE
        key = None

        def generate(text, out_path, base_pct):
            # Vbee bao hoa ngoai [0.7,1.2] -> khong the day qua -30%/+20%.
            return vbee_render_cell(text, out_path, voice,
                                    base_pct=max(-28.0, min(18.0, base_pct)))
    else:
        key = _key()

        def generate(text, out_path, base_pct):
            from probe import duration as _d
            generate_one(key, voice, model, text, out_path,
                         stability=stability, similarity=similarity)
            d = _d(out_path)
            return d, d, []

    from probe import duration

    def _text_hash(c):
        # provider PHAI nam trong hash: Azure va edge dung chung ten giong
        # (vi-VN-NamMinhNeural) nen thieu no thi doi provider ma cache van bao
        # "con nguyen", bo qua sinh lai va giu y nguyen giong cu.
        # Ban thu am phu thuoc ca TOC DO va HE SO NGHI, khong chi van ban.
        # Thieu hai thu nay thi doi nhip xong chay lai se "xong" trong tich tac
        # va tra ve y nguyen ban cu — dung cai bay da dinh mot lan.
        gs = os.environ.get("AZURE_GAP_SCALE", "") if provider == "azure" else ""
        br = os.environ.get("TTS_BREATH", "1")
        sig = (f'{c["vo"]}|{provider}|{voice}|p{PROSODY_VERSION}'
               f'|r{base_pct0:g}|g{gs}|b{br}|m{_gap_mul():g}'
               f'|i{IM_LANG_DICH:g}|t{tts_mode()}')
        return hashlib.md5(sig.encode("utf-8")).hexdigest()[:12]

    def gen_one(c, base_pct):
        name = f"cell-{c['id']}"
        out_path = os.path.join(out_dir, f"{name}.mp3")
        speech, total, words = generate(c["vo"], out_path, base_pct)
        # wpm do tren PHAN NOI THAT. Ban cu chia cho do dai ca file (gom ~1s
        # lang cuoi) nen tuong giong doc cham, roi ep rate len — ket qua la doc
        # gap 200+ wpm roi ngoi im gan mot giay. Chinh la cam giac "may doc".
        wpm = len(strip_marks(c["vo"]).split()) / (max(0.01, speech) / 60.0)
        with open(os.path.join(out_dir, f"{name}.words.json"), "w",
                  encoding="utf-8") as f:
            # speech/dur/rate_pct ghi kem de lan chay sau (nhanh cache) tinh
            # dung wpm tren phan NOI, khong phai tren ca file gom im lang.
            json.dump({"hash": _text_hash(c), "words": words,
                       "speech": round(speech, 3), "dur": round(total, 3),
                       "rate_pct": round(base_pct, 1)}, f,
                      ensure_ascii=False)
        # File tam tung cau (raw mp3 + wav 48k + joined.wav) chi dung de ghep:
        # case Can Long 186 cell de lai 319 MB o build/voice/_seg den het case.
        import shutil
        shutil.rmtree(os.path.join(out_dir, "_seg", name), ignore_errors=True)
        return {"seg": name, "file": f"{name}.mp3", "dur": round(total, 3),
                "speech": round(speech, 3), "cell": c["id"],
                "wpm": round(wpm, 0), "rate_pct": round(base_pct, 1)}

    # pass 1: sinh tai rate goc (hoac skip neu da co VA text khong doi)
    #
    # Vbee mat ~20s cho moi cell (goi API + tai ve). Chay tuan tu thi mot script
    # 140 cell ton gan mot tieng. Cell doc lap hoan toan voi nhau nen chay song
    # song duoc; moi cell ben trong da co ThreadPool rieng cho tung cau, nen giu
    # cell_workers thap de tong so request dong thoi khong lam Vbee tra 429.
    def _pass1(c):
        name = f"cell-{c['id']}"
        out_path = os.path.join(out_dir, f"{name}.mp3")
        wpath = os.path.join(out_dir, f"{name}.words.json")
        cached, meta = None, {}
        if skip_existing and os.path.exists(out_path) and os.path.exists(wpath):
            try:
                with open(wpath, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("hash") == _text_hash(c):
                    cached = duration(out_path)
            except Exception:
                cached = None
        if cached:
            # wpm phai tinh tren PHAN NOI nhu gen_one. Ban cu lay ca do dai file
            # (gom ~24% im lang) lam speech -> wpm thap gia ~25% -> pass 2 tuong
            # cell cham, sinh lai ca nhung cell da dat nhip.
            speech = meta.get("speech") or _speech_dur(out_path) or cached
            return {"seg": name, "file": f"{name}.mp3",
                    "dur": round(cached, 3), "speech": round(speech, 3),
                    "cell": c["id"],
                    "wpm": round(len(strip_marks(c["vo"]).split()) / (speech / 60.0), 0),
                    "rate_pct": meta.get("rate_pct", base_pct0)}
        return gen_one(c, base_pct0)

    # edge ban cu chay TUAN TU (1): 12 cell test mat 158s, toan cho mang. 4 luong
    # edge khong bi chan (do 01/10/2026). Vbee 5 cell x TTS_UNIT_WORKERS cau.
    cell_workers = int(os.environ.get("TTS_CELL_WORKERS",
                                      "5" if provider == "vbee" else "4"))
    if cell_workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=cell_workers) as ex:
            manifest = list(ex.map(_pass1, cells))   # map giu nguyen thu tu cell
    else:
        manifest = [_pass1(c) for c in cells]

    # pass 2: fix pace — CHINH MOT LAN, co giam chan, va giu lai ban tot hon.
    # Do thuc te: edge-tts tra ve do dai khac nhau ~7% giua hai lan goi CUNG
    # tham so, va rate khong don dieu tuyet doi (-25% co the cham hon -30%).
    # Vong lap duoi ba lan cua ban cu vi the cu bam bap quanh dich va moi lan
    # sinh lai la mot ban thu am khac — vua ton request vua khong hoi tu.
    if provider == "edge" and fix_pace:
        import shutil

        def _fix(i):
            m = manifest[i]
            c = next(x for x in cells if x["id"] == m["cell"])
            out_path = os.path.join(out_dir, f"{m['seg']}.mp3")
            for _ in range(2):
                w = manifest[i]["wpm"]
                if wpm_lo <= w <= wpm_hi:
                    break
                cur_pct = manifest[i].get("rate_pct", base_pct0)
                speed = (1.0 + cur_pct / 100.0) * (target_wpm / w)
                new_pct = max(-35.0, min(45.0, (speed - 1.0) * 100.0))
                new_pct = cur_pct + 0.6 * (new_pct - cur_pct)      # giam chan
                if abs(new_pct - cur_pct) < 1.5:
                    break
                bak = out_path + ".bak"
                shutil.copyfile(out_path, bak)
                cand = gen_one(c, new_pct)
                if abs(cand["wpm"] - target_wpm) < abs(w - target_wpm):
                    cand["fixed"] = True
                    manifest[i] = cand
                    print(f"  chinh nhip cell {c['id']}: {w:.0f} -> "
                          f"{cand['wpm']:.0f} wpm ({new_pct:+.0f}%)")
                    os.remove(bak)
                else:
                    shutil.move(bak, out_path)   # ban moi te hon -> giu ban cu
                    print(f"  giu nguyen cell {c['id']}: {w:.0f} wpm "
                          f"(thu {new_pct:+.0f}% ra {cand['wpm']:.0f})")
                    break

        # cell doc lap -> chinh nhip song song (ban cu tuan tu tung cell)
        if cell_workers > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=cell_workers) as ex:
                list(ex.map(_fix, range(len(manifest))))
        else:
            for i in range(len(manifest)):
                _fix(i)
        # canh bao cell con lech ngay ca sau 3 vong
        for m in manifest:
            if not (wpm_lo <= m["wpm"] <= wpm_hi):
                print(f"  WARN cell {m['cell']}: {m['wpm']:.0f} wpm ngoai "
                      f"[{wpm_lo:.0f},{wpm_hi:.0f}] (edge-tts gioi han rate)")

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"provider": provider, "voice": voice, "target_wpm": target_wpm,
                   "segs": manifest}, f, ensure_ascii=False, indent=2)
    total = round(sum(m["dur"] for m in manifest), 1)
    avg_wpm = round(sum(m["wpm"] for m in manifest) / max(1, len(manifest)), 0)
    print(f"\n{len(manifest)} cell VO, tong {total}s (~{total/60:.1f} phut), "
          f"avg {avg_wpm:.0f} wpm")
    return manifest


def list_voices():
    import urllib.request
    key = _key()
    raw = _eleven_call("/v1/voices", {"xi-api-key": key})
    for v in json.loads(raw).get("voices", []):
        print(f"{v['voice_id']}  {v['name']}  labels={v.get('labels', {})}")


def list_edge_voices():
    import asyncio
    import edge_tts
    vs = asyncio.run(edge_tts.list_voices())
    for v in vs:
        if v["Locale"].startswith("en-"):
            print(f"{v['ShortName']}  {v['Gender']}  {v['Locale']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--provider", choices=["elevenlabs", "edge"], default="edge")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--edge-voice", default=None)
    ap.add_argument("--rate", default="+0%")
    ap.add_argument("--wpm", type=float, default=170.0, help="target words/minute")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()

    if args.list_voices:
        if args.provider == "edge":
            list_edge_voices()
        else:
            list_voices()
        return

    root = os.path.abspath(args.case)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as CFG
    cfg = CFG.load(root)
    generate_for_case(root, cfg, args.voice, args.model,
                      provider=args.provider, edge_voice=args.edge_voice,
                      rate=args.rate, target_wpm=args.wpm)


if __name__ == "__main__":
    main()
