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

## Nguồn hình — chọn bằng `anh:` trong queue.yml

| Chế độ | Lấy ở đâu | Cần key | Dùng khi |
|---|---|---|---|
| `bg` | 1 ảnh Wikipedia VN, tĩnh cả video | không | video ngắn, test nhịp |
| `wiki` | Wikimedia Commons, mỗi keyword vài ảnh | không | **ảnh tư liệu thật**: chân dung, bản đồ, hiện vật |
| `photo` | Unsplash → Pexels → Pixabay, ảnh tĩnh → Ken Burns | có | cảnh không khí: núi sương, đèn lồng, lụa, nến |
| `stock` | video Pexels + Pixabay + Coverr | có | b-roll động |
| `mix` | `wiki` + `photo` | có | **mặc định nên dùng cho kênh kể sử** |
| `full` | `wiki` + `photo` + `stock` | có | pool lớn nhất, chạy lâu nhất |

`anh_per` / `anh_photo_per` giờ là **trần** mỗi keyword, không phải định mức: số
file tải = tổng giây các cell dùng keyword / 8s + 1, trừ file đã có ở mọi kho
(`stock.kw_demand`). Trước đây tải cố định 6 × 3 API/keyword → Càn Long 171
keyword ≈ 2000 file, kho 21 GB.

Mọi nguồn ghi vào **một kho chung** `assets/stock/` theo `md5("<kho>|<keyword>|<idx>")`,
nên tải một lần dùng cho mọi video. Năm kho: `pixabay` `pexels` `coverr` (video),
`photo` và `wiki` (ảnh tĩnh → shot Ken Burns 9s). Ảnh wiki cũ từng ghi nhờ kho
`pixabay` (trùng hash với video Pixabay thật) — vẫn đọc được, file mới ghi `wiki`.

### Marker `ent=` — ảnh tư liệu THẬT của nhân vật/địa danh/sự kiện

```
[[stock:"<cảnh không khí tiếng Anh, cụ thể>"|ent="<Tên bài Wikipedia EN / Commons category>"]]
[[wiki:"Qianlong Emperor"]]          ← bí danh: keyword rỗng + ent
[[stock:"misty mountains dawn"]]     ← không ent: như cũ (cảnh không khí)
```

Có `ent` → `wiki_images.fetch_entity` lấy ảnh trong bài Wikipedia EN (+ VI/ZH
qua langlinks), ảnh đại diện Wikidata P18, Commons `Category:` (P373) và
subcategory 1 tầng; lọc icon/logo/cờ/svg/ảnh < 800px; ghi kho `wiki` khoá
`ent:<tên>`. Tranh dọc được đặt giữa trên nền mờ (không cắt mất mặt); thiếu ảnh
thì làm thêm crop thứ hai (cận mặt) của cùng bức. Render ưu tiên file ent
(rel 1.0) hơn keyword của cùng cell (0.85). Không đủ ảnh thì rơi về keyword.
Bước ent chạy kể cả khi `anh:` không có `wiki` (`--ent-only`).

Đo 01/10 trên 20 marker Càn Long: full-text search cũ cho **9/60** ảnh đúng
thực thể (0/12 là Càn Long); `ent` cho 18/20 marker có tư liệu thật (44 shot,
cả 6 shot Càn Long là chân dung/tranh ông), 141s. 2 ent trượt (không có bài/
category: "Literary inquisition", "Southern Inspection Tours...") → keyword.

Circuit breaker (`stock.api_get`): 401/403 → tắt API cả phiên; 429 → đợi
Retry-After/lũy thừa và nhân đôi nhịp; hết quota (`X-Ratelimit-Remaining`=0)
→ tắt. Tải song song có semaphore theo từng API.

### Kho stock nhỏ lại

Tải xong là `shrink_clip`: cắt 18s giữa, 1920×1080 24fps, crf22 trần 5 Mbps,
bỏ tiếng (282 MB → 11,6 MB). Ken Burns encode `veryfast crf22` (ultrafast cũ ra
26–66 MB/9s, giờ ~1,5–5 MB). Trần kho `STOCK_CACHE_GB` (mặc định 6) xoá file
atime cũ nhất; render ghi atime khi chọn file. Thu gọn kho có sẵn:
`python auto	hu_gon_kho.py` (xem trước) / `--that` (trùng → hardlink, thu gọn,
LRU).

