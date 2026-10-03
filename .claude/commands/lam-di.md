---
description: Chay hang doi video trong queue.yml (goi auto/runner.py)
allowed-tools: Bash(python auto/runner.py:*), Read
---

Chay day chuyen san xuat video cho cac muc chua xong trong `queue.yml`.

Lenh tuong duong go thang trong terminal: `python auto\runner.py $ARGUMENTS`

Viec cua ban:
1. Chay `python auto/runner.py $ARGUMENTS` (neu khong co tham so thi chay khong tham so).
2. Doc tong ket in ra cuoi cung.
3. Bao lai cho nguoi dung: video nao XONG (kem duong dan OUTBOX), video nao HONG
   (kem dong loi cuoi trong `auto/logs/<slug>.log`), video nao dang CHO duyet.

Khong tu sua script, khong tu render lai — chi bao ket qua.
