# S3-D06: Thử 10 CV thật, đo độ đúng kỹ năng, sửa alias thiếu

Ngày 16/11/2026 · Duy · Issue #480 (US-12 #403) · Quy trình: `docs/labeling/cv_real.md`

> **Kết quả (10 CV, lần 2 sau khi sửa):** đọc được 10/10 · kỹ năng **P 0,970 · R 0,779 · F1 0,864**
> (lần 1: 0,921 · 0,745 · 0,824) · đúng mức strong/listed 0,973 · số năm lệch ≤ 0,5 năm 10/10 ·
> chức danh 10/10 (lần 1: 0/10) · section 10/10 (lần 1: 0/10) · **CV còn lộ PII 0/10 (lần 1: 6/10)**.
> JD không tụt: trích kỹ năng 50 JD F1 0,795 → 0,802, gắn mức macro-F1 0,973 giữ nguyên.

## 1. Phần 1: alias / luật sửa từ lỗi đã biết (S3-D04)

| Vấn đề | Sửa | Ở đâu |
|---|---|---|
| "A/B tests" không nhận | + alias `a/b tests`, `ab tests` → `ab_testing` | `config/skills.yaml` |
| "kiểm thử người dùng" (user testing) thành Kiểm thử phần mềm | + `kiểm thử người dùng`, `kiểm thử khả dụng`, `user testing`, `usability testing` → `ui_ux` (cụm dài thắng "kiểm thử") | `config/skills.yaml` |
| "đọc hiểu tài liệu kỹ thuật" thành Technical Documentation | Bỏ alias chung `tài liệu kỹ thuật`; + `soạn tài liệu kỹ thuật`, `viết tài liệu` | `config/skills.yaml` |
| "Data Analyst" (chức danh) không thành Phân tích dữ liệu | + `data analyst`, `chuyên viên phân tích dữ liệu` → `data_analysis` | `config/skills.yaml` |
| "Spring-Boot" (gạch nối) thành Spring | + `spring-boot` → `spring_boot` | `config/skills.yaml` |
| Kỹ năng lấy từ **tên công ty** ("Blue Lotus **Cloud**"…) | Bỏ kỹ năng nằm trong tên công ty ở dòng tiêu đề việc làm | `cvparser/profile.py` |
| Kỹ năng lấy từ **URL** (`github.com/[LINK]`) | Bỏ kỹ năng nằm trong đường dẫn | `cvparser/profile.py` |

## 2. Bộ CV và cách chấm

- **10 CV PDF** Duy cung cấp, chép vào `data/cv_real/` (không lên git): Backend, Frontend, Full-Stack,
  Mobile, DevOps/Cloud, Data Engineer, AI/ML, QA/Automation, Cybersecurity, BA/PO. Mỗi CV 3 trang,
  **song ngữ**: phần I tiếng Anh, phần II tiếng Việt (cùng nội dung), cùng một mẫu, xuất từ Chrome.
- **Hạn chế**: cả 10 cùng một mẫu, chỉ có PDF (không có DOCX/Canva/TopCV, không có CV 2 cột), nên số
  liệu phản ánh mẫu song ngữ này hơn là CV thật nói chung. Đợt sau nên thêm CV đa dạng như
  `docs/labeling/cv_real.md` mục 1 gợi ý.
- **Chấm tay**: Claude chấm theo `docs/labeling/cv_real.md` mục 3, đối chiếu toàn văn từng CV. Bảng
  chấm nằm trong `data/eval/cv_real_*.csv` (không lên git). Duy nên xem lại các dòng `dung = n` và
  `cv_real_missing.csv` trước khi chốt số.
- Quy ước: kỹ năng thuộc **thẻ họ công cụ** đã gắn (k6 → JMeter, Splunk/Wazuh → SIEM, Mockito →
  JUnit, BPMN/Draw.io → UML…) không tính là bỏ sót. Lần 1 và lần 2 chấm bằng cùng một quy ước (theo
  từ điển sau khi sửa) để chênh lệch chỉ do máy đổi.
- Số năm tính tay từ các mốc thời gian, đến 11/2026 (CV ghi "Present"), không tính thực tập.

## 3. Kết quả trên 10 CV