### Ảnh stock ĐẸP nhưng hay SAI thời

Pexels/Unsplash không có Tần Thủy Hoàng, Võ Tắc Thiên, Tư Mã Thiên. Chúng luôn
trả về *một cái gì đó*: gõ "Tang dynasty empress portrait" ra đôi cosplay chụp
trước tòa nhà kính; gõ "prison interrogation" ra nhà tù hiện đại áo cam còng tay.
`_rel_score()` trong `tool/stock_photo.py` chặn ba nhóm:

- **dấu hiệu thời nay** (`_MODERN`): cosplay, posing, tourists, handcuffs, car,
  neon, office... → loại thẳng.
- **sai vùng địa lý** (`_REGIONS`): keyword nói Trung Hoa mà ảnh chụp lăng ở
  Azerbaijan / cung điện Hàn Quốc → loại thẳng.
- **không khớp gì**: điểm 0 → bỏ, thà thiếu ảnh còn hơn ảnh sai.

Ngoại lệ `TOP_TRUST = 6`: 6 kết quả đầu của mỗi API được giữ dù không khớp chữ
nào — Unsplash mô tả ảnh rất cộc ("brown and beige concrete building") nên chấm
điểm theo chữ sẽ giết cả ảnh đúng, trong khi chính API đã xếp hạng theo độ liên quan.

Tắt bộ lọc bằng `PHOTO_STRICT=0` (chỉ nên tắt cho kênh không kể sử).

### Video động cũng bị lọc như ảnh (từ 26/09/2026)

Trước đó bộ lọc chỉ có ở `stock_photo.py`. `stock.py` (video) xếp hạng **thuần
theo độ phân giải**, nên một clip cosplay quay 4K luôn được chấm điểm cao nhất
và chắc chắn lên sóng — đó là lý do `queue.yml` phải tắt hẳn `stock` cho video
kể sử, và video Võ Tắc Thiên ra lò với **426 shot toàn ảnh tĩnh, 0 clip động**.

Ba API trước đây vứt hết chữ mô tả đi (`_pixabay_search` chỉ trả `(url, w, h)`).
Giờ chúng giữ lại: Pixabay `tags`, Pexels **slug URL** (API video của Pexels
không có trường mô tả — chữ duy nhất nằm ở slug), Coverr `title`+`description`.
`_rel_filter()` chấm điểm bằng đúng `_rel_score()` của ảnh, chạy **trước**
`_pick_landscape` để còn dùng được thứ hạng do API xếp.

`VIDEO_TOP_TRUST = 4` (ảnh là 6) — mô tả video cộc hơn mô tả ảnh, nhưng một clip
sai thời hại hơn một ảnh sai thời vì nó đóng đầy 8 giây. Tắt bằng `STOCK_STRICT=0`.

Đo thật 26/09 trên Pexels: `"Tang dynasty empress ceremonial robe"` 50 clip →
giữ 30, loại đúng mấy clip `traditional costume` / `fashion display`.
`"misty mountains clouds moving"` 49 → giữ 47 (b-roll không khí gần như không
bị đụng). Nên `anh: full` giờ an toàn cho kênh kể sử.

**Coverr chỉ ăn truy vấn ngắn.** Thư viện nhỏ (~vài nghìn clip): `"clouds"` ra
578 kết quả, `"Tang dynasty empress ceremonial robe"` ra 0. Dùng nó cho mây,
mưa, lửa, khói, lụa — không dùng cho nhân vật/sự kiện.

**Pixabay đang thiếu key** (kiểm tra 01/10) — `tool/.env` có Pexels, Unsplash,
Coverr nhưng không có `PIXABAY_API_KEY`. Thêm vào là mở thêm một kho video free nữa.

**Nguyên tắc chia việc**: nhân vật/sự kiện/hiện vật cụ thể → marker `ent=` (hoặc ảnh AI).
Cảnh không khí, chuyển đoạn, nền cho lời bình → `photo`/`stock`.

### Key stock (tool/.env)

```
PEXELS_API_KEY=      # pexels.com/api — 200 req/giờ, ảnh 6000px + video 4K
COVERR_API_KEY=      # coverr.co/profile/api — demo 50 req/giờ, chỉ phục vụ 1080p
UNSPLASH_ACCESS_KEY= # unsplash.com/oauth/applications — bắt buộc ghi tác giả
PIXABAY_API_KEY=     # pixabay.com/api/docs — ảnh chỉ dùng được fullHDURL
```

