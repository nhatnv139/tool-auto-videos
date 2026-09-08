# 02-research.md — Cách gom clip + reference

## Nguồn clip (Mode A — manual manifest)

Ghi thẳng `videos/<topic>/clip-manifest.json`:

```json
[
  {"id": 1, "url": "https://youtu.be/PZqDFs2sbiY", "in": 7594, "out": 7606,
   "speaker": "Yoshua Bengio", "role": "Turing Award winner", "note": "hook"},
  {"id": 2, "url": "https://youtu.be/Yl5DWYNDxpg", "in": "38.28", "out": "38.34",
   "speaker": "..."}
]
```

- `in`/`out` hỗ trợ: giây (`7594`), `mm.ss` (`38.28`), `mm:ss` (`3:29`),
  `hh:mm:ss`, hoặc tham số `t=` trong URL.
- `out` có thể bỏ → mặc định `in + 6s`.
- URL x.com/facebook/instagram → tool bỏ qua với warning (không tải được).

## Tìm timestamp tự động (Mode B — tùy chọn)

Cần `yt-script` (project riêng, chạy local bằng IP nhà) để tự tìm vị trí câu
quote trong video nguồn rồi suy timestamp. Nếu chưa cài, có thể:
- dùng `search` (tool/run.py) tìm video + ghi `in/out` tay theo transcript YouTube
  (xem trực tiếp trên trang video), hoặc
- cài yt-script rồi set `YT_SCRIPT_PATH` trong `tool/.env`.

Cách tìm tay (không cần yt-script): mở video trên YouTube → bật transcript →
tìm câu nói → lấy timestamp → ghi vào `clip-manifest.json`.

## Nguồn reference

`references.json`:
```json
[
  {"url": "https://arxiv.org/abs/2603.25326", "note": "DeepMind 10K people manipulation"},
  "https://www.anthropic.com/research/agentic-misalignment"
]
```
Ưu tiên nguồn gốc: paper/PDF chính thức > blog công ty > báo lớn (NYT, Guardian,
Fortune, BBC). Ghi cả URL gốc để kiểm chứng.

## Tự bắt đầu câu khi cắt clip (align)

`fetch` mặc định tự dịch timestamp `in` của clip về **đầu câu** dựa trên
transcript video nguồn (gọi yt-script, cache trong `build/transcript/`).
Tránh lỗi "And keep in mind that..." (cắt giữa câu). Tắt cho 1 clip bằng
`"align": false` trong clip-manifest.

Giới hạn: transcript tự động (ASR) không có dấu câu chuẩn → "đầu câu" thực
chất là đầu mảnh transcript (2–6s). Với video có phụ đề tay thì chính xác hơn.

## Nguồn Trung Quốc (Bilibili, Douyin)

`fetch` hỗ trợ thêm Bilibili (`BVxxxx`) và thử Douyin — yt-dlp xử lý, tải về
như YouTube. `manifest` tự nhận diện `type: youtube|bilibili|douyin`.

- **Bilibili**: hoạt động tốt với yt-dlp. URL dạng `https://www.bilibili.com/video/BVxxxxxx/`.
- **Douyin**: yt-dlp hay bị chặn — thử, lỗi thì tải tay.
- **Tìm kiếm tiếng Trung** (kết quả tốt hơn): trên Bilibili dùng keyword như
  "AI 前沿" (AI frontier), "人工智能 前沿" (trí tuệ nhân tạo tiên phong),
  "大模型 风险" (rủi ro mô hình lớn). Dán URL `/video/BV...` vào clip-manifest.
- **Align câu**: nguồn không phải YouTube → tool tự gỡ băng bằng faster-whisper
  từ `build/raw/<vid>.mp4`. Phụ đề TQ kém chính xác hơn phụ đề YouTube; câu nói
  tiếng Trung cần dịch trước khi dùng.
- **Fair use**: áp dụng như các nguồn khác (clip ngắn + attribution).

## Nguồn stock footage (thay card cho VO thường)

Stock dùng **chung toàn project** trong `assets/stock/` (tải 1 lần, mọi video
dùng). Lệnh tải toàn bộ ~500 files:

```
python tool/run.py --case videos/<topic> stock --all   # tải hết theme (1 lần)
```

- **Keyword AI đúng chủ đề** (không dùng camera/circuit/server kỹ thuật chung):
  `STOCK_THEMES` trong `tool/stock.py` — 7 theme AI: robot, abstract, digital
  human, neural, futuristic, data viz, HUD.
- **Keyword liên quan cùng theme**: 1 keyword ít variant → tự mở rộng sang
  keyword cùng theme (vd "AI robot humanoid" → pool chung với "cyborg AI"...).
- **Dedup nội dung**: loại video Pixabay trả trùng (hash frame đầu).
- Mỗi cell dài tự cắt thành đoạn 4s, mỗi đoạn 1 file khác nhau — không lặp.
- Key để trong `tool/.env`: `PIXABAY_API_KEY`, `PEXELS_API_KEY` (Pexels có thể
  403 trên IP này — chỉ Pixabay vẫn đủ).

## Checklist trước khi viết script

- [ ] Luận điểm 1 câu, viết được trong 10 từ.
- [ ] ≥ 20 clip, mỗi beat chính có ít nhất 1 clip chuyên gia.
- [ ] Mọi con số trong script có reference.
- [ ] Câu quote dài nhất ≤ 15 giây nói.
- [ ] Attribution (tên + vai trò) rõ cho từng clip.
