# 04-production.md — Quy trình dựng + fair use

## Luồng dựng

```
script2config → fetch → render → tts → music → plan → assemble → sources
```

### 1. script2config
`python tool/run.py --case videos/<topic> script2config`
Đọc `script/script.md`, sinh `config.json`. Chạy lại mỗi lần đổi script.

### 2. fetch
`python tool/run.py --case videos/<topic> fetch`
Tải video nguồn (yt-dlp) + cắt đúng [in,out] (ffmpeg) → `assets/clips/clip-<id>.mp4`.
Cache theo video id → chỉ tải 1 lần/1 video. `--force` để tải lại.

### 2b. stock
`python tool/run.py --case videos/<topic> stock`
Tải stock footage (Pixabay/Pexels) cho các cell `[[stock:"keyword"]]` →
`assets/stock/`. Key trong `tool/.env`. Không có key/tìm thấy → render fallback card.

### 3. render
`python tool/run.py --case videos/<topic> render`
Sinh `build/shots/cell-<id>.mp4`. ffmpeg filter phức tạp được emit `.sh` chạy
qua git-bash (`C:\Program Files\Git\bin\bash.exe`) + retry — máy này segfault
khi subprocess spawn filter phức tạp.

### 4. tts (VO)
- `--provider edge` — Microsoft neural, miễn phí, test nhịp.
- `--provider elevenlabs` — giọng thật, cần `ELEVENLABS_API_KEY`.
- Chỉnh tốc độ: `--rate +8%` nếu edge đọc chậm.

### 5. music
`python tool/run.py --case videos/<topic> music --dur <giây>`
Sinh bed placeholder. **Trước khi đăng: thay bằng nhạc Epidemic Sound** để
tránh Content ID. Ducking tự động: nhạc hạ khi có tiếng nói; cell
`music=out/drop` → nhạc cắt hẳn (beat).

### 6. plan
`python tool/run.py --case videos/<topic> plan`
In timeline: cell, start, dur, loại, VO/clip. Kiểm tra nhịp trước khi assemble.

### 7. assemble
`python tool/run.py --case videos/<topic> assemble`
4 stage: trim+burn caption → concat → mix audio (VO + clip duck theo VO + nhạc
duck) → mux. Đầu ra `build/final/video-1.mp4`.

- **Windows Media Player fix**: concat re-encode với `-g {2*fps}` (GOP 2s) +
  `-bf 0` (không B-frame). WMP (codec cũ) fail 0x80004005 khi seek vào giữa
  GOP dài. Nhược điểm: file lớn hơn ~5–10%.
- **Decode check**: sau mux, tool tự decode toàn bộ file, báo lỗi nếu có.

Nếu ffmpeg lỗi: `--emit-only` rồi chạy tay từng `source build/run_stage*.sh`.

### 8. sources
`python tool/run.py --case videos/<topic> sources`
Sinh `build/sources.md` (clip + reference) → dán vào mô tả video, đúng phong
cách AI Frontier.

## Kiểm tra trước khi đăng

- [ ] Xem video: clip nào có tiếng gốc quá nhỏ/lớn → chỉnh `clip_vol`.
- [ ] Caption đọc nhanh/chậm → chỉnh `--rate` hoặc tách câu.
- [ ] Nhạc thật thay placeholder.
- [ ] File nguồn dán vào mô tả.
- [ ] Attribution hiển thị đúng trên mọi clip.

## Fair use (rủi ro pháp lý — tự quyết định)

- **Stock footage (Pexels/Pixabay/Mixkit)**: royalty-free, dùng dài thoải mái — không nằm trong rủi ro này.
- **Clip YouTube/bài báo/transcript**: phải tuân thủ fair use:
  - Clip ngắn **≤ 15s**, commentary/narration chen vào, attribution trên hình.
  - **Reframe** (crop/zoom/flip) để đổi video fingerprint — nhưng **audio vẫn match** (không đảm bảo tránh claim 100%).
  - Không tải lên nguyên vẹn clip dài của người khác.
- Chủ bản quyền vẫn có thể claim; video càng nhỏ càng ít rủi ro.
- Reference để nguyên URL gốc, không tự nhận là tác giả.
- SFX Mixkit: miễn phí thương mại, không cần attribution (kiểm tra license trang web).

## Xử lý lỗi thường gặp

| Lỗi | Xử lý |
|---|---|
| `thieu shot cell N` | chạy `render` trước |
| `thieu VO cell N` | chạy `tts` trước |
| ffmpeg segfault ở assemble | `--emit-only` + chạy tay từng stage |
| clip x.com không tải | bỏ qua, warning, dùng ảnh/quote thay |
| edge-tts lỗi DNS | gỡ aiodns (aiohttp dùng ThreadedResolver) |
| YouTube chặn yt-dlp | chạy `fetch` lại (retry), hoặc thêm cookies |
