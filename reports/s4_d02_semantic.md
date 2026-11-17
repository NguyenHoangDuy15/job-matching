# S4-D02 · E (điểm Ngữ nghĩa): max-cosine trung bình theo đoạn, phân vị toàn kho

Ngày 17/11/2026 · Duy · Issue #492 (US-16 #408) · Model: bge-m3 qua Workers AI (ADR-004)

> **Kết quả:** tính E của 1 CV với 2.000 tin (8.504 đoạn) mất **6,5 ms (p95)**, AC ≤ 500 ms.
> Nạp ma trận vector tin đang mở dạng binary mất khoảng 3–6 s (dạng text: 24 s), làm lúc API
> khởi động và mỗi giờ ở luồng nền. Vector hóa 1 CV qua Workers AI: p50 346 ms, chỉ lần đầu.

## 1. Cách làm

E là 1 trong 4 điểm thành phần của `H = 100 × (0,25 K + 0,35 M + 0,30 E + 0,10 X)`.

```
E_raw(j) = (1/n) Σᵢ maxₖ cos(cᵢ, dₖ)     cᵢ: n đoạn CV · dₖ: các đoạn của tin j
E(j)     = phân vị của E_raw(j) trên mọi tin đang mở có vector
```

1. **Ma trận tin** (`src/ranking/semantic.py`, `SemanticIndex.from_db`): đọc `core.job_chunks` của
   tin đang mở dạng binary (`pgvector` → numpy float16), sắp theo tin, chuẩn hóa L2 → float32
   (25 MB với 6.130 đoạn). Chỉ lấy vector cùng model `cf/baai/bge-m3`.
2. **Tính E** thuần numpy: `S = Q @ M.T`, `np.maximum.reduceat` theo ranh giới tin, trung bình
   theo đoạn CV, rồi phân vị (`src/ranking/percentile.py`, dùng chung với K).
   - **Chiều CV → JD**: mọi tin chấm bằng cùng một tập đoạn CV nên so được với nhau. Luồng HR
     (1 JD với nhiều CV) đảo đầu vào của `maxsim`.
   - Tin chưa có vector → `E = None` (S4-D03 chia lại trọng số), không coi là 0.
   - Vector CV khác model với kho tin → báo lỗi, không so lẫn.
3. **Đoạn CV** (`embedding.chunker.cv_chunks`): đoạn tóm tắt "Chức danh mong muốn · Kỹ năng" (đối
   xứng với đoạn summary của tin), rồi các mục giới thiệu, kinh nghiệm, dự án, kỹ năng, chứng chỉ,
   ≤ 300 token, tiền tố "CV — Mục:". Bỏ header (đã che PII), học vấn, ngoại ngữ, hoạt động: giống
   nhau ở mọi tin nên chỉ kéo E của mọi tin lại gần nhau.
4. **Cache vector CV** (`CvVectorCache`): nhớ trong RAM theo sha256 nội dung đoạn + model: đổi N
   hay bộ lọc không gọi lại Workers AI.
5. `top_k(result, 100, allowed_ids)` trả top 100 theo vector cho S4-D04. Kho chỉ vài nghìn đoạn
   nên quét toàn bộ trong RAM nhanh hơn gọi HNSW trên DB.
6. Làm mới mỗi giờ: `ranking.refresh.RefreshingIndex` (chuyển từ S4-D01, dùng chung cho K và E).

## 2. Đo trên dữ liệu thật

`uv run python scripts/semantic_bench.py` · 1.441 tin / 6.130 đoạn thật trên Supabase (chỉ đọc),
nhân lên 2.000 tin / 8.504 đoạn · 10 CV mẫu (CV giả trong `tests/fixtures/cv/samples`), vector hóa
thật qua Workers AI · 20 lần mỗi CV · máy Duy.

| Chỉ số | Kết quả |
|---|---|
| Nạp ma trận (binary) | 3,3–5,6 s (dạng text: 24 s, 78 MB) |
| Tính E 1 CV × 2.000 tin, p50 / p95 | **3,1 ms / 6,5 ms** |
| AC ≤ 500 ms | Đạt |
| Vector hóa CV lần đầu (4–8 đoạn) | p50 346 ms, max 552 ms |
| Vector hóa CV lần sau (cache) | < 0,1 ms |

Top 3 theo E, so với K (S4-D01):

