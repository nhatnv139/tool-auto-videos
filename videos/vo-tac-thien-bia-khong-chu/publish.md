# publish.md — Võ Tắc Thiên, tấm bia không chữ

## Tiêu đề (3 phương án)

**Khuyến nghị:** `Người Đàn Bà Duy Nhất Ngồi Lên Ngai Vàng Trung Hoa` (49 ký tự)

Hai phương án còn lại:

- `Võ Tắc Thiên: Tấm Bia Để Trắng Và Lý Do Đằng Sau` (48 ký tự)
- `Vì Sao Võ Tắc Thiên Không Cho Khắc Một Chữ Lên Bia Mình?` (56 ký tự)

Phương án 1 đặt điểm độc nhất lên trước và không cần người xem biết trước tên
nhân vật. Phương án 2 hợp hơn nếu kênh đã có lượng người xem quen đề tài Trung
Hoa. Phương án 3 là câu hỏi nên nhấp cao hơn nhưng giữ chân kém hơn, đúng lý do
mà skill bỏ câu hỏi tu từ ra khỏi hook.

## Mô tả

Suốt 1300 năm, sử sách do đàn ông viết đã dựng Võ Tắc Thiên thành con ngáo ộp
của đạo Nho: tàn nhẫn, dâm loạn, giết con ruột để đoạt ngôi hoàng hậu. Nhưng tàn
nhẫn là thứ rẻ tiền nhất trong cung đình Trung Hoa, và người tàn nhẫn thì thời
nào cũng có hàng trăm.

Thứ đưa bà đi hết quãng đường từ một tài nhân bậc 5 bị bỏ quên 12 năm đến chiếc
ngai vàng không phải là sự tàn nhẫn. Đó là chữ. Bà giành cây bút phê tấu trước
khi giành cái ngai. Lên ngôi rồi thì bà đổi tên toàn bộ quan chế, chế ra khoảng
18 chữ Hán mới cho riêng mình, đổi 14 niên hiệu trong 15 năm, và kiểm soát từng
dòng mà người đời được phép viết về bà.

Để rồi khi chết, bà dựng một tấm bia cao 7,5 mét, nặng gần 99 tấn, và không cho
khắc lên đó một chữ nào.

Video này kể lại 82 năm cuộc đời bà theo đúng trình tự thời gian, từ đêm sinh
bên sông Gia Lăng năm 624 đến cuộc chính biến Thần Long năm 705. Có hai chỗ
video cố ý không kết luận: cái chết của đứa con gái sơ sinh năm 654 và cái chết
của thái tử Lý Hoằng năm 675. Cựu Đường thư soạn năm 945 và Tân Đường thư soạn
năm 1060 chép hai thủ phạm khác nhau cho cùng một sự việc, và khoảng cách 115
năm giữa hai bộ sử ấy chính là câu chuyện.

Cũng có chỗ video không bênh: vụ Vương hoàng hậu và Tiêu Thục phi bị chặt tay
chân ném vào vại rượu năm 655 là sự thật, và nó không có cách nào bào chữa.

## NỘI DUNG

```
00:00  Mở đầu: thứ đưa bà lên ngôi không phải sự tàn nhẫn
00:59  Chương 1 — Mười hai năm không ai nhớ tên (624 đến 649)
05:07  Chương 2 — Ván cờ đổi bằng mạng (650 đến 659)
08:48  Chương 3 — Người đàn bà sau tấm rèm (660 đến 683)
12:41  Chương 4 — Chữ là vũ khí (684 đến 705)
18:01  Chương 5 — Tại sao nên cơ sự này
```

Mốc thật, đo bằng `ffmpeg blackdetect` trên chính file `video.mp4` đã xuất: sáu
đoạn đen tìm được khớp đúng sáu marker `[[black]]` trong script. Đoạn đen thứ tư
ở 10:29 là khối chào lại giữa video nằm trong chương 3, cố ý không đưa vào danh
sách chương để mục lục không bị gãy.

Độ dài từng chương: mở đầu 59 giây, chương 1 dài 4,1 phút, chương 2 dài 3,7
phút, chương 3 dài 3,9 phút, chương 4 dài 5,3 phút, chương 5 dài 4,3 phút.

## NGUỒN

Toàn bộ số liệu trong video đều trỏ về nguồn tra cứu được, danh sách đầy đủ nằm
trong `sources.md` đi kèm. Nguồn chính:

- Cựu Đường thư, quyển 6, Tắc Thiên hoàng hậu bản kỷ (soạn năm 945)
- Tân Đường thư, quyển 4 (soạn năm 1060)
- Tư trị thông giám, quyển 199 đến 208, Đường kỷ
- Wikipedia: Wu Zetian, Emperor Gaozong of Tang, Qianling Mausoleum,
  Wordless Stele, Zetian characters, Di Renjie, Lai Junchen, Zhang Jianzhi

Ảnh tư liệu lấy từ Wikimedia Commons và Unsplash, ghi công trong
`wiki-credits.json` và `photo-credits.json`.

## Tag

võ tắc thiên, wu zetian, lịch sử trung hoa, nhà đường, vô tự bi, càn lăng, hoàng đế nữ duy nhất, đường cao tông, địch nhân kiệt, tắc thiên tân tự, chính biến thần long, lịch sử trung quốc, kể chuyện lịch sử, nhân vật lịch sử, sử ký

## Ghi chú sản xuất (không đăng)

- Giọng: **Azure vi-VN-NamMinhNeural**, không phải giọng chuẩn kênh. Vbee sập
  (504) lúc dựng ngày 25/09/2026. Muốn đổi về chuẩn thì sửa `queue.yml` theo
  khối ghi chú trong đó rồi chạy `--from tts`.
- Nhịp đo được: 218 âm tiết/phút video, đích của skill `su-nhan-vat` là 223.
- Script: viết tay, bản sao ở `D:\dev\content\vo-tac-thien-ban-viet-tay\`.