Bẫy đã sửa: `.env` mẫu có sẵn dòng `PEXELS_API_KEY=` rỗng; `_load_env()` bản cũ
`setdefault` giá trị rỗng đó rồi key thật ghi ở cuối file không bao giờ được nạp —
nhìn `.env` thấy có key mà tool vẫn báo thiếu.

## Ký tự ngắt nghỉ trong lời đọc (trường `vo`)

Vbee **không** có đường nào điều khiển khoảng lặng từ bên trong — đo thật
2026-09-12 trên `hn_male_manhdung_full_24k-st`:

| Thử | Kết quả |
|---|---|
| `input_type` / `text_type` / `emotion` / `style` / `pitch` / `volume` / `silence_ms` / `break_time` | 400 `"not allowed"` |
| `<break time="1500ms"/>` | audio **dài thêm 3.56s** — máy đọc to tên thẻ, không thành khoảng lặng |
| bọc `<speak>…</speak>` | tệ hơn nữa, +6.1s |
| `speed_rate` | **bão hoà ngoài [0.7, 1.2]** — 0.5/0.6/0.7 đều ra 148–151 âm tiết/phút; 1.2/1.5 đều ra 197 |

Trong vùng dùng được, `speed_rate` còn **phi tuyến**: đo 2026-09-12 trên đoạn 32
âm tiết, tốc độ **lúc đang nói** là `-5%`→280, `-12%`→275 (gần như đứng im),
`-18%`→267, `-25%`→249. Khoảng lặng không bị ảnh hưởng: `khoa_im_lang()` giữ
24,3% ở mọi mức rate.

### Giọng kênh: `hn_male_phuthang_stor_24k-stl` (từ 26/09/2026)

"Anh Khôi nâng cao (Beta)", nam Hà Nội, kiểu kể chuyện, **2 credit/ký tự** —
rẻ hơn `hn_male_manhdung_full_24k-st` (3 credit). Đo 26/09 trên mẫu 35 âm tiết,
tính riêng thời gian **đang nói** (trừ khoảng lặng bằng `silencedetect -40dB`):

| `speed_rate` | `rate` | Phú Thắng | Mạnh Dũng |
|---|---|---|---|
| 1.10 | `+10%` | 379 | |
| 1.00 | `0%` | 297 | |
| 0.90 | `-10%` | 286 | |
| 0.82 | `-18%` | 279 | **241** |
| 0.75 | `-25%` | 276 | **229** |
| 0.70 | `-30%` | 275 | |
| 0.60 | (bị kẹp) | 275 | |

**Phú Thắng bão hoà ở 275 âm tiết/phút** — không tham số nào đưa nó chậm hơn,
và trong khoảng 0.6–0.9 nó gần như trơ với `speed_rate` (lệch 4%). Mạnh Dũng
xuống được 229. Nên **đòn bẩy nhịp của giọng này là `nhip` và `slow_voice`, không
phải `rate`**; `rate` mặc định để `-25%` (0.75) cho sát đáy mà không phí.

### Đừng suy nhịp bằng công thức — chạy thử 5 cell rồi đo

Bảng trên đo trên **một câu chạy dài một mạch**, nên nó chỉ nói được tốc độ phát
âm thuần. Đem nhân với `1 − 0,24 × nhip` để đoán nhịp video là **sai**: `nhip`
chỉ nhân phần khoảng lặng *tool chèn thêm*, còn bản thân giọng đọc tự nó đã nghỉ
rất nhiều theo dấu câu và hơi thở — phần đó `nhip` không đụng tới. Đo 26/09 trên
5 cell đầu script Võ Tắc Thiên (243 âm tiết, pipeline thật, `nhip: 0.15`):

| | Phú Thắng `-25%` | Mạnh Dũng `-18%` |
|---|---|---|
| im lặng thật | 18,1% | 18,3% |
| **tổng âm tiết/phút** | **213** | **220** |
| lúc đang nói | 260 | 269 |