| CV mẫu | Top 3 theo E | Trùng top 5 của K |
|---|---|---|
| Lập trình viên Backend | Backend Developer (Java) · CV/CVCC Backend Software · Backend Developer | 1/5 |
| Data Analyst | Data Analyst · Data Analyst · Data Analyst (Data Science Track) | 3/5 |
| Lập trình viên Frontend | Front-End React Developer · Nhân Viên Frontend Developer · Frontend Engineer | 4/5 |
| Kiểm thử phần mềm | Trưởng Nhóm Kiểm Thử Phần Mềm · Chuyên Viên Kiểm Thử Phần Mềm · Chuyên Viên Kiểm Thử (Tester) | 0/5 |
| DevOps Engineer | Cloud DevOps Engineer · Kỹ Sư DevOps · Cloud Operation/Platform Engineer | 2/5 |
| Kỹ sư Dữ liệu | Data Engineer (Kỹ Sư Dữ Liệu) · Chuyên Viên Kỹ Sư Dữ Liệu · Data Engineer | 2/5 |
| UI/UX Designer | UI/UX Designer × 3 | 2/5 |
| Lập trình viên Mobile | Flutter Engineer · Mobile App Developer (Flutter) · Lập Trình Viên Mobile | 2/5 |
| Chuyên viên Phân tích nghiệp vụ | Chuyên Gia Phân Tích Nghiệp Vụ · Chuyên Viên Phân Tích Nghiệp Vụ · Trưởng Nhóm Phân Tích Nghiệp Vụ | 1/5 |
| Kỹ sư An toàn thông tin | Kỹ Sư An Toàn Thông Tin (Pentest) · Kiểm Thử Xâm Nhập (Pentest) · Cyber Security Engineer | 4/5 |

E bắt được tin chức danh tiếng Việt mà K bỏ sót ("Kiểm Thử Phần Mềm", "Phân Tích Nghiệp Vụ" cho
CV viết chức danh khác). Đây đúng là lý do kết hợp K và E (hybrid). Cosine top nằm trong khoảng
0,59–0,74 cho mọi CV: giá trị tuyệt đối hẹp, nên dùng phân vị thay vì cosine thô.

## 3. Kiểm thử

`tests/unit/test_semantic_e.py`, 13 test, không cần DB và mạng:

| Test | Kiểm tra |
|---|---|
| `test_maxsim_matches_brute_force` | Khớp vòng lặp tính tay; tin 1 đoạn và 15 đoạn |
| `test_job_boundaries_and_best_chunk_at_end` | Đoạn tốt nhất ở cuối tin vẫn được lấy, không lẫn tin bên cạnh |
| `test_chunks_of_a_job_must_be_contiguous` | Đoạn của một tin không liền nhau → báo lỗi |
| `test_percentile_shared_with_k_bounds_and_ties` | Trong [0, 1], đơn điệu, hòa điểm cùng E |
| `test_job_without_vectors_has_no_e` | Tin chưa có vector → None, không phải 0 |
| `test_empty_cv_or_empty_index_gives_none` | CV không có đoạn / kho rỗng → None |
| `test_model_mismatch_refused` | Không so vector của hai model |
| `test_float16_storage_keeps_cosine` | Sai số float16 so với float32 < 1e-3 |
| `test_e_does_not_change_with_filters` | Lọc chỉ đổi top_k, không đổi E |
| `test_cv_chunks_keep_professional_sections_only` | Không có học vấn, hoạt động, liên hệ; ≤ 300 token |
| `test_cv_texts_from_parse_cv_output` | Dùng thẳng kết quả `parse_cv` |
| `test_cv_vectors_cached_by_content` | Cùng nội dung chỉ gọi model 1 lần; giới hạn số CV nhớ |
| `test_e_for_2000_jobs_within_500ms` | **AC**: 2.000 tin, 10 đoạn CV, ≤ 500 ms |

## 4. Hạn chế, việc sau

- Vector CV mới nhớ trong RAM (mất khi API khởi động lại). Lưu bền vào `app.cv_chunks` cần migration
  thêm policy RLS (bảng đã bật RLS nhưng chưa có policy, hiện 0 dòng): giống `cv_child` của
  `cv_skills`. Đề xuất Tùng làm trước S4-D04.
- API đọc ma trận cần role Postgres chỉ đọc (`matcher_ro`), dùng chung với S4-D01.
- Độ đúng mới kiểm bằng mắt; nDCG@10 khi có bộ nhãn CV–JD (US-21).
- AC tính riêng phần tính E. Vector hóa CV lần đầu (khoảng 0,35 s) nằm trong ngân sách p95 ≤ 3 s
  của S4-D05.
