# Hướng dẫn gán nhãn mức liên quan CV–JD, bản nháp v0

TASK-H006 · US-12.02/AC1 · Người viết: Thịnh · Trạng thái: **nháp, chờ góp ý để chốt v1 (TASK-H012)**

## 1. Mục đích

Mỗi nhãn trả lời một câu hỏi: **"Nếu hệ thống gợi ý JD này cho ứng viên có CV này, đó là gợi ý tốt đến mức nào?"**

Nhãn dùng để tính nDCG@10 cho ranker và các baseline. Ba người (Duy, Tùng, Thịnh) cùng gán, nên hướng dẫn này cần đủ rõ để hai người đọc cùng một cặp ra cùng một nhãn. Mục tiêu của gold set là kappa ≥ 0,6.

Gain theo ADR-001 nháp là `2^nhãn − 1`, tức nhãn 0, 1, 2, 3 lần lượt đáng 0, 1, 3, 7 điểm. Nhãn 3 nặng gấp đôi nhãn 2, nên **chặt tay với nhãn 3**: chỉ cho khi thật sự không còn gì để chê.

## 2. Thang 0–3

| Nhãn | Tên | Ý nghĩa ngắn | Ứng viên nên làm gì |
|---|---|---|---|
| **3** | Rất phù hợp | Đúng nghề, đúng cấp, đáp ứng gần hết yêu cầu bắt buộc | Nộp ngay; HR gần như chắc sẽ gọi phỏng vấn |
| **2** | Phù hợp | Đúng nghề, nhưng thiếu 1–2 yêu cầu bắt buộc hoặc lệch 1 bậc cấp | Đáng cân nhắc nộp |
| **1** | Liên quan một phần | Cùng lĩnh vực rộng hoặc chung vài kỹ năng, nhưng khác vai trò chính hoặc lệch cấp xa | Chỉ nộp nếu muốn chuyển hướng |
| **0** | Không liên quan | Khác nghề; nếu có trùng thì chỉ trùng từ khóa bề mặt | Không nên nộp |

## 3. Cách chấm: 3 câu hỏi theo thứ tự

Đọc phần **yêu cầu** của JD trước, sau đó đọc phần **kinh nghiệm và dự án** của CV, rồi trả lời lần lượt:

**Câu 1. Vai trò chính có cùng nghề không?** Xét theo việc người đó *thực sự làm*, không theo từ khóa.
- Khác nghề → **0**, dừng.
- Cùng lĩnh vực rộng nhưng khác vai trò (QA ↔ BA, Data Analyst ↔ Data Engineer) → **1**, dừng.
- Cùng nghề → sang câu 2.

**Câu 2. Cấp có khớp không?** Dùng bảng bậc: Intern/Fresher (dưới 1 năm) · Junior (1–2 năm) · Mid (2–5 năm) · Senior (5 năm trở lên) · Lead/Architect.
- Lệch từ 2 bậc trở lên, theo cả hai chiều (thiếu hoặc thừa) → **1**, dừng.
- Lệch 1 bậc → **tối đa 2**, sang câu 3.
- Khớp → sang câu 3.

**Câu 3. Đáp ứng yêu cầu bắt buộc (must) đến đâu?**
- Có gần hết must, thiếu tối đa 1 must phụ (không phải kỹ năng cốt lõi của vai trò) → **3**.
- Thiếu 1–2 must, hoặc chỉ có kỹ năng tương đương thay cho must cốt lõi → **2**.
- Thiếu phần lớn must → **1**.

Lấy **mức thấp nhất** trong các giới hạn ở câu 1–3. Yêu cầu ưu tiên (nice to have) chỉ dùng để chọn giữa hai mức khi đang phân vân. Nó không bao giờ đẩy nhãn vượt giới hạn mà câu 1–3 đã đặt.

## 4. Ba CV persona dùng trong ví dụ

Đây là persona giả lập, không phải CV thật.

| Mã | Tóm tắt CV |
|---|---|
| **P1** | Fresher Backend Java. Tốt nghiệp CNTT, thực tập 3 tháng. Đồ án: REST API bằng Spring Boot + MySQL. Biết Git, cơ bản Docker. |
| **P2** | Data Analyst 3 năm, ngành ngân hàng. SQL thành thạo, dashboard Power BI, Excel nâng cao, Python pandas mức khá. |
| **P3** | Tester 2 năm, chủ yếu test thủ công web và API. Viết test case, dùng Jira, Postman. Có viết vài script Selenium Java cơ bản. |

