"""azure_tts.py — Doc bang Azure Speech, dung SSML that.

Vi sao them duong nay khi da co edge-tts: edge-tts CHINH LA giong Azure, goi qua
cong mien phi khong chinh thuc — cung mot model nen chat giong y het. Khac biet
nam o dieu khien: edge chi nhan rate/pitch/volume ap cho CA cum, con Azure nhan
SSML nen mot lan goi lam duoc het:

    <prosody rate="-8%" pitch="-12Hz">cau chot</prosody>
    <break time="900ms"/>

Nghia la khoang nghi do MINH dat nam ngay trong ban tong hop, khong phai cat roi
ghep silence nhu ben edge — nhip lien mach hon va so lan goi giam tu 411 xuong
149 (moi cell mot lan).

Gia: bac F0 cua Azure cho 500.000 ky tu neural TTS mien phi moi thang. Ca video
21 phut ~21.000 ky tu, nen thuc te khong ton gi.

Can hai bien moi truong (dat trong tool/.env):
    AZURE_SPEECH_KEY=...
    AZURE_SPEECH_REGION=southeastasia

Dung thu:
    python tool/azure_tts.py --text "Ho goi thu do la than." --out thu.mp3
    python tool/azure_tts.py --voices          # liet ke giong tieng Viet
"""
import argparse
import html
import os
import sys
import urllib.error
import urllib.request

DEFAULT_VOICE = "vi-VN-NamMinhNeural"
DEFAULT_REGION = "southeastasia"
# 48kHz mono mp3: dung dinh dang ma phan con lai cua kit dang dung.
AUDIO_FORMAT = "audio-48khz-192kbitrate-mono-mp3"


def _load_env():
    """Doc tool/.env neu co (kit khong dung python-dotenv)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _creds():
    _load_env()
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION", DEFAULT_REGION)
    if not key:
        raise SystemExit(
            "thieu AZURE_SPEECH_KEY.\n"
            "  1. Tao resource 'Speech' tren portal.azure.com (bac F0 mien phi)\n"
            "  2. Them vao tool/.env:\n"
            "       AZURE_SPEECH_KEY=<key>\n"
            "       AZURE_SPEECH_REGION=<vung, vi du southeastasia>")
    return key, region


def build_ssml(units, voice=DEFAULT_VOICE, lang="vi-VN"):
    """Ghep cac don vi da phan vai tro (tts.plan_units) thanh mot khoi SSML.

    Moi don vi mang rate/pitch rieng; khoang nghi sau no thanh <break>. Toan bo
    cell di trong MOT request, nen giong lien mach thay vi ghep tu nhieu ban thu.
    """
    parts = []
    for u in units:
        txt = html.escape(u["text"])
        parts.append(f'<prosody rate="{u["rate"]}" pitch="{u["pitch"]}">'
                     f'{txt}</prosody>')
        gap = u.get("gap", 0.0)
        if gap > 0:
            parts.append(f'<break time="{int(round(gap * 1000))}ms"/>')
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{lang}"><voice name="{voice}">'
            f'{"".join(parts)}</voice></speak>')


def build_ssml_doan(text, voice=DEFAULT_VOICE, rate_pct=0.0, lang="vi-VN"):
    """SSML cho kieu "doan" (tts.TTS_MODE=doan): CA manh trong mot <prosody>
    duy nhat, khong <break>, khong doi pitch — de engine tu lam ngu dieu lien
    cau. Giong vi-VN (NamMinh, HoaiMy, MAI-Voice) khong co StyleList (do
    01/10/2026 qua voices/list) nen mstts:express-as khong dung duoc."""
    txt = html.escape(text)
    r = int(round(rate_pct))
    if r:
        txt = f'<prosody rate="{r:+d}%">{txt}</prosody>'
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{lang}"><voice name="{voice}">{txt}</voice></speak>')


def synth_ssml(ssml, out_path, timeout=90):
    key, region = _creds()
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    req = urllib.request.Request(
        url, data=ssml.encode("utf-8"), method="POST",
        headers={"Ocp-Apim-Subscription-Key": key,
                 "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": AUDIO_FORMAT,
                 "User-Agent": "ai-frontier-kit"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"Azure tra loi {e.code}: {body}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def synth(text, out_path, voice=DEFAULT_VOICE, base_pct=0.0):
    """Doc mot doan text: tu phan vai tro cau roi dung SSML."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import tts as T
    units = T.plan_units(T.prep_vo_text(text), base_pct=base_pct,
                         cell_end_gap=False)
    return synth_ssml(build_ssml(units, voice), out_path), units


def list_voices(prefix="vi-VN"):
    key, region = _creds()
    url = (f"https://{region}.tts.speech.microsoft.com"
           f"/cognitiveservices/voices/list")
    req = urllib.request.Request(url,
                                 headers={"Ocp-Apim-Subscription-Key": key})
    import json as _json
    with urllib.request.urlopen(req, timeout=30) as r:
        voices = _json.loads(r.read().decode("utf-8"))
    for v in voices:
        if v.get("Locale", "").startswith(prefix):
            styles = ",".join(v.get("StyleList") or []) or "-"
            print(f"  {v['ShortName']:<28} {v.get('Gender',''):<7} style: {styles}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--out", default="azure-thu.mp3")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--rate", type=float, default=0.0)
    ap.add_argument("--voices", action="store_true")
    ap.add_argument("--show-ssml", action="store_true")
    args = ap.parse_args()

    if args.voices:
        list_voices()
        return
    if not args.text:
        raise SystemExit("can --text hoac --voices")
    out, units = synth(args.text, args.out, args.voice, args.rate)
    if args.show_ssml:
        print(build_ssml(units, args.voice))
    for u in units:
        print(f"  [{u['role']:<8}] {u['rate']:>4} {u['pitch']:>6} "
              f"nghi {u['gap']:.2f}s | {u['text'][:52]}")
    print(f"\nOK  {out}")


if __name__ == "__main__":
    main()