| Chỉ số | Lần 1 (trước khi sửa) | Lần 2 (sau khi sửa) |
|---|---|---|
| CV đọc được | 10/10 | 10/10 |
| Thẻ máy gắn · đúng · sai | 304 · 280 · 24 | 302 · 293 · 9 |
| Kỹ năng bỏ sót | 96 | 83 |
| **Precision** | 0,921 | **0,970** |
| **Recall** | 0,745 | **0,779** |
| **F1** | 0,824 | **0,864** |
| Đúng mức strong/listed (trên thẻ đúng) | 0,982 | 0,973 |
| Số năm: MAE · lệch ≤ 0,5 năm | 0,0 · 10/10 | 0,0 · 10/10 |
| Chức danh hợp lý | 0/10 | **10/10** |
| Section đúng | 0/10 | **10/10** |
| CV còn lộ PII trong văn bản đã che | **6/10** | **0/10** |

Số liệu: `reports/eval_cv_real_lan1.json`, `reports/eval_cv_real.json` (lần 2). Chỉ có số liệu và tên
kỹ năng, không có nội dung CV.

Đúng mức giảm 0,982 → 0,973 vì lần 1 có 3 thẻ "strong" đúng một cách tình cờ: bằng chứng lấy từ dòng
footer ("CV 07 — AI / Machine Learning Engineer … Page 1 of 3") hoặc dòng chức danh phần tiếng Việt
bị xếp nhầm vào mục Dự án. Sửa footer và section thì 3 thẻ này về "listed" (xem mục 5).

## 4. Lỗi tìm thấy và đã sửa

### 4.1 Lộ PII (nghiêm trọng nhất, S3-D03)

| Lỗi (lần 1) | CV | Sửa |
|---|---|---|
| Họ tên **không bị che** khi có chữ Quân / Huyền / Phương: bỏ dấu thành "quan/huyen/phuong" trùng từ địa danh quận/huyện/phường trong `not_name_words` | 3/10 (cả phần Anh lẫn Việt) | Từ địa danh trùng tên (quận, huyện, phường, tỉnh, đường, trường, viện, phố) tách sang `place_words`, so **có dấu**; dòng không dấu chỉ chặn khi từ đứng đầu ("QUAN 3", "PHUONG 5") |
| Link portfolio cá nhân không bị che: `*.vercel.app`, `*.notion.site`, tên miền riêng, `huggingface.co/<tên>` | 4/10 | + nhãn `Portfolio:`/`Website:`/`Blog:` → che giá trị; + `profile_hosts` (tên miền con là tên người: vercel.app, netlify.app, github.io, notion.site…); + huggingface.co, kaggle.com…; link tìm được che ở **mọi chỗ** (CV song ngữ ghi lại ở dòng không có nhãn) |

`config/pii.yaml` lên `pii-2`. Bộ 20 mẫu S3-D03 vẫn 20/20 không lộ.

### 4.2 Đọc cấu trúc CV

| Lỗi (lần 1) | Hậu quả | Sửa |
|---|---|---|
| Footer "CV 01 — … (Bilingual EN/VI) Page 1 of 3" không bị nhận là footer vì số trang khác nhau mỗi trang | Footer nằm giữa mục Kinh nghiệm → "Java", "Machine Learning", "Automation Test" thành bằng chứng strong giả | `pdf.py` (`pdf-3`): bỏ đuôi "Page N of M" / "Trang N/M" khi so dòng lặp; footer gom một lần ở đầu văn bản, không kèm số trang |
| "PART I — ENGLISH VERSION" / "PHẦN II — PHIÊN BẢN TIẾNG VIỆT" không phải heading | Chức danh máy đề xuất = "PART I — ENGLISH VERSION" (10/10); tên + liên hệ phần tiếng Việt rơi vào mục Học vấn/Chứng chỉ/Dự án → "GitHub" (9 CV), "Flutter", "AWS", "Kubernetes" sai mục | `cv_headings.yaml` (`cv-sections-2`): các tiêu đề phần ngôn ngữ → `header` |
| Nhãn che "[HỌ_TÊN]" viết HOA bị đoán là heading (luật đoán heading chữ IN HOA) | Phần sau tên thành "Dự án" | `sections.py`: dòng chỉ có nhãn che PII không phải heading |
| "KEY ACHIEVEMENTS" chưa có trong danh sách heading | Bug bounty rơi vào Kinh nghiệm | + `key achievements`, `notable achievements` → activities |
| Dòng việc làm kiểu tiếng Anh: "Chức danh — Công ty" rồi dòng "June 2024 – Present \| Hanoi, Vietnam" | Máy lấy "Hanoi, Vietnam" làm tên công ty; tên công ty thật không được lọc → "Fintech" (VietCloud **FinTech** Solutions), "Phân tích dữ liệu" (DataInsight **Analytics**) | `profile.py` (`cv-profile-2`): dòng ngày chỉ còn nơi làm → lấy dòng trước làm tiêu đề việc làm; tự nhận phần nào là công ty, phần nào là chức danh |
| "GitHub: github.com/[LINK]" | GitHub thành kỹ năng (9/10 CV) | Nhãn đứng ngay trước một link không phải kỹ năng |
| Tên trường / ngành ở Học vấn: "Academy of **Cryptography** Techniques", "B.Eng. in **Network** & Telecommunications", "Khoa học **Máy** tính" | Cryptography, Networking, Machine Learning sai | Mục Học vấn: dòng có từ trường/bằng cấp (`school_words` trong `cv_profile.yaml`) không lấy kỹ năng |
| Chức danh có ngoặc liệt kê công nghệ: "Full-Stack Software Engineer (Node.js / React / AWS)" quá 7 từ | Rơi xuống chức danh việc làm gần nhất | Bỏ phần trong ngoặc trước khi đếm từ; xét mọi khối header (CV song ngữ có 2 khối) |

