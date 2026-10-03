---
name: su-hoc
description: Mổ xẻ kênh lịch sử đối thủ trên YouTube bằng đo đạc thật — tự tải video, bóc script bằng whisper, đo decibel/loudness/ngắt nghỉ/tốc độ giọng, đối chiếu lời đọc với hình, soi kỹ 5 giây và 30 giây đầu — rồi xuất ra spec giọng + spec hình để áp cho kênh mình. Dùng khi người dùng đưa link kênh/video đối thủ và muốn biết "nó đọc thế nào, hình chạy thế nào, sao giữ chân được người xem", hoặc muốn chấm video của mình so với đối thủ.
---

# su-hoc — đo đạc kênh sử đối thủ

Nguyên tắc: **không nghe rồi phán, phải đo.** Mọi nhận định về giọng đọc phải
kèm con số lấy từ file. Cảm nhận ("giọng cuốn", "nhạc hợp") không được ghi vào
kết luận nếu không có chỉ số đỡ lưng.

Script đo: `scripts/analyze_voice.py` (cùng thư mục skill này).
Cần sẵn: `yt-dlp`, `ffmpeg`, `ffprobe`, `faster-whisper`, `numpy`.

Skill này **nằm trong repo** `D:\dev\ai-frontier-kit\.claude\skills\su-hoc\` để đi
theo git. `~/.claude/skills/su-hoc` chỉ là junction trỏ về đó, nên sửa ở đường dẫn
nào cũng là sửa cùng một file. Sửa xong nhớ commit trong repo ai-frontier-kit.

## Quy trình

### Bước 1 — Nhận link, chọn video để đo

Người dùng đưa **link kênh** thì lấy 3–5 video nhiều view nhất trong 3 tháng gần
đây (video mới phản ánh format hiện tại, video cũ có thể là format đã bỏ):

```bash
yt-dlp --flat-playlist --print "%(view_count)s\t%(duration)s\t%(id)s\t%(title)s" \
  "https://www.youtube.com/@<kenh>/videos" | sort -rn | head -20
```

Người dùng đưa **link 1 video** thì đo luôn video đó.

Đo ít nhất 2–3 video rồi lấy median trước khi gọi là "chuẩn của kênh". Một video
có thể là ngoại lệ.

### Bước 2 — Chạy đo

```bash
python D:/dev/ai-frontier-kit/.claude/skills/su-hoc/scripts/analyze_voice.py "<URL>" \
  --out "$TEMP/suhoc/<video_id>" --model small
