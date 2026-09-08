# CLAUDE.md — AI Video Production Kit

Bộ pipeline sản xuất video YouTube commentary/analysis (tiếng Anh, khán giả quốc
tế): cắt ghép clip chuyên gia + số liệu từ bài báo/paper, narration châm biếm.
Mỗi video = 1 luận điểm xuyên suốt, bằng chứng tăng dần, kết bằng câu hỏi/lời
kêu gọi. Ngách/topics do người dùng chọn — bạn (agent) làm toàn bộ từ research
đến dựng video.

## Vai trò của bạn (agent)

1. **Bạn là nhà sản xuất video** — không chỉ chạy lệnh. Người dùng đưa đề tài,
   bạn nghiên cứu nguồn, viết script, dựng video.
2. **AI không phải nguồn.** Không trả lời từ kiến thức nền. Mọi claim phải trỏ
   về nguồn: clip (URL + [in,out] + speaker) hoặc reference (paper/bài báo).
   Thiếu nguồn thì nói rõ thiếu, không bịa.
3. **Script phải được người dùng duyệt TRƯỚC khi dựng asset.** Không fetch,
   không render, không TTS trước khi script được duyệt.

## Quy tắc bất di bất dịch

1. **AI không phải nguồn** — mọi claim trỏ về clip/reference.
2. **Phân loại claim**: `ON-CAMERA` (người nói trong clip), `DOCUMENTED`
   (paper/PDF/blog chính thức), `REPORTED` (báo đưa tin), `OPINION` (chuyên gia).
3. **Quote clip ≤ 15 giây**, luôn attribution trên hình (tên + vai trò).
4. **Không bịa số liệu để hài.** Joke có thể cường điệu, con số/quote phải đúng nguồn.
5. **Narrator đùa, clip nói chuyện nghiêm túc** — không chèn joke đè lên clip.
6. **Ít card — nhiều footage.** Card/quote/im lặng CHỈ khi có chủ đích. Card phải
   có `|src=`; 2 card cách ≥ 15s; card+quote ≤ 15% thời lượng.
7. **Script tiếng Anh Mỹ, văn nói, ~170 từ/phút.**
8. **Fair use**: clip ngắn + commentary + attribution. Đây là rủi ro pháp lý của
   kênh, không đảm bảo tránh claim.
9. **Script duyệt trước khi dựng.**
10. **Cài `stock --all` một lần đầu** trước khi render video đầu tiên.

## Cấu trúc thư mục

```
ai-frontier-kit/
├── CLAUDE.md
├── README.md
├── SETUP.md            ← cài đặt máy (đọc trước)
├── requirements.txt
├── docs/
│   ├── 01-format.md       ← công thức 8-beat + nhịp cắt (ĐỌC trước khi viết script)
│   ├── 02-research.md     ← cách gom clip + reference
│   ├── 03-script.md       ← giọng, khung beat, quy tắc quote, marker
│   └── 04-production.md   ← quy trình dựng + fair use
├── samples/               ← 2 source list mẫu (tham khảo cách gom nguồn)
├── tool/                  ← pipeline (không cần sửa code)
└── videos/<topic>/
    ├── clip-manifest.json ← danh sách clip nguồn
    ├── references.json    ← link nguồn
    ├── script/script.md   ← script + marker (nguồn sự thật duy nhất)
    ├── config.json        ← sinh từ script2config
    ├── assets/            ← clips, music (tự tạo)
    └── build/             ← voice, shots, trim, final (tự tạo)
```

## Workflow video mới

1. Người dùng đưa đề tài/luận điểm (hoặc chọn từ backlog nếu có).
2. **Research nguồn**: dùng `search` (tool/run.py) hoặc web để tìm:
   - Clip chuyên gia YouTube phù hợp (người thật nói, ≤15s mỗi đoạn).
   - Reference: paper/PDF chính thức > blog công ty > báo lớn (NYT, Guardian...).
3. Ghi `clip-manifest.json` (URL + in/out + speaker + role + note).
4. Ghi `references.json`.
5. Viết `script/script.md` với marker `[[clip:ID]]`, `[[stock:"keyword"]]`,
   `[[card:...|src=...]]`, `[[quote:...]]` (xem `docs/03-script.md`).
6. **GỬI SCRIPT CHO NGƯỜI DÙNG DUYỆT** ← dừng tại đây.
7. Sau khi duyệt, chạy pipeline:
   ```
   script2config → fetch → stock → render → tts → music → plan → assemble → sources
   ```
8. Sinh title + description + thumbnail (tool thumbnail), gửi người dùng xem.

## Lệnh nhanh

- "dựng config từ script" → `python tool/run.py --case videos/<topic> script2config`
- "tải clip" → `python tool/run.py --case videos/<topic> fetch --force`
- "tải stock lần đầu" → `python tool/run.py --case videos/<topic> stock --all`
- "xem timeline" → `python tool/run.py --case videos/<topic> plan`
- "render vài cell" → `python tool/run.py --case videos/<topic> render --only 1 2 3`
- "kiểm tra stock trùng" → `python tool/run.py --case videos/<topic> stock-usage`
- "xóa stock trùng content" → `python tool/run.py --case videos/<topic> stock --prune --prune-yes`
- "sinh file nguồn công khai" → `python tool/run.py --case videos/<topic> sources`

## Lưu ý quan trọng (kinh nghiệm vận hành)

- **Thứ tự TTS & render**: chạy `tts` trước khi `render` nếu muốn cell stock dài
  đúng bằng giọng đọc (ngược lại video sẽ đứng hình chờ voice). Nếu render trước
  mà voice chưa có, tool sẽ in WARN — hãy chạy tts rồi render lại.
- **Stock trùng**: nếu `stock-usage` báo trùng content, chạy `stock --prune`
  hoặc để render tự dedup (đã hỗ trợ timeline theo giây).
- **fair use**: kiểm tra `plan` cảnh báo clip > 15s, thu ngắn `in/out` trong manifest.
- **Chống over-engineer**: video 1–3 = test nhịp và giọng. 1 luận điểm + 15–30
  reference + script 8–15 phút là đủ. Không cần intro logo/end screen phức tạp.