Công thức cho ra 3,6% im lặng và 265 âm tiết/phút — lệch thực tế 24%. Hai giọng
thật ra **gần như cùng nhịp**, và đều sát đích 223 của spec nhân vật.

Mẫu nghe thử: `OUTBOX/test-giong/{phuthang,manhdung}.mp3`.

Nên mọi khoảng lặng do `tool/tts.py` chèn ở hậu kỳ. Người viết điều khiển nhịp
bằng các ký tự đặt thẳng trong `vo` — chúng bị **bóc sạch** trước khi gọi TTS và
trước khi vẽ phụ đề, máy không bao giờ đọc chúng:

| Ký tự | Tác dụng |
|---|---|
| `//` | lặng thêm 0,8s — hết một ý, chưa hết đoạn |
| `///` | lặng thêm 1,5s — chuyển ý |
| `////` | lặng thêm 2,4s — chuyển chương |
| `\|` | ngắt hơi 0,16s — tách cụm giữa câu mà không cần dấu phẩy |
| `^` | hít một hơi nghe thấy ngay trước câu đó |
| `*` | cả câu đọc chậm hơn 8%, nghỉ sau dài gấp 1,4 lần |

### Nhịp được khoá tự động về chuẩn kênh

`khoa_im_lang()` (trong `tool/tts.py`, gọi từ `plan_track`) kéo **tổng** khoảng
lặng của mỗi cell về đúng **24% thời lượng** — tỉ lệ đo được ở kênh đối thủ. Hình
dáng nhịp giữ nguyên: chỗ đang nghỉ lâu vẫn lâu hơn chỗ khác, cả cụm chỉ bị kéo
hoặc giãn cùng một hệ số.

Phải khoá theo **độ dài giọng thật**, không ước theo số chữ. Đo 2026-09-12 trên
Vbee `hn_male_manhdung`: 23 âm tiết ra 5,3s tiếng nói ≈ **260 âm tiết/phút lúc
đang phát âm**. Con số 196 là nhịp **tổng** đã tính cả ngắt nghỉ: 260 × (1−0,24)
= 198. Bản trước ước nhầm 196 là tốc độ phát âm nên cấp gấp đôi lượng nghỉ cần
thiết — video ra 121 wpm, nghe lê thê.

### `slow_voice` — chốt chặn cuối, chạy thật từ 26/09/2026

`khoa_im_lang()` chỉ nắn được **khoảng lặng**; nó không làm giọng đọc chậm lại.
Khi giọng đã bão hoà mà vẫn nhanh hơn đích (đúng trường hợp Phú Thắng), thứ duy
nhất cứu được là kéo dài audio ở hậu kỳ — `tool/slow_voice.py` làm việc đó bằng
`atempo` (giữ nguyên cao độ), rồi **giãn luôn mốc thời gian trong
`cell-<id>.words.json`** nên phụ đề không lệch dần về cuối.

Trước đây `auto/steps.py` gọi nó với `--dry-run` — chỉ in số rồi thôi, vì "skill
nói thường đã đạt". Giờ chạy thật, như một chốt chặn: đo 26/09 thì cả hai giọng
đều đang sát đích nên lệnh này là **no-op**, nhưng để `--dry-run` nghĩa là bất kỳ
lần đổi giọng nào sau này cũng chỉ in ra một dòng cảnh báo rồi vẫn dựng video
sai nhịp.

Tự bỏ qua khi hệ số ≥ 0,995 nên với giọng đã đạt đích đây là lệnh không làm gì.
Ngưỡng an toàn `--min-factor 0.75` chặn kéo quá tay gây méo tiếng. Đo thật 26/09:
đích 223 cần `atempo 0.93`, đích 196 cần `atempo 0.82` — cả hai đều trên ngưỡng.
Bản gốc được cất ở `build/voice/_pretempo/` nên chạy lại được.
Tắt bằng `keo_cham: false` trong `queue.yml`.

Chỉnh lệch khỏi chuẩn bằng field `nhip` trong `queue.yml` (cộng vào **đích**, không
bị vòng khoá xoá mất):

```yaml
  - slug: abc
    nhip: 0.7        # 1.0 = 24% im lặng (chuẩn) | 0.7 → 18% | 1.3 → 29%
```

Hai thứ khác cùng gây lê thê, đã sửa trong `PROSODY_VERSION = 4`:

- `sentence_role` gọi **mọi câu ≤ 8 chữ kết bằng dấu chấm** là `punch` — văn kể
  chuyện toàn câu ngắn nên cả đoạn thành câu chốt. `ha_nhan()` giữ lại câu mạnh
  cuối đoạn, hạ các câu còn lại về `narrate` khi tỉ lệ vượt 40%.
- Độ lệch tốc độ cộng dồn (nền −5%, vai trò −6%, câu cuối −3%, dấu `*` −8% =
  −19%). Giờ chặn tổng ở −6%, và "câu cuối đoạn hạ cánh" chỉ áp khi cell có ≥ 3 câu.

**Dùng thưa tay.** Mỗi `//` là +0,8s thật: rắc dày một đoạn 10 câu đẩy im lặng từ
26% lên 47% và tụt còn 141 âm tiết/phút. Chuẩn kênh là ~24% / ~196 âm tiết/phút;
mặc định không marker hiện cho 26% / 195.

Tiếng **hít hơi** còn được chèn tự động sau mỗi khoảng lặng ≥ 0,75s khi câu tiếp
theo dài ≥ 16 từ (hoặc khoảng lặng ≥ 0,95s). Hơi được **khoét ra từ khoảng lặng
có sẵn** nên không làm video dài thêm và không lệch mốc phụ đề. Tắt bằng
`TTS_BREATH=0` (biến này nằm trong hash cache nên đổi là sinh lại giọng).

### Kiểu `doan` — mặc định từ 01/10/2026 (`PROSODY_VERSION = 5`)

Người dùng nghe video và nhận xét "giọng đọc và tốc độ như AI". Đo A/B trên cùng 3 cell
Càn Long (`OUTBOX/test-giong-2026-10-01/README.md`) thì thấy bốn nguyên nhân:

1. **Gọi TTS từng câu/vế**: 10 lần gọi cho 3 cell, tức 7 chỗ nối. Ở mỗi câu engine lại
   bắt đầu như câu đầu tiên, nên nghe rời rạc.
2. **Lặng giữa câu gần đều nhau**: độ lệch chuẩn chỉ 0,27s, vì `khoa_im_lang` nhân mọi
   khoảng lặng với cùng một hệ số.
3. **Rate/pitch nhảy theo vai trò câu**: pitch Vbee bị dịch bằng rubberband −6/−8Hz giữa
   hai câu liền nhau.
4. **`loudnorm` "linear=true" rơi về chế độ nén động** ở cả 6/6 cell Vbee (+5dB vượt TP):
   LRA còn ~2 và mức ra −17,2 thay vì −16.

Kiểu mới (`doan_render_cell` trong `tool/tts.py`, dùng chung cho edge/vbee/azure):

- Chỉ tách ở `//` `///` `////`, mỗi mảnh đọc **một lần gọi**, dùng một tốc độ cho cả mảnh và không đổi pitch.
  `|` được đổi thành dấu phẩy để engine tự ngắt. `*` làm cả mảnh chậm 5%. `^` vẫn chèn hơi thở như cũ.
- **Giữ khoảng lặng engine tự đặt** (ngắn sau dấu phẩy, dài sau dấu chấm). Muốn đủ 24% thì
  **giãn** các khoảng ≥ 0,14s theo trọng số p^1,5, cộng thêm biến thiên ±10% có hạt giống cố
  định. Khoảng ngắn hơn là chỗ khép âm tắc trong một từ, giãn vào sẽ vỡ từ. Kết quả: độ lệch
  chuẩn lặng tăng từ 0,27 lên 0,47s, số chỗ nối giảm từ 7 xuống 2.
- Mốc từ của Vbee/Azure: nếu số cụm giữa các dấu câu bằng số đoạn đang nói thì gán từng
  cụm vào đoạn tương ứng; nếu không thì chia theo số ký tự trên phần thời gian đang nói.
- Âm lượng: tăng đúng một gain (−16 − I đo được) rồi qua `alimiter`, không nén động
  (`TTS_LOUDNORM=loudnorm` để dùng lại cách cũ).
