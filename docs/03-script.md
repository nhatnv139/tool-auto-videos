# 03-script.md — Khung script, giọng, marker

`videos/<topic>/script/script.md` là nguồn sự thật duy nhất. Thứ tự dòng =
thứ tự timeline. Mỗi dòng VO = một cell; độ dài cell tự tính theo duration TTS.

## Marker

| Marker | Cell | Ghi chú |
|---|---|---|
| `[[clip:ID]]` | clip | talking-head, giữ tiếng gốc, attribution tự thêm |
| `[[broll:ID]]` (hoặc `[[clip-mute:ID]]`) | clip-mute | lấy hình clip, tắt tiếng, VO đọc đè; `\|low` giữ tiếng nhẹ |
| `[[stock:"keyword"]]` | stock | stock footage (Pixabay/Pexels), VO đọc đè; không tìm thấy → card |
| `[[card:"text"\|src=...]]` | card | text im lặng, src = nguồn hiện góc dưới |
| `[[card:"..."\|vo="..."]]` | card | card có VO: narrator đọc, card hiện cùng lúc |
| `[[quote:"text"\|who=...\|role=...]]` | quote | quote lớn + attribution, tự thêm pause 0.8 |
| `[[black]]` | black | cắt đen (beat mạnh), VO sau đó đọc trên đen |
| `[[hold]]` | hold | đứng yên khung cuối shot trước |
| `[[sfx]]` | sfx | hiệu ứng hit tự sinh (noise burst) |
| `[[sfx:whoosh]]` | sfx | SFX từ kho `assets/sfx/`: whoosh/riser/hit/beep/pop/glitch/drone/transition. `\|dur=1.5` để cắt ngắn |
| `[[outro]]` | outro | "Sources in the description" |

## Hiệu ứng video (fx per-cell)

- `blur-in`: cold open mờ → nét (1.2s đầu).
- `vhs`: scanline + chroma noise (cảm giác băng cũ).
- `glitch`: jitter ngang nhẹ.
- `shake`: camera shake 0.5s đầu (impact moment).
- `flash`: trắng flash 0.15s đầu (cắt đen / hit) — dùng cho `[[black|fx=flash]]`.

## Kho SFX (Mixkit — miễn phí thương mại, không cần attribution)

```
python tool/run.py --case videos/<topic> sfx            # tải tất cả loại cơ bản
python tool/run.py --case videos/<topic> sfx --refresh  # tải lại + normalize
python tool/run.py --case videos/<topic> sfx --list-sfx # xem gì đã có
```

Các loại (~27): `whoosh, riser, hit, beep, pop, glitch, drone, transition,
click, notification, alarm, swoosh, horror, tension, science-fiction, machine,
keyboard, impact, boom, punch, rising, cinematic-hit, digital, ui,
glitch-whoosh, cinematic-boom, hit-impact`.
Dùng: `[[sfx:whoosh]]` (đè lên cell kế tiếp, không tạo màn đen). Tất cả
normalize -16 LUFS (không chói). Mixkit free thương mại — kiểm tra license
trang web trước khi đăng.

Thêm option: `|pause=1.5` (im lặng sau cell), `|music=swell/out/drop`,
`|fx=blur-in/vhs/glitch/shake/flash`, `|zoom=1.12`, `|crop=x,y,w,h`,
`|flip=true`, `|low` (b-roll giữ tiếng nhẹ).

## Caption (subtitle)

- Caption tự tách **theo đoạn câu ngắn** (~42 ký tự), hiện **instant** (không
  fade), 1–2 dòng dưới màn hình. Mỗi đoạn xuất hiện đúng lúc giọng đọc tới.
- Tự sanitize ký tự không có trong font (→, … → ->, ...) — hết "ô vuông".
- Câu dài quá 4 đoạn → `plan` cảnh báo, nên tách câu trong script.

## Crop/zoom tránh Content ID

Mọi clip mặc định `zoom=1.06` (reframe nhẹ, video fingerprint khác bản gốc).
Thêm tùy chọn khi cần: `|zoom=1.12`, `|crop=0.1,0.2,0.7,0.7` (góc + kích thước
tỷ lệ), `|flip=true`. Lưu ý: zoom/crop chỉ đổi video fingerprint, **audio vẫn
match** — không đảm bảo tránh claim 100%. Phòng thủ chính vẫn là clip ngắn +
commentary + attribution.

## Quy tắc chống lặp nguồn

Trong 1 section (cold open / 1 beat), **1 video nguồn chỉ dùng 1 clip**. Cần clip
thứ 2 → lấy từ nguồn khác. `plan` sẽ cảnh báo nếu 2 clip liền nhau cùng video URL.