### 4.3 Từ điển (`config/skills.yaml`)

| Cách viết trong CV | Trước | Sửa |
|---|---|---|
| "Khoa học Máy tính" (tên ngành) | Machine Learning (chứa "học máy"); gặp ở **95/1833** tin VietJobs | Mới: `stop_phrases` (cụm chặn: cụm dài nuốt alias bên trong rồi bị bỏ) + `khoa học máy tính` |
| "SQLite, **Hive**, Isar" (CSDL cục bộ Flutter) | Hadoop | `hive` thành từ nhập nhằng: cần ngữ cảnh big data, có từ veto Flutter/SQLite/offline |
| "Lập kế hoạch kiểm thử" | Quản lý thời gian | + `lập kế hoạch kiểm thử`, `lập kế hoạch test`, `test plans` → Test Case Design |
| "Agile/Scrum" | Chỉ Agile (alias gộp) | Bỏ alias `agile/scrum` → ra cả Agile và Scrum |
| "S3", "RDS", "IAM" trong "AWS (EC2, S3, RDS, IAM)" | Không nhận | + `s3`, `rds`, `iam`; `iam` cần ngữ cảnh AWS (IAM chung của Azure/GCP không phải AWS IAM) |
| "peer code reviews" | Không nhận | + `code reviews`, `peer code review(s)` |
| "Firebase Crashlytics", "Apollo Client" | Không nhận | + vào Firebase, GraphQL |
| "BLoC", "Riverpod", "GetX" | Không nhận | + vào Flutter (thẻ họ, như k6 → JMeter) |
| "OSCP", "CEH" | Không nhận | + vào Penetration Testing |
| "backlog grooming", "Product Backlog" | Không nhận | + vào Quản lý sản phẩm |
| "regression testing", "kiểm thử hồi quy", "smoke test" | Không nhận | + vào Kiểm thử phần mềm |
| "SaaS", "multi-tenant" | Ngoài từ điển (37/1833 tin) | Kỹ năng mới `saas` (domain, như Fintech/E-commerce) |
| "UAT sign-offs", "nghiệm thu UAT" | Ngoài từ điển (33/1833 tin) | Kỹ năng mới `uat` (con của Kiểm thử phần mềm) |

`db/seed/seed_skills.sql` sinh lại: **381 kỹ năng, 1310 cách viết**.

## 5. Còn lại (không sửa, có lý do)

**9 thẻ sai còn lại**: "Kiểm thử" trong "kiểm thử xâm nhập" bị **ngắt dòng** ("kiểm thử xâm⏎nhập"; bộ
khớp làm theo dòng); "kiểm thử chất lượng dữ liệu"; "kỹ sư, thiết kế UI/UX và kiểm thử viên" (thành
viên nhóm, 2 thẻ); "Kanban Workspace" (tên sản phẩm); "analytics dashboards", "analytics-ready
assets", "BI dashboard" (3 thẻ, cần hiểu nghĩa câu); "Thiết kế hệ thống trợ lý ảo" (động từ, nhưng
trong JD "thiết kế hệ thống" đúng là kỹ năng nên giữ alias). Những lỗi này cần Tầng 2 (mô hình theo
ngữ cảnh), từ điển không sửa được mà không làm hỏng JD.