- Hơi thở tự động chỉ chèn sau khoảng lặng ≥ 1,2s (`///`, `////`) khi câu sau dài ≥ 10 từ.
- Cái giá phải trả: đọc cả đoạn thì Phú Thắng nói ~299 âm tiết/phút (từng câu chỉ ~275), nên
  `slow_voice` phải kéo khoảng 0,88. Vì vậy `slow_voice` đổi sang `rubberband` (giữ formant,
  tự bù 1–2 dB bị hụt), còn `SLOW_VOICE_ENGINE=atempo` để quay về cách cũ. `slow_voice`
  cũng không còn đếm `//` là một âm tiết.

Quay về kiểu cũ: `TTS_MODE=cau`, hoặc `tts_mode: cau` trong một mục của `queue.yml`.
Biến này nằm trong hash cache. **Chưa chốt bằng tai**: người dùng cần nghe A/B/C/E/I
trong `OUTBOX/test-giong-2026-10-01/`.

Azure: các giọng vi-VN **không có** `StyleList`, nên `mstts:express-as` không dùng được.
Có giọng mới `vi-VN-Grant:MAI-Voice-2.1`, đọc được theo kiểu đoạn, nhận `prosody rate`
(yếu hơn: +20% chỉ nhanh ~10%). Tốc độ gốc của nó là 245 âm tiết/phút lúc nói, gần người
thật nhất trong các giọng đã thử. Cấu hình cũ của Võ Tắc Thiên (NamMinh `+25%`) đo được
**345 âm tiết/phút lúc nói, 43% im lặng**: máy đọc gấp rồi ngồi im. Không dùng lại mức
rate đó với kiểu `doan`.

## Dọn ổ đĩa — chỉ giữ đầu vào + video cuối

Xong một video thì **mọi thứ máy tự sinh đều xoá**. `auto/don_dep.py` giữ lại:
`script/`, `references.json`, `clip-manifest.json`, `config.json`, `meta.json`,
`publish.md`, `sources.md`, các file `*-credit(s).json` — tất cả đều cỡ KB, đủ để
đọc lại và dựng lại. Xoá: `assets/` (nhạc, sfx, clip tải về), `build/tmp|shots|
trim|voice`, các file `.mp3/.wav/.sh/.log` trong `build/`.

Video cuối **chỉ giữ một bản**: nếu `OUTBOX\<ngày>-<slug>\video.mp4` đã có bản sao
đúng kích thước thì `build/final/video-1.mp4` bị xoá; chưa có thì giữ nguyên tại chỗ.
Case chưa ra video thì không đụng vào.

```
python auto\don_dep.py            xem trước, không xoá gì
python auto\don_dep.py --that     xoá thật
python auto\don_dep.py --slug X --that
```

Runner tự gọi ở bước `cleanup` cuối mỗi video; `--giu-build` để giữ lại khi cần soi
file trung gian.

## Lưu ý quan trọng (kinh nghiệm vận hành)

- **Thứ tự TTS & render**: chạy `tts` trước khi `render` nếu muốn cell stock dài
  đúng bằng giọng đọc (ngược lại video sẽ đứng hình chờ voice). Nếu render trước
  mà voice chưa có, tool sẽ in WARN — hãy chạy tts rồi render lại.
- **Stock trùng**: nếu `stock-usage` báo trùng content, chạy `stock --prune`
  hoặc để render tự dedup (đã hỗ trợ timeline theo giây).
- **fair use**: kiểm tra `plan` cảnh báo clip > 15s, thu ngắn `in/out` trong manifest.
- **Chống over-engineer**: video 1–3 = test nhịp và giọng. 1 luận điểm + 15–30
  reference + script 8–15 phút là đủ. Không cần intro logo/end screen phức tạp.

## Đo end-to-end 03/10/2026 — Càn Long 28,8 phút, 186 cell

| Bước | 26/09 (code cũ) | 03/10 |
|---|---|---|
| images | 3511s | **21s** (kho đã có, `kw_demand` không tải thừa) |
| tts (Vbee, kiểu `doan`) | 2637s | **981s** |
| render | 3587s | **782s** |
| assemble | chết ở lô 22 | **1725s** |
| tổng | > 2,5 giờ, không ra video | **42,7 phút** |

Hình/tiếng lệch 0,02s trên 1726s, −19,7 LUFS, LRA 2,6.

