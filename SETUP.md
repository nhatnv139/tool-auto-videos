# SETUP.md — Cài đặt lần đầu (làm 1 lần trên máy bạn)

Bộ kit này là pipeline sản xuất video YouTube commentary. Bạn dùng opencode
(terminal AI) đọc folder này rồi chat để tự làm video. Dưới đây là phần cài đặt.

## 1. Cài công cụ hệ thống

| Tool | Vì sao | Cài |
|---|---|---|
| **ffmpeg / ffprobe** | cắt clip, render, ghép video | `winget install ffmpeg` (hoặc gyan.dev) + thêm PATH |
| **Git for Windows** | git-bash chạy script ffmpeg (render/assemble) | `winget install Git.Git` — mặc định `C:\Program Files\Git\bin\bash.exe` |
| **Python 3.11+** | chạy pipeline | python.org, tick "Add to PATH" |
| **yt-dlp** | tải video YouTube | `pip install yt-dlp` (hoặc binary) |

> Nếu git-bash cài ở chỗ khác: đặt biến môi trường `GIT_BASH` trỏ tới `bash.exe`.

## 2. Cài Python packages

Mở terminal tại folder này (ví dụ `C:\Users\<ban>\ai-frontier-kit`):

```bash
pip install -r requirements.txt
```

## 3. Tạo file key

```bash
copy tool\.env.example tool\.env
```

Mở `tool\.env` và điền key (lấy miễn phí):
- **PIXABAY_API_KEY**: đăng ký pixabay.com → API key (tải stock footage)
- **PEXELS_API_KEY**: đăng ký pexels.com → API key

`edge-tts` (giọng đọc) miễn phí, không cần key. Nếu muốn giọng tự nhiên hơn,
có thể set `ELEVENLABS_API_KEY` (trả phí).

## 4. Cài opencode + DeepSeek

1. Cài opencode (xem https://opencode.ai — CLI terminal).
2. Cấu hình model DeepSeek làm backend:
   ```
   opencode models    # chọn deepseek / hoặc cấu hình qua opencode.json
   ```
   Bạn cần DeepSeek API key (platform.deepseek.com) và đặt:
   ```
   $env:DEEPSEEK_API_KEY="sk-..."
   ```
3. Mở terminal trong folder:
   ```
   cd ai-frontier-kit
   opencode
   ```

## 5. Tải stock footage lần đầu (~17 GB, 1 lần)

Trong opencode, yêu cầu agent chạy:

```bash
python tool/run.py --case videos/<topic> stock --all
```

Sau đó mọi video dùng chung kho này (không tải lại).

## 6. Bắt đầu

Trong opencode, chat bằng tiếng Việt/tiếng Anh:
- "Làm video về <đề tài> cho tôi"
- Agent sẽ research nguồn → viết `clip-manifest.json` + `references.json` +
  `script/script.md` → **gửi bạn duyệt script** → chạy pipeline → ra video.

## Xử lý sự cố

- `ffmpeg: not found` → chưa thêm PATH, hoặc mở terminal mới.
- `bash.exe` không thấy → đặt `GIT_BASH` (xem mục 1).
- `fetch` báo video không tải được → URL x.com/facebook bỏ qua là bình thường.
- `stock --all` chậm → đúng, tải hàng trăm file; chỉ chạy 1 lần.
- Cần align câu tự động → cài `yt-script` và set `YT_SCRIPT_PATH`
  (xem `docs/02-research.md`). Nếu không, để `align:false` trong manifest.