**8 thẻ sai mức** (máy "listed", đúng là "strong"): kỹ năng dùng trong Kinh nghiệm nhưng câu ở đó viết
bằng **tên con** hoặc cách nói khác: AWS ("Docker on **AWS ECS**"), Kubernetes ("**EKS** clusters"),
Machine Learning ("trained **YOLOv8**"), REST API ("REST **endpoints**"), API Testing, Performance
Testing ("**k6 load tests**"), Agile ("sprint planning"), Stakeholder Management ("stakeholder
**interviews**"). Hướng sửa (S4): kỹ năng con strong thì kỹ năng cha cũng strong.

**Alias không thêm** (dễ gây nhầm hơn lợi): `lambda` (lambda của Java/Python), `provider` (từ thường),
`vpc` (không riêng AWS), "unit and integration testing" (cụm ghép, cần tách "unit … testing").

**83 kỹ năng bỏ sót**, phần lớn **ngoài từ điển** và hiếm trong JD. Ví dụ (số tin VietJobs có từ khóa,
trên 1833, đếm thô bằng regex): Zustand 4, React Query 3, RBAC 3, Dependency Injection 3, Webhook 2, Prisma 0, TypeORM 0,
shadcn/ui 0, Framer Motion 0, Isar 0, Codemagic 0, Fastlane 1, WebRTC 1, Trivy 1, Snyk 1, Semgrep 1,
vLLM 0, LoRA/QLoRA 0, TensorRT 0, ONNX 2, CUDA 0, RAGAS 0, Great Expectations 0, Delta Lake 1, Iceberg
0, RestAssured 2, Allure 1, Page Object Model 0. Kỹ năng không có trong JD thì không giúp ghép
CV ↔ việc, nên **chưa thêm**. Khi kho JD lớn hơn, chạy lại đếm tần suất rồi thêm những kỹ năng
≥ 5 tin. Đáng cân nhắc trước (số đếm thô, cần lọc tay): App Store/Google Play (21/18 tin), Data
Modeling (18), Vulnerability Management (17).

## 6. Không làm tụt chất lượng chỗ khác

| Bộ đo | Trước S3-D06 | Sau S3-D06 |
|---|---|---|
| 10 CV mẫu, hồ sơ JSON (S3-D04) | 10/10 | 10/10 |
| 20 mẫu che PII (S3-D03) | 20/20 không lộ | 20/20 không lộ |
| Gắn mức JD (S2-D04) | macro-F1 0,973 (747 mention) | **0,973** (741 mention: 3 lần "Khoa học máy tính" không còn là Machine Learning; 3 lần "Agile/Scrum" nay tách thành 2 mention khác vị trí gold) |
| Trích kỹ năng JD (S2-D07, 50 JD), chỉ kỹ năng | P 0,995 · R 0,662 · F1 0,795 | **P 0,995 · R 0,672 · F1 0,802** |
| Trích kỹ năng JD, kỹ năng + mức | P 0,982 · R 0,653 · F1 0,785 | P 0,975 · R 0,658 · F1 0,786 |

Cột "Trước" chấm lại bằng bộ chấm đã sửa (dưới đây) trên commit trước S3-D06 phần 2, để so cùng
thước đo.

**Sửa bộ chấm S2-D07** (`scripts/evaluate_extraction.py`): người gán ghi một kỹ năng là "máy bỏ sót"
mà máy đã gắn (gán nhầm, hoặc từ điển vừa được sửa để bắt được) thì bộ chấm **bỏ nó khỏi nhãn chuẩn**,
nên chính thẻ đúng đó bị tính là thẻ sai. Đó là lý do phần 1 báo "3 thẻ sai mới đều đúng là kỹ năng"
(P 0,995 → 0,987). Nay kỹ năng đó vẫn là nhãn chuẩn, chỉ không tính là bỏ sót. Nhãn chuẩn
`tests/fixtures/jd_gold/skills_gold.csv` chỉ đổi 2 dòng: UAT và SaaS nay có mã kỹ năng.

## 7. Chạy lại

```bash
uv run python scripts/eval_cv_real.py run --as-of 2026-11-16 --force   # đọc lại 10 CV
uv run python scripts/eval_cv_real.py score                            # sau khi chấm 3 file CSV
uv run python scripts/evaluate_extraction.py score --name eval_extraction_s3d06_lan2
```

**Sau khi merge** (Tùng): từ điển, luật che PII, section và hồ sơ đều đổi phiên bản, nên CV và JD cũ
cần xử lý lại:

```bash
psql "$DATABASE_URL" -f db/seed/seed_skills.sql                       # kỹ năng + alias mới
uv run python scripts/label_skills.py --apply --stale --only-open     # gắn lại kỹ năng tin đang mở
```

CV đã tải lên trước đó cần che PII và đọc lại (`pii-2`, `cv-sections-2`, `cv-profile-2`, `pdf-3`).

**Riêng tư**: xong đồ án thì xóa `data/cv_real/` và `data/eval/cv_real*` (`docs/labeling/cv_real.md`
mục 5).