```

Tự làm hết: tải audio wav + video 480p → bóc script có timestamp từng từ →
ffmpeg `loudnorm` (EBU R128) → đường bao dBFS mỗi 20ms → tách giọng/nhạc/khoảng
lặng bằng ngưỡng thích nghi → dò cắt cảnh → cắt sẵn frame ở mỗi điểm đổi hình
trong 60 giây đầu.

Sinh ra: `report.md` (bảng cho người đọc), `voice.json` (số liệu đầy đủ),
`transcript.json` (script + timestamp), `frames/` (ảnh để đối chiếu).

Video 10 phút mất ~3–5 phút (whisper CPU là phần chậm). **Chạy nền**, đừng ngồi
chờ. `--model medium` chính xác hơn nhưng chậm gấp 3 — chỉ dùng khi cần trích
câu nguyên văn.

### Bước 3 — Đọc script bằng mắt, đối chiếu với hình

Đây là phần máy không làm thay được. Mở `transcript.json` + `frames/` rồi tự
xem từng cặp (lời đang đọc ↔ hình đang chiếu) trong 60 giây đầu, trả lời:

- Hình minh họa **đúng danh từ đang đọc**, hay chỉ là hình chung chung lấp chỗ?
- Hình đổi khi **ý đổi** hay đổi máy móc theo đồng hồ?
- Có phụ đề cháy trên hình không? Có chữ/tiêu đề chạy không? Logo ở đâu?
- Ảnh cùng một phong cách hay trộn nhiều nguồn (tranh, ảnh phim, AI)?
- Khung hình: tràn viền hay ảnh nhỏ đặt trên nền trang trí?

Muốn xem thêm mốc giữa video:
```bash
ffmpeg -y -ss <giây> -i video.mp4 -frames:v 1 -vf scale=640:-1 mid_<giây>.jpg
```

### Bước 4 — Soi 5 giây và 30 giây đầu (bắt buộc, không được bỏ)

Đây là chỗ quyết định retention, phải tách riêng chứ không lẫn vào trung bình
cả video. Trong `voice.json` khối `mo_dau` đã có sẵn. Cần trả lời đủ 8 câu:

1. Từ đầu tiên vang lên ở giây thứ mấy? (`moc_vao_loi_s` — tốt là ≤ 1,0s)
2. Có nhạc dạo / logo / lời chào trước khi vào nội dung không?
3. 5 giây đầu **to hơn hay nhỏ hơn** phần còn lại bao nhiêu LU?
   (so `loudness_5s.I` với `loudness.I`)
4. Nhạc nền ở hook bị kéo xuống bao nhiêu dB so với thân bài?
   (so `mo_dau.5s.db_khi_im` với `nhac_nen.db_median_trong_pause`)
5. 5 giây đầu đọc bao nhiêu âm tiết, nhanh hay chậm hơn trung bình?
6. Có cắt hình trong 5 giây đầu không? Hình đầu tiên đổi ở giây thứ mấy?
7. 30 giây đầu nói xong bao nhiêu ý, câu bản lề ("Thế nhưng...") rơi vào giây nào?
8. Khoảng lặng dài nhất trong 60 giây đầu ở đâu — đó là điểm cắt hook/thân.

### Bước 5 — Xuất spec, không xuất cảm nhận

Kết quả giao cho người dùng gồm 3 thứ:
- **Bảng số đo** (copy từ `report.md`, thêm cột "áp cho mình bao nhiêu").
- **Spec giọng**: tốc độ âm tiết/phút, loudness thân bài, loudness hook, chênh
  giọng–nhạc, độ dài câu, khe giữa câu.
- **Spec hình**: giây/hình, cắt/phút, nhịp 30s đầu, phụ đề bật/tắt, kiểu ảnh.

Lưu bài phân tích vào `D:\dev\content\phan-tich-giong-doc-<ten-kenh>.md`.

## Ngưỡng đọc kết quả

| Chỉ số | Đọc thế nào |
|---|---|
| `loudness.I` | −14 = chuẩn YouTube; −17 = kênh cố tình để dày. Dưới −20 là mỏng |
| `loudness.LRA` | ≤ 4 LU = nén mạnh, giọng đều (kiểu kênh kể chuyện). > 8 = chưa nén |
| `loudness.TP` | > −1,0 dBTP là đang ép trần, có méo. Đừng bắt chước |
| `chenh_voice_tru_nhac_dB` | < 10 dB = nhạc lấn giọng; 12–15 dB = chuẩn voice-first |
| `am_tiet_phut_gop` | 190–200 = trầm ngâm; 220–240 = kể nhanh, giữ nhịp; > 260 = hụt hơi |
| `am_tiet_phut_khi_noi` | Trừ hết ngắt. Chênh nhiều với gộp = ngắt dày (nhấn nhá tốt) |
| `pause_moi_phut` | ~20 lần/phút là nhịp người thật. < 10 = giọng máy đọc liền tù tì |
| `ngat_nghi.median_s` | 0,3s = lấy hơi trong câu; khe giữa câu tính riêng từ transcript |
| `ti_le_im_lang` | 18–25% là bình thường. > 35% là video lê thê |
| `giu_hinh_median_s` | 8–12s cho kênh sử; < 5s là kiểu tin tức/reels |
| `theo_phut` (cột dB giọng) | Dao động > 4 dB giữa các phút = thu nhiều buổi, chưa nén đều |

Bẫy hay gặp: đoạn nào nhạc nền nổi to bất thường sẽ bị ngưỡng thích nghi tính
nhầm là "đang nói" → phút đó báo im lặng ~2% và rất ít ngắt. Thấy một phút lệch
hẳn khỏi các phút khác thì nghe lại đoạn đó trước khi kết luận.

## Chuẩn tham chiếu đã đo — BLV Hải Thanh History

Video `oWPAVAdWTGI` (9:05, 61,7k view). Chi tiết đầy đủ ở
`D:\dev\content\phan-tich-giong-doc-blv-hai-thanh.md`.

| Chỉ số | Số đo |
|---|---|
| Integrated / LRA / TP | −17,36 LUFS / 3,4 LU / +0,07 dBTP |
| dB giọng / dB nhạc / chênh | −23,4 / −36,8 / **13,4 dB** |
| Tốc độ gộp / lúc phát âm | **225,7** / 283 âm tiết/phút |
| Ngắt | 22,3 lần/phút, median 0,30s, dài nhất 2,26s |
| Im lặng | 20,3% |
| Câu | median 17 âm tiết, 4,2s; khe giữa câu 0,50s; chỉ 7/113 khe > 1s |
| Hình | 5,6 cắt/phút, giữ hình median 9,3s |
| **Vào lời** | **giây 0,94** — không nhạc dạo, không logo, không chào |
| **5s đầu** | **−15,25 LUFS (+2,1 LU)**, giọng +2,6 dB, nhạc −4,6 dB, **0 cắt hình** |
| **30s đầu** | **240 âm tiết/phút (+6%)**, cắt hình đúng 8,0s/16,0s/24,0s |
| Bản lề hook→thân | ngắt 1,7s ở giây 37,98 |

Ba điều rút ra đáng chép:
1. **Hook được mix riêng**: giọng đẩy lên, nhạc dìm xuống, chênh ~20 dB thay vì
   13,4 dB. Người xem vừa bấm vào là nghe giọng người rất gần.
2. **Không cắt hình trong 5 giây đầu**, sau đó cắt đúng nhịp 8 giây.
3. **Nhanh đều, không xuống sức**: dB giọng dao động trong 2,8 dB suốt 9 phút,
   tốc độ giữ 195–246 âm tiết/phút.

## Chấm video của mình

Script chạy được với file local, nên chấm bản dựng của mình bằng đúng thước đo:

```bash
python D:/dev/ai-frontier-kit/.claude/skills/su-hoc/scripts/analyze_voice.py \
  "D:/dev/ai-frontier-kit/videos/<topic>/build/final/video-1.mp4" \
  --out "$TEMP/suhoc/minh" --no-transcribe
