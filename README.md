# AI Video Production Kit

Bộ pipeline sản xuất video YouTube commentary/analysis: cắt ghép clip chuyên gia
+ số liệu từ bài báo/paper, narration châm biếm, một luận điểm xuyên suốt.

Hoạt động cùng **opencode** (terminal AI): bạn mở terminal, chat yêu cầu làm video
về một đề tài — agent nghiên cứu nguồn, viết script, dựng video ra `build/final/`.

## Bắt đầu nhanh

1. Đọc `SETUP.md` — cài đặt 1 lần (ffmpeg, Git, Python, packages, API keys, opencode + DeepSeek).
2. Mở terminal trong folder này:
   ```
   opencode
   ```
3. Chat: *"Làm video về <đề tài> cho tôi"*.

Agent sẽ: research nguồn → ghi `videos/<topic>/clip-manifest.json` +
`references.json` + `script/script.md` → **gửi bạn duyệt script** → chạy
`script2config → fetch → stock → render → tts → music → plan → assemble → sources`.

## Công thức 1 video (rút gọn)

1. **1 luận điểm** xuyên suốt → bằng chứng tăng dần → twist → kết.
2. **Nguồn = 2 loại tách bạch**: clip (YouTube + in/out) và reference (paper/bài báo).
3. **Script** là nguồn sự thật duy nhất: dòng VO + marker hình.
4. **Pipeline** tự dựng: script → config → tải/cắt clip → render shot → VO →
   nhạc → ghép → file nguồn công khai.

## Cấu trúc

```
├── CLAUDE.md            ← hướng dẫn agent làm video (đọc khi mở opencode)
├── SETUP.md             ← cài đặt 1 lần
├── requirements.txt
├── docs/                ← 01-format, 02-research, 03-script, 04-production
├── samples/             ← 2 source list mẫu (tham khảo cách gom nguồn)
├── tool/                ← pipeline (run.py + module)
└── videos/<topic>/      ← mỗi video 1 thư mục (manifest, references, script, build)
```

## Pipeline CLI

```bash
python tool/run.py --case videos/<topic> script2config   # script.md -> config.json
python tool/run.py --case videos/<topic> fetch           # tải + cắt clip
python tool/run.py --case videos/<topic> stock --all     # tải stock lần đầu (~17GB)
python tool/run.py --case videos/<topic> render          # build/shots/cell-*.mp4
python tool/run.py --case videos/<topic> tts --provider edge   # VO (free)
python tool/run.py --case videos/<topic> music --dur 480        # nhạc nền
python tool/run.py --case videos/<topic> plan            # xem timeline
python tool/run.py --case videos/<topic> assemble        # ghép ra build/final/
python tool/run.py --case videos/<topic> sources         # file nguồn công khai
python tool/run.py --case videos/<topic> search --q "..."  # tìm clip YouTube
```

## Quy tắc

- **AI không phải nguồn.** Mọi claim phải trỏ về clip (URL+time) hoặc reference.
- **Quote clip ≤ 15s**, luôn attribution. Không bịa số liệu.
- **Script duyệt trước khi dựng.**
- Chi tiết: `docs/01-format.md` · `docs/02-research.md` · `docs/03-script.md` · `docs/04-production.md`.