## 5. Ví dụ: 3 ví dụ cho mỗi mức

JD trong ví dụ do nhóm tự viết theo dạng tin TopCV, không chép tin thật.

### Nhãn 3: Rất phù hợp

| CV | JD | Vì sao |
|---|---|---|
| P1 | **Fresher Java Developer**, 0–1 năm. Must: Java, Spring Boot, SQL. Nice: Docker. | Đúng nghề, đúng cấp, đủ cả 3 must, có luôn nice. |
| P2 | **Data Analyst**, 2–4 năm. Must: SQL, Power BI hoặc Tableau, Excel. Nice: Python. | Đúng nghề, 3 năm nằm trong khoảng yêu cầu, đủ must. |
| P3 | **Manual Tester (Web/API)**, 1–3 năm. Must: viết test case, test API, Jira. Nice: Selenium. | Đúng nghề, đúng cấp, đủ must; Selenium cơ bản là điểm cộng. |

### Nhãn 2: Phù hợp

| CV | JD | Vì sao |
|---|---|---|
| P1 | **Junior Backend Developer (Node.js)**, 1 năm. Must: Node.js, REST API, SQL. | Đúng vai trò backend. Fresher so với Junior lệch 1 bậc → tối đa 2. Thiếu must cốt lõi Node.js nhưng có Java tương đương (quy tắc 5), REST/SQL đã có. → 2. |
| P2 | **Senior Data Analyst**, 5+ năm. Must: SQL, BI, dẫn dắt phân tích cho phòng ban. | Đủ kỹ năng nhưng Mid so với Senior là lệch 1 bậc. Câu 2 giới hạn → 2. |
| P3 | **Automation Tester**, 2 năm. Must: Selenium (Java hoặc Python), viết framework test, CI. | Đúng nghề, đúng cấp; có Selenium cơ bản nhưng thiếu framework và CI (2 must). Câu 3 → 2. |

### Nhãn 1: Liên quan một phần

| CV | JD | Vì sao |
|---|---|---|
| P1 | **Senior Java Architect**, 8+ năm. Must: thiết kế hệ thống phân tán, microservices, dẫn dắt nhóm. | Đúng ngôn ngữ, đúng nghề, nhưng Fresher so với Lead/Architect lệch xa. Câu 2 → 1. |
| P2 | **Data Engineer**, 2–4 năm. Must: Python, Spark, Airflow, Kafka. | Cùng mảng dữ liệu, chung SQL/Python, nhưng vai trò khác (xây pipeline, không phân tích). Câu 1 → 1. |
| P3 | **Business Analyst**, 2 năm. Must: thu thập yêu cầu, viết user story, vẽ quy trình. | QA có đọc yêu cầu nên liên quan, nhưng vai trò chính khác. Câu 1 → 1. |

### Nhãn 0: Không liên quan

| CV | JD | Vì sao |
|---|---|---|
| P1 | **Nhân viên kinh doanh phần mềm (IT Sales)**. Must: tìm khách hàng, đạt doanh số. | Bẫy từ khóa "phần mềm"; công việc là bán hàng, không phải lập trình. |
| P2 | **Nhân viên nhập liệu (Data Entry)**. Must: gõ nhanh, cẩn thận. | Bẫy từ khóa "Data"; công việc không cần phân tích. |
| P3 | **Kỹ sư QA/QC cơ khí**. Must: đọc bản vẽ, kiểm tra kích thước sản phẩm. | Bẫy từ khóa "QA"; đây là kiểm tra chất lượng sản xuất, không phải phần mềm. |

## 6. Quy tắc cho ca khó

