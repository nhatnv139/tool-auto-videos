"""vbee.py — TTS tieng Viet qua Vbee AIVoice (vbee.vn). TRA PHI theo ky tu.

API async: POST /api/v1/tts -> {request_id} -> poll GET /api/v1/tts/{id} toi khi
SUCCESS -> tai audio_link ve.

Credential doc theo thu tu:
  1. bien moi truong VBEE_TOKEN / VBEE_APP_ID (hoac dong trong tool/.env)
  2. tool/vbee_config.json  {"token": "...", "app_id": "..."}

Vbee CHI nhan mot num dieu khien la speed_rate (0.8-1.2). input_type / emotion /
style / pitch / volume deu bi tra 400. The <break/> bi DOC TO LEN thanh chu chu
khong thanh khoang lang. Vi vay nhip cau phai do phia goi tu chen (xem
tts.vbee_render_cell; tu 01/10/2026 mac dinh doc CA DOAN giua hai ky tu // roi gian khoang lang noi tai, TTS_MODE=cau = kieu cu doc tung cau).
"""
import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "vbee_config.json")
BASE = "https://vbee.vn/api/v1/tts"

# Giong mac dinh: HN nam, chat dan tin/binh luan — gan nhat voi kenh su Viet.
DEFAULT_VOICE = "hn_male_manhdung_full_24k-st"


def _load_env():
    """Nap tool/.env vao os.environ neu chua co (giong stock._load_env)."""
    p = os.path.join(HERE, ".env")
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v


def creds():
    _load_env()
    token = os.environ.get("VBEE_TOKEN", "")
    app_id = os.environ.get("VBEE_APP_ID", "")
    if not (token and app_id) and os.path.exists(CFG_PATH):
        try:
            d = json.load(open(CFG_PATH, encoding="utf-8"))
            token = token or d.get("token", "")
            app_id = app_id or d.get("app_id", "")
        except Exception:
            pass
    if not (token and app_id):
        raise SystemExit(
            "Thieu credential Vbee. Dat VBEE_TOKEN / VBEE_APP_ID trong tool/.env "
            "hoac tao tool/vbee_config.json {\"token\":..., \"app_id\":...}")
    return token, app_id


def _post(payload, token, tries=5):
    for i in range(tries):
        req = urllib.request.Request(
            BASE, data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + token,
                     "Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=90).read())
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            # CloudFront truoc vbee.vn hay tra 5xx nhat thoi khi ban lien tiep.
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2.0 * (2 ** i))
                continue
            raise RuntimeError(f"Vbee loi {e.code}: {detail or e.reason}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            if i < tries - 1:
                time.sleep(2.0 * (2 ** i))
                continue
            raise RuntimeError(f"Vbee loi mang: {e}")


def synth(text, out_path, voice_code=None, speed_rate=1.0, timeout=90):
    """Doc `text` -> ghi mp3 vao out_path. speed_rate bi kep trong [0.7, 1.2].

    Do that 2026-09-12 tren hn_male_manhdung_full_24k-st: API KHONG bao loi khi
    gui ngoai khoang, no chi bao hoa — 0.5/0.6/0.7 deu ra 148-151 am tiet/phut,
    1.2/1.5 deu ra 197. San duoi that la 0.7 chu khong phai 0.8 nhu ban cu kep;
    keo them duoc ~8% cham ma khong phai nho den atempo (meo tieng).
    """
    token, app_id = creds()
    speed = max(0.7, min(1.2, round(float(speed_rate), 2)))
    payload = {"app_id": app_id, "response_type": "direct",
               "input_text": text, "voice_code": voice_code or DEFAULT_VOICE,
               "audio_type": "mp3", "bitrate": 128, "speed_rate": str(speed)}
    j = _post(payload, token)
    res = j.get("result") or {}
    rid = res.get("request_id") or res.get("id") or ""
    link = res.get("audio_link") or ""
    if not (rid or link):
        raise RuntimeError(f"Vbee khong tra request_id/audio_link: {j}")

    # Hoi trang thai day hon luc dau (0,4s trong ~6s dau, sau do 1s): doan ngan
    # Vbee tra trong vai giay, cho tron 1s moi lan thi moi lan goi mat them
    # trung binh ~0,5s — nhan voi hang tram/nghin lan goi cua video 30 phut.
    # GET trang thai khong tinh phi ky tu. Tong thoi gian cho van la `timeout`.
    deadline = time.time() + timeout
    k = 0
    while time.time() < deadline:
        k += 1
        if link:
            try:
                data = urllib.request.urlopen(link, timeout=30).read()
                if len(data) > 1000:      # CDN tra trang rong khi chua san sang
                    with open(out_path, "wb") as f:
                        f.write(data)
                    return out_path
            except Exception:
                pass
        else:
            q = urllib.request.Request(
                BASE + "/" + str(rid), headers={"Authorization": "Bearer " + token})
            try:
                rr = (json.loads(urllib.request.urlopen(q, timeout=30).read())
                      .get("result") or {})
                st = (rr.get("status") or "").upper()
                if st == "SUCCESS":
                    link = rr.get("audio_link") or ""
                elif st in ("FAILURE", "ERROR", "FAILED"):
                    raise RuntimeError(f"Vbee bao loi: {rr}")
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"Vbee poll loi {e.code}")
            except (urllib.error.URLError, OSError, ValueError):
                pass
        time.sleep(0.4 if k <= 15 else 1.0)
    raise RuntimeError(f"Vbee: qua {timeout}s chua co audio")


def list_voices(query="", lang="vi-VN", limit=60):
    """In danh sach giong tu vbee_voices.json neu co (cache canh tool/)."""
    p = os.path.join(HERE, "vbee_voices.json")
    if not os.path.exists(p):
        print("Chua co tool/vbee_voices.json — copy tu du an khac hoac tai tu Vbee Studio.")
        return
    voices = json.load(open(p, encoding="utf-8")).get("voices", [])
    q = query.lower()
    n = 0
    for v in voices:
        if lang and v.get("lang") != lang:
            continue
        if q and q not in v["name"].lower() and q not in v["code"].lower():
            continue
        print(f"{v['code']:<55} {v['name']:<28} {v['gender']:<7} "
              f"{v['own']:<10} credit={v['credit']}")
        n += 1
        if n >= limit:
            print("...")
            break


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--query", default="")
    ap.add_argument("--say", default="")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--out", default="vbee-test.mp3")
    a = ap.parse_args()
    if a.list:
        list_voices(a.query)
    elif a.say:
        synth(a.say, a.out, a.voice)
        print("OK ->", a.out)