**Nghẽn đã sửa**: `render_all` dựng pool bằng `cell_pool`/`stock_pool`, hash từng file
TUẦN TỰ (6 lần gọi ffmpeg mỗi file chưa có cache `.h`/`.c`). Sau khi bước ảnh sinh
~300 shot Ken Burns mới, render đứng ở đó với CPU 1%. Giờ `stock.prewarm_sigs()` làm
nóng cache song song (`SIG_JOBS`, mặc định cpu−2, tối đa 12) trước vòng tuần tự →
12 ffmpeg, CPU 90%. Kết quả hash y hệt (cùng hàm, cùng cache).

**Đã thử, KHÔNG áp dụng**: `-threads 2` trước mỗi `-i` của stage1. RAM đỉnh một lô
giảm 3,0 → 2,2 GB nhưng không nhanh hơn (số "76s → 60s" ban đầu là do lần A chạy
lúc đĩa nguội; chạy lại A ra 56,7s), và bản có `-threads 2` có 3 frame vỡ chữ phụ
đề ở chỗ chuyển câu (A với A lặp lại thì không lệch frame nào dưới 40 dB). Stage1
hiện chạy 2 lô song song vì RAM (mỗi lô ~2,6 GB, 225–300 luồng).

## Demo Bạch Đằng 938 (03/10/2026) — bốn lỗi hình/tiếng tìm ra khi làm video sử Việt

Case `videos/demo-bach-dang-938`, 3,7 phút, 20 cell, 12/16 marker có `ent=`. Chạy 4 lần
mới ra bản đúng; mỗi lần lộ một lỗi:

1. **Wikimedia full-text search cho cảnh không khí là rác, và nó chạy TRƯỚC nên
   Pexels không tải nữa.** `anh: full` = wiki → photo → stock, mà `kw_demand` dùng
   chung: wiki lấp "Vietnam river mist dawn wooden boats" bằng thành phố Đà Nẵng ban
   đêm, "fire smoke on water dusk" bằng pháo hoa, rồi photo chỉ còn tải 1 ảnh. Nay
   `step_images`: có photo/stock thì wiki chỉ chạy `--ent-only`.
2. **Ảnh tĩnh lấp hết định mức, video động chỉ còn 3 clip.** photo chạy trước stock.
   Nay stock (video) chạy trước, photo lấp phần thiếu; `anh_uu_tien: anh` để đảo lại.
   Kết quả: 28 clip Pexels + 3 ảnh thay vì 3 clip + 29 ảnh.
3. **Ảnh `ent` lặp 4–5 lần.** `render_stock` vắt kiệt một file theo offset 0/6/12 s —
   với shot Ken Burns 9 s thì vẫn là một bức ảnh; pool cell ent xếp ảnh ent lên đầu nên
   clip động không tới lượt. Nay `stock.is_still()` (phân biệt bằng `_urls.json`), ảnh
   tĩnh góp đúng 1 đoạn/cell, đoạn kế xen clip động, bỏ qua file vừa dùng trong
   `REUSE_COOLDOWN` 150 s.
4. **Logo và ảnh phố lọt vào `ent`.** `Dương Đình Nghệ` lấy 2/3 shot là triện đỏ
   "Lịch sử Việt" (ảnh đầu đề bản mẫu Wikipedia VI); `Ngô Quyền` lấy chợ nổi Cần Thơ
   vì Commons có ảnh Panoramio chụp ở *đường* Ngô Quyền. Thêm vào `_JUNK`:
   `template heading|lichsuvietnam|navbox|banner|panoramio|mapillary|street view`.

### Nền âm thanh — `nhac:` trong queue.yml (từ 03/10/2026)

| `nhac` | Kết quả |
|---|---|
| `ambience` (mặc định) | gió + drone trầm (`tool/ambience_bed.py`); `nhac_lop: gio-trong,song-nuoc` chọn lớp SFX Mixkit, `nhac_drone: Em` |
| `sine` | 3 sóng sine cũ của `music.py` — chỉ để test pipeline |
| `assets/music/x.mp3` | nhạc thật của bạn, lặp cho đủ dài, fade hai đầu |

Càn Long 03/10 ra với `sine` (mặc định cũ) — nghe là tiếng u u của máy. Mọi video thật
phải dùng `ambience` hoặc nhạc thật.

`check_script.py`: console Windows cp1252 làm nó văng `UnicodeEncodeError` khi in lỗi có
dấu — đã `reconfigure(utf-8)` ở `main()`.