```

(`--no-transcribe` khi đã có sẵn script gốc — nhanh hơn nhiều; nhưng bỏ nó đi
thì mất cột tốc độ âm tiết, nên thường vẫn nên bóc.)

Rồi đặt hai bảng cạnh nhau, sửa theo thứ tự ưu tiên: **loudness hook → nhịp hình
30s đầu → tốc độ đọc → chênh giọng/nhạc**. Ba cái đầu ăn thẳng vào retention.

Cách sửa trong `ai-frontier-kit`:
- Loudness: `tool/assemble.py` stage 4 đang chuẩn hóa cả video về một mức — muốn
  hook to hơn thì gain riêng đoạn 0–5s trước khi ghép.
- Nhịp hình: khóa cứng độ dài cell mở đầu trong `script/script.md`, đừng để
  render tự kéo theo độ dài VO.
- Tốc độ: đổi `--wpm` khi chạy `tts`; tiếng Việt đếm **âm tiết**, một âm tiết là
  một "từ" cách nhau bằng khoảng trắng.

## Giới hạn phải nói rõ khi báo cáo

- whisper `small` sai tên riêng và số (sai số âm tiết ~±3%). Trích nguyên văn
  thì phải chạy `medium` hoặc nghe lại.
- Số đo từ 1 video không đại diện cho cả kênh.
- Tất cả chỉ số đều là **cách kênh đó làm**, không phải cách duy nhất đúng.
  Chép nhịp và mix, đừng chép luôn cả lỗi (ví dụ TP chạm 0 dBTP).