1. **Phân vân giữa hai mức thì chọn mức thấp hơn**, và ghi `phân vân` vào ghi chú. Quy tắc này giữ nhãn nhất quán giữa ba người, và những cặp đã ghi chú sẽ được đem ra buổi hiệu chuẩn.
2. **Trùng từ khóa không phải là trùng nghề.** Java ≠ JavaScript, "Go" ≠ Google, "Data Entry" ≠ Data Analyst, "QA/QC sản xuất" ≠ QA phần mềm. Chấm theo vai trò thực.
3. **Thừa cấp cũng là lệch cấp.** Senior 7 năm gặp JD Intern lệch ≥ 2 bậc → 1. Lý do: người đó gần như chắc không nộp.
4. **JD "không yêu cầu kinh nghiệm"** được coi là khớp với Intern, Fresher và Junior. JD ghi một khoảng năm (2–4 năm) thì dùng cả khoảng; CV nằm trong khoảng là khớp.
5. **Kỹ năng tương đương** (React ↔ Vue, MySQL ↔ PostgreSQL, AWS ↔ GCP, Java ↔ C#) được tính là đáp ứng *một nửa*. Nếu nó thay cho một must cốt lõi thì nhãn tối đa là 2.
6. **Kỹ năng chỉ có trong mục "Kỹ năng"** mà không xuất hiện ở kinh nghiệm hay dự án thì vẫn tính là có, nhưng là bằng chứng yếu. Dùng quy tắc 1 khi nó quyết định giữa hai mức.
7. **Chuyển ngành:** CV có khóa học hoặc dự án cá nhân đúng nghề, nhưng kinh nghiệm đi làm thuộc nghề khác. Với JD Fresher hoặc Junior thì nhãn tối đa là 2; với JD Mid trở lên thì nhãn tối đa là 1.
8. **Một tin tuyển nhiều vị trí** (ví dụ "Tuyển Backend và Frontend") thì chấm theo vị trí hợp với CV nhất.
9. **Ngôn ngữ của văn bản không ảnh hưởng.** CV tiếng Việt gặp JD tiếng Anh vẫn chấm bình thường. Chỉ khi JD ghi tiếng Anh là must thì mới xét tiếng Anh như một kỹ năng.
10. **JD quá ngắn**, chỉ có tiêu đề và số năm, không có danh sách yêu cầu: chấm theo câu 1 và câu 2, và **nhãn tối đa là 2**, vì không kiểm được câu 3. Hiện bộ TopCV chưa có cột mô tả (xem `reports/profiling_topcv.md`), nên quy tắc này sẽ gặp nhiều cho tới khi có mô tả đầy đủ.
11. **Không xét thông tin nhạy cảm:** tên, giới tính, năm sinh hay tuổi, ảnh, quê quán, tình trạng hôn nhân. Nếu JD có yêu cầu về giới hay tuổi thì bỏ qua yêu cầu đó khi chấm.
12. **Chưa xét lương và địa điểm trong v0.** Nếu bạn thấy chúng làm đổi nhãn, ghi vào ghi chú (xem mục 8).
13. **Chỉ dùng văn bản của CV và JD.** Không tra thêm thông tin về công ty, không xem điểm, thứ hạng hay hệ thống nào đã gợi ý cặp này. Trang gán nhãn (US-12.05) sẽ ẩn các thông tin đó.
14. **Hai JD giống hệt nội dung** (tin đăng lại) thì phải cùng nhãn.

## 7. Ghi một nhãn

Mỗi cặp là một dòng JSONL. Schema sẽ được chốt cùng trang gán nhãn (US-12.05); bản nháp như sau:

```json
{"cv_id": "P1", "job_id": "topcv_0123", "label": 2, "annotator": "thinh", "ts": "2026-11-27T09:15:00+07:00", "note": "phân vân 2/3: thiếu Docker"}
```

`note` có thể để trống. Nên ghi note khi dùng quy tắc 1, quy tắc 10 hoặc quy tắc 12.

## 8. Câu hỏi mở để chốt v1

Nhờ Duy và Tùng góp ý trực tiếp vào PR:

1. Lương và địa điểm: có nên đưa vào nhãn không? Ví dụ CV ghi "chỉ làm ở Hà Nội" mà JD ở TP.HCM.
2. Thừa cấp (quy tắc 3): cho 1 có quá nặng không, hay nên cho 2?
3. Ranh giới giữa 2 và 3 khi thiếu đúng 1 must phụ: cần định nghĩa "must phụ" chặt hơn không?
4. Quy tắc 10 (JD chỉ có tiêu đề): có nên bỏ các JD này khỏi pool gán nhãn thay vì giới hạn ở 2 không?
5. Bảng bậc cấp ở câu 2 có khớp với cách ranker tính điểm kinh nghiệm X (US-06.02) không?
