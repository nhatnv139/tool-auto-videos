"""
manifest.py — Doc clip-manifest.json va references.json.

clip-manifest.json: danh sach clip nguon truoc khi fetch.
[
  {"id": 1, "url": "https://youtu.be/PZqDFs2sbiY", "in": 7594, "out": 7606,
   "speaker": "Yoshua Bengio", "role": "Turing Award winner", "note": "hook"},
  ...
]

HoTro 3 dang in/out:
  "38.28"            -> mm.ss (38 phut 28 giay)
  "02:59" / "3:29"   -> mm:ss
  "7594" (int)       -> giay nguyen
  "1:22:17"          -> hh:mm:ss
out co the thieu (null) -> in + dur_mac_dinh (6s).
URL co the chua tham so t= (vi du ...&t=149s hoac ?t=7594) -> neu in thieu
thi lay tu t=.
"""
import json
import os
import re

DEFAULT_DUR = 6.0


class ManifestError(Exception):
    pass


def parse_time(v, default=None):
    """Giai ma thoi gian thanh giay. Chap nhan so, mm.ss, mm:ss, hh:mm:ss."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return default
    # hh:mm:ss hoac mm:ss
    m = re.match(r"^(\d+):(\d{1,2})(?::(\d{1,2}))?$", s)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2))
        se = int(m.group(3)) if m.group(3) else 0
        return h * 3600 + mi * 60 + se
    # mm.ss (phut.giay) — vi du "38.28"
    m = re.match(r"^(\d+)\.(\d{1,2})$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # t=149s hoac 149s
    m = re.match(r"^t=(\d+)s?$", s)
    if m:
        return float(m.group(1))
    # giay nguyen
    try:
        return float(s)
    except ValueError:
        raise ManifestError(f"khong hieu time '{v}'")


def url_time(url):
    """Lay thoi gian tu tham so t= trong URL neu co (vi du ?t=7594, &t=149s)."""
    m = re.search(r"[?&]t=(\d+)s?", url)
    return float(m.group(1)) if m else None


def load_manifest(root, path="clip-manifest.json"):
    full = os.path.join(root, path)
    if not os.path.exists(full):
        return []
    with open(full, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    seen = set()
    for i, item in enumerate(data):
        if "id" not in item:
            raise ManifestError(f"clip[{i}] thieu 'id'")
        cid = item["id"]
        if cid in seen:
            raise ManifestError(f"trung clip id {cid}")
        seen.add(cid)
        url = item["url"]
        t_url = url_time(url)
        cin = parse_time(item.get("in"), t_url)
        if cin is None:
            raise ManifestError(f"clip {cid}: thieu 'in' va khong co t= trong URL")
        out.append({
            "id": cid,
            "url": url,
            "in": cin,
            "out": parse_time(item.get("out"), cin + DEFAULT_DUR),
            "speaker": item.get("speaker", ""),
            "role": item.get("role", ""),
            "note": item.get("note", ""),
            "align": item.get("align", True),
            "src_type": item.get("type") or detect_src_type(url),
        })
    return out


def load_references(root, path="references.json"):
    full = os.path.join(root, path)
    if not os.path.exists(full):
        return []
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def is_skippable(url):
    """Nhung link khong the dung yt-dlp tai duoc (x.com, facebook...)."""
    return re.search(r"(x\.com|twitter\.com|facebook\.com|instagram\.com)", url) is not None


def detect_src_type(url):
    """Phan loai nguon: youtube | bilibili | douyin | other."""
    if re.search(r"(youtu\.be|youtube\.com)", url):
        return "youtube"
    if "bilibili.com" in url:
        return "bilibili"
    if re.search(r"(douyin\.com|iesdouyin\.com|v\.douyin)", url):
        return "douyin"
    return "other"


def extract_video_id(url):
    """Lay video id tu URL. YouTube 11 ky tu; Bilibili BV[0-9A-Za-z]{10}; douyin so dai."""
    m = re.search(r"(?:youtu\.be/|v=|/shorts/|/live/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"(BV[0-9A-Za-z]{10})", url)
    if m:
        return m.group(1)
    m = re.search(r"video/(\d{15,20})", url)
    if m:
        return m.group(1)
    return None