## Ví dụ script

```markdown
## Cold open

[[clip:1|fx=blur-in]]
This is the most dangerous bet in AI.

[[broll:2]]
And the researchers behind it are hiding their identity.

[[card:"6x more persuasive than human comments"|src=arxiv:2603.25326|pause=1.0]]

[[quote:"They're almost like sociopaths."|who=Yoshua Bengio|role=Turing Award winner]]

[[stock:"server room dark"]
And behind the scenes, this is what it looks like.

[[black]]
It wasn't a test.

[[sfx]]
```

## Quy tắc viết VO

- Mỗi dòng VO = 1 ý, 5–20 giây nói (~15–55 từ).
- **Khối VO dài 8–15s** (gộp 2–4 câu vào 1 cell) — đừng cắt câu lẻ 2–4s (gây đứt quãng). VO ngắn = dồn dập.
- Không bịa số liệu. Số liệu đứng một mình cuối câu.
- Joke sau clip nghiêm túc ≤ 2 dòng, không joke đè clip.
- Cầu nối leo thang: "But it gets way worse", "But that's just the beginning".
- Câu hỏi tu từ giữa chân để giữ người xem.
- `pause_after` 0.8–1.5s sau reveal lớn; nhạc `drop` ở twist.

## Quy tắc nhịp (tránh "đứt quãng")

- **Khối VO dài** chạy trên `[[stock:...]]` (stock free → dùng dài thoải mái).
- **Stock keyword đa dạng — KHÔNG lặp**: mỗi keyword tối đa **2 lần/video**.
  Tool tự mở rộng sang **keyword LIÊN QUAN cùng theme** (xem `STOCK_THEMES`
  trong `tool/stock.py`) — vd "security camera corridor" → dùng chung pool với
  "cctv street camera", "traffic camera road"... để mỗi đoạn 4s là 1 cảnh khác
  thật sự, không lặp file. Keyword khớp là tốt nhất, không khớp thì dùng từ
  khóa liên quan miễn visual liền mạch (cùng chủ đề AI).
- **Ít card — nhiều footage.** Video cần liền mạch, bắt mắt/bắt tai. Card/quote/
  im lặng **CHỈ khi có chủ đích**: số liệu gây sốc, punchline, reveal, "let it land".
  Mặc định VO chạy trên `[[stock:]]` hoặc `[[broll:]]`, KHÔNG trên card.
- **Card bắt buộc `|src=`** (nguồn hiện góc dưới) — cấm card trang trí không nguồn.
- **2 card liền nhau cách ≥ 15s** — không dồn card.
- **Tỷ lệ mục tiêu**: clip+stock ≥ 75% · card+quote ≤ 15% · black/sfx ≤ 5%.
  `plan` cảnh báo nếu card+quote > 15%.
- **Quote im lặng ≤ 2 lần/video ngắn** (video 10–20 phút mới 3–5 lần). Test 1 phút chỉ giữ 1 quote.
- **SFX tối đa 1–2 điểm/video**, chỉ ở chuyển cảnh lớn. SFX giờ **đè lên cảnh kế tiếp** (không tạo cell màn đen riêng) — audio mix tại thời điểm cắt, timeline video không đổi.
- Black "beat mạnh" gộp luôn SFX hit vào (không tách 2 cell).

## Nguồn theo bản quyền

- **Stock (Pexels/Pixabay/Mixkit)**: royalty-free → dùng dài thoải mái, không giới hạn độ dài.
- **Clip YouTube/bài báo/transcript**: **≤ 15s**, luôn attribution + commentary + reframe (crop/zoom) — fair use. `plan` sẽ cảnh báo nếu clip youtube > 15s.
- Ghi `"type": "youtube"` hoặc `"type": "stock"` trong clip-manifest.

## Tìm nguồn bằng lệnh search

```
python tool/run.py --case videos/<topic> search --q "AI frontier"          # YouTube
python tool/run.py --case videos/<topic> search --q "AI 前沿" --site douyin # Douyin (cần cookie)
```
YouTube search chạy được ngay. Douyin cần `--cookies-from-browser edge`
(tắt trình duyệt trước) hoặc dán URL thủ công. Bilibili không hỗ trợ (IP bị chặn).

## Kiểm tra script (P-check)

- [ ] Mọi claim có clip hoặc reference tương ứng.
- [ ] Không có câu nào ≥ 3 claim đứng chung.
- [ ] Quote đúng nguyên văn nguồn (không sửa lời).
- [ ] Đếm từ tổng: ~170 từ/phút → video dài bao nhiêu phút.
- [ ] Card+quote ≤ 15% thời lượng; mọi card có `|src=`; 2 card cách ≥ 15s.
