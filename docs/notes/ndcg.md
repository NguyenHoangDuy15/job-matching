# nDCG@10 tính tay (TASK-D008)

Đối chiếu bằng code: `uv run pytest tests/learning/test_ndcg.py` → 3 passed.

## Công thức

Nhãn: 0 đến 3, càng cao càng liên quan. Vị trí `i` đếm từ 1.

- Gain Burges: `2^nhãn − 1`, nên nhãn 0, 1, 2, 3 có gain 0, 1, 3, 7. Giống `ndcg_burges` của ranx.
- `DCG@k` = tổng `gain / log2(i + 1)` của k vị trí đầu theo thứ tự hệ thống trả về.
- `IDCG@k` là DCG@k của thứ tự tốt nhất: sắp **toàn bộ** nhãn của truy vấn giảm dần rồi cắt k.
- `nDCG@k = DCG@k / IDCG@k`, từ 0 đến 1. Nếu IDCG = 0 (không có tài liệu liên quan) thì quy ước bằng 0.

Mẫu số `log2(i + 1)`: vị trí 1 là 1, vị trí 2 là 1.5850, 3 là 2, 4 là 2.3219, 5 là 2.5850, 6 là 2.8074.

## Kết quả

| Truy vấn | Nhãn theo thứ tự hệ thống | DCG@10 | IDCG@10 | nDCG@10 |
| --- | --- | --- | --- | --- |
| q1 | 3, 2, 3, 0, 1, 2 | 13.8483 | 14.5954 | **0.9488** |
| q2 | 0, 0, 1, 3 | 3.5147 | 7.6309 | **0.4606** |
| q3 | 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 3 | 3.6309 | 9.3928 | **0.3866** |

## Tính chi tiết

Các vị trí có nhãn 0 cho đóng góp bằng 0 nên không ghi.

**q1**

- DCG = 7/1 + 3/1.5850 + 7/2 + 1/2.5850 + 3/2.8074 = 7 + 1.8928 + 3.5 + 0.3869 + 1.0686 = 13.8483
- Thứ tự tốt nhất: 3, 3, 2, 2, 1, 0
- IDCG = 7/1 + 7/1.5850 + 3/2 + 3/2.3219 + 1/2.5850 = 7 + 4.4165 + 1.5 + 1.2920 + 0.3869 = 14.5954
- nDCG = 13.8483 / 14.5954 = 0.9488

**q2**

- DCG = 1/2 (vị trí 3) + 7/2.3219 (vị trí 4) = 0.5 + 3.0147 = 3.5147
- Thứ tự tốt nhất: 3, 1, 0, 0
- IDCG = 7/1 + 1/1.5850 = 7 + 0.6309 = 7.6309
- nDCG = 3.5147 / 7.6309 = 0.4606

**q3**

- DCG@10 chỉ xét 10 vị trí đầu, nên nhãn 3 ở vị trí 11 bị cắt: 3/1 + 1/1.5850 = 3 + 0.6309 = 3.6309
- Thứ tự tốt nhất: 3, 2, 1, 0, ...
- IDCG = 7/1 + 3/1.5850 + 1/2 = 7 + 1.8928 + 0.5 = 9.3928
- nDCG = 3.6309 / 9.3928 = 0.3866

## Điều rút ra

- **Đưa tài liệu tốt lên đầu là chính.** q2 có nhãn 3 ở vị trí 4 nên mất hơn nửa điểm, vì gain 7 chỉ còn 3.01 sau khi chia mẫu số.
- **Gain Burges thưởng rất mạnh cho nhãn 3:** nhãn 3 có gain 7, gấp hơn 2 lần nhãn 2.
- **Cắt k chỉ áp dụng sau khi sắp xếp.** Ở q3, tài liệu nhãn 3 không vào được DCG@10 nhưng vẫn nằm trong IDCG@10. Nếu tính IDCG từ danh sách đã cắt thì q3 thành 1.0, cao giả.
- **Khác nhau về gain thì khác điểm.** Với gain tuyến tính (gain = nhãn), q1 là 0.9608 thay vì 0.9488, nên khi so sánh kết quả phải ghi rõ công thức.
