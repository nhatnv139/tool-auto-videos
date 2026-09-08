# 01-format.md — Công thức video (giải mã từ video mẫu AI Frontier)

Nguồn mẫu chính: `samples/video-1-sources.md` (3ohDmtfdHks) và
`samples/video-2-sources.md` (TE1QQ4h0An4).

## Video tham chiếu FORMAT (học cách dựng — chỉ URL + ghi chú)

| Video | Vì sao tham chiếu |
|---|---|
| AI Frontier — "AI realises it's not being watched" (`3ohDmtfdHks`) | Chuẩn format gốc: 8-beat, clip chuyên gia + số liệu, narrator châm biếm |
| AI Frontier — "Loving AI robot does exactly what experts warned" (`TE1QQ4h0An4`) | Format tương tự, chủ đề companions, có meta-twist "I'm not human" |
| Cold Fusion — documentary tech | Pacing kể chuyện, nhiều clip nguồn đan xen |
| A Bit of Worry / AI Explained — AI commentary | Châm biếm, nhịp nhanh, hook mạnh |
| The AIGRID — AI news analysis | Cắt clip nóng + phân tích, intro hấp dẫn |
| Last Week Tonight (John Oliver) — AI segment | Hài + clip chuyên gia, "let it land" beats chuẩn |

## 8-beat structure (cả 2 video giống hệt)

| Beat | Chức năng | Vị trí | Ví dụ (video 2) |
|---|---|---|---|
| **Cold open** | Hook 5s + clip chuyên gia ngay, không intro | 0:00–0:50 | "There is a risk that doesn't get discussed enough" → clip "I felt the purest unconditional love..." |
| **Setup** | Nêu luận điểm cốt lõi | ~0:50 | "Can an AI change your deepest beliefs without you knowing?" |
| **Bằng chứng tăng dần** | 4–6 beat: claim → bằng chứng → joke → nâng mức | 1:00–80% | Zurich exp → 200M users → children → brain rot → population → control |
| **Climax** | Khoảnh khắc "oh sht" | ~85% | "The technology is systematically reducing users' capacity for real human connection" |
| **Meta twist** (tùy chọn) | Narrator lộ diện là AI | ~90% | "I'm not human. I'm an AI-generated presenter." |
| **Giải pháp** | "What can we do", thực tế, có nguồn | cuối | AI chips trackable, regulation |
| **Close** | Bookend gag + câu mạnh | cuối cùng | "Russian roulette" lặp lại từ mở đầu |

## Nhịp cắt (pacing)

```
VO (5–20s) → clip chuyên gia (4–15s) → VO joke (3–8s) → [card stat im 2–4s] → VO → clip...
```

- Clip chuyên gia đặt ở **đỉnh cảm xúc**: narrator set up, clip đấm.
- Joke cách clip nghiêm túc ≤ 2 dòng; **không joke đè clip**.
- Số liệu đứng riêng, 1 số/câu, cuối câu → chỗ chèn card.
- Sau reveal lớn: im 0.8–1.5s (nhạc lên) = `pause_after`.
- Nhạc: duck khi có tiếng nói; swell ở reveal; **cut hẳn (drop) ở twist**.

## Cách viết script (tóm tắt)

1. Hook ≤ 5 giây, câu khẳng định táo bạo, không chào hỏi.
2. Số liệu là đơn vị hài: "six times more persuasive", "85,000 weekly visitors".
3. Cầu nối leo thang: "But it gets way worse" / "But that's just the beginning".
4. Câu hỏi tu từ giữa chân: "What alarm are we waiting for...".
5. Narrator đùa, clip nói chuyện.
6. ~170 từ/phút, văn nói Mỹ.

Chi tiết giọng + marker script: `docs/03-script.md`.
