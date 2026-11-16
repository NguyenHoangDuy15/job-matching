# S2-D07: F1 trích xuất kỹ năng lần 1 trên 50 JD

Ngày 15/11/2026 · Issue #457 (US-10 #401) · Phụ thuộc: S2-D04 (nhãn mức từng lần nhắc), S2-D05 (kiểm tay 14 tin production)

Bộ trích được chấm: Tầng 1 (từ điển + FlashText) và luật mức, phiên bản `dict-83913672+rules-v1-eb5abe00+jev_local_v1`. Tập JD là 50 tin trong `data/eval/jd_gold.jsonl`, lấy đủ 8 kiểu trình bày (topcv 9, vietnamworks 8, itviec_en 7, itviec_vi 7, numbered_caps 6, inline 5, markdown 5, unseen 3).

## Kết quả

**Tiêu chí "xong" của issue:** tập 50 JD có nhãn chuẩn và chỉ số F1 lưu trong repo.

- Nhãn chuẩn: `tests/fixtures/jd_gold/skills_gold.csv` (597 thẻ, chỉ có `jd_id`, kỹ năng, mức, nguồn; không có câu JD)
- Số liệu: `reports/eval_extraction_lan1.json`

```
$ uv run python scripts/evaluate_extraction.py score
Thẻ máy 396 · thẻ chuẩn 597 (394 từ gold D04 + 203 bỏ sót bổ sung)
Chỉ kỹ năng:   P 0.995  R 0.66  F1 0.794
Kỹ năng + mức: P 0.982  R 0.652  F1 0.783
Macro-F1 theo JD: 0.707
Bỏ sót theo nguyên nhân: {'co_trong_tu_dien_khong_bat_duoc': 68, 'ngoai_tu_dien': 135}
```

| Chỉ số (micro, đơn vị là cặp JD + kỹ năng) | Precision | Recall | **F1** |
|---|---|---|---|
| Chỉ kỹ năng | 0,995 (394/396) | 0,660 (394/597) | **0,794** |
| Kỹ năng + đúng mức bắt buộc/ưu tiên | 0,982 (389/396) | 0,652 (389/597) | **0,783** |
| Macro-F1 theo JD (trung bình 49 JD có thẻ chuẩn) | | | 0,707 |

| Nhóm JD | JD | P | R | F1 |
|---|---|---|---|---|
| Việc IT | 29 | 0,994 | 0,715 | 0,832 |
| Không phải IT (thiết kế, bán hàng, khác) | 21 | 1,000 | 0,442 | 0,613 |

| Kiểu trình bày | P | R | F1 |
|---|---|---|---|
| inline | 1,000 | 0,787 | 0,881 |
| vietnamworks | 0,975 | 0,705 | 0,819 |
| topcv | 1,000 | 0,667 | 0,800 |
| markdown | 1,000 | 0,636 | 0,778 |
| unseen | 1,000 | 0,636 | 0,778 |
| itviec_vi | 1,000 | 0,625 | 0,769 |
| itviec_en | 1,000 | 0,612 | 0,759 |
| numbered_caps | 1,000 | 0,605 | 0,754 |

**Kết luận:** thẻ máy gắn gần như luôn đúng. F1 bị kéo xuống bởi recall. Hai phần ba số bỏ sót là kỹ năng chưa có trong từ điển, và gần một nửa số đó nằm ở tin không phải IT. Một phần ba còn lại là kỹ năng đã có trong từ điển nhưng JD viết theo cách alias chưa có. Nếu bộ trích bắt được hết các kỹ năng đã có trong từ điển, F1 lên **0,871** (R 0,774) mà không cần thêm kỹ năng mới. Kiểu trình bày gần như không ảnh hưởng: chênh lệch giữa các kiểu đến từ nội dung tin, không phải từ việc tách mục.

## Cách tạo nhãn chuẩn

Thẻ chuẩn của một JD = (a) + (b):

- **(a) 394 thẻ** lấy từ `data/eval/gold_mentions.csv` của S2-D04: mỗi lần nhắc kỹ năng mà máy tìm thấy đã được người gán cho mức `required` / `preferred` / `mentioned` / `drop`. Gộp về mức cao nhất cho mỗi cặp (JD, kỹ năng), giữ cặp có mức `required` hoặc `preferred`.
- **(b) 203 thẻ** từ `data/eval/bo_sot.csv`: đọc phần Yêu cầu và Ưu tiên của từng JD, ghi kỹ năng JD yêu cầu mà máy chưa gắn thẻ. Có 241 dòng, trong đó 38 dòng script bỏ qua vì tên đó là alias của một kỹ năng máy đã gắn (xem mục "Đã gắn, nhưng dưới tên chuẩn khác").

Quy ước khi ghi (b): có ghi công nghệ, công cụ, phương pháp, nghiệp vụ, chứng chỉ, ngoại ngữ cụ thể, kỹ năng mềm có tên rõ ràng (làm việc nhóm, thuyết trình...). Không ghi phẩm chất chung (chủ động, chịu áp lực), bằng cấp chung, số năm kinh nghiệm đứng một mình, và kỹ năng chỉ nằm ở phần Mô tả hoặc Quyền lợi. Câu có "ưu tiên / lợi thế / is a plus" hoặc nằm ở mục Ưu tiên thì ghi `preferred`.

**Giới hạn của nhãn (b):** phần bỏ sót được điền bằng trợ lý AI đọc `bo_sot_jd.md` theo quy ước trên, chưa có người thứ hai kiểm chéo. Ranh giới "kỹ năng" và "phẩm chất" (ví dụ "tư duy chiến lược", "bất động sản") là chỗ dễ lệch nhất. Recall đo được phụ thuộc trực tiếp vào chỗ này: bỏ 13 dòng thuộc nhóm kinh doanh và 17 dòng nghiệp vụ ngành thì recall lên khoảng 0,69.

## Lỗi điển hình

### 1. Bỏ sót: kỹ năng chưa có trong từ điển (135 thẻ, 66% số bỏ sót)

| Nhóm | Thẻ | Ví dụ (JD) |
|---|---|---|
| Thiết kế, dựng phim, marketing | 40 | After Effects, Premiere Pro (vj_023, vj_036, vj_045); Houdini, Maya, Nuke (vj_008); InDesign, CapCut, Canva (vj_036); "thiết kế đồ họa", "dựng video" (4 JD mỗi loại) |
| Công cụ IT | 26 | Chef, Puppet (vj_003); Patroni, pgBackRest, Debezium (vj_046); CloudTrail, GuardDuty (vj_020); CloudFront, Route 53 (vj_034); Jamf (vj_005); ZeroMQ, ROS (vj_024) |
| Phương pháp, nghiệp vụ IT | 23 | SDLC (vj_021, vj_033); UAT (vj_016); User Research, Design Thinking (vj_011); quản trị hệ thống (vj_018, vj_034); High Availability (vj_046) |
| Nghiệp vụ ngành | 17 | bất động sản (4 JD thiết kế); chứng khoán (vj_012); T24 (vj_004); MISA, FAST (vj_049); BIM, GIS (vj_044) |
| Chứng chỉ | 15 | CBAP, PMI-PBA, CCBA (vj_004, vj_044); MCSA, MCSE, MCITP, LPIC-1 (vj_005, vj_018); NIST 800-53, CIS Benchmark (vj_020) |
| Bán hàng, kinh doanh | 13 | bán hàng (vj_009, vj_022, vj_042); B2B Sales, Business Development (vj_014, vj_017); SaaS (vj_017) |
| Ngoại ngữ | 1 | tiếng Pháp (vj_043) |

Tên ngoài từ điển gặp nhiều nhất: dựng video, thiết kế đồ họa, bất động sản, After Effects (4 JD mỗi tên); bán hàng, tư duy chiến lược, Premiere Pro (3).

### 2. Bỏ sót: kỹ năng có trong từ điển nhưng không bắt được (68 thẻ, 34%)

57 thẻ máy không nhận ra; 11 thẻ máy nhận ra nhưng gắn mức `mentioned` nên không hiện thẻ.

| Nguyên nhân | Thẻ | Ví dụ (JD: câu trong JD → kỹ năng) |
|---|---|---|
| Cách viết chưa có trong alias, chủ yếu kỹ năng mềm và tiếng Anh | 35 | "work as part of a team", "kỹ năng làm việc theo nhóm", "làm việc độc lập và theo nhóm" → Làm việc nhóm (**7 JD**); "self-learn new technologies", "tự tìm hiểu tài liệu", "chủ động học hỏi công nghệ mới" → Tự học (4); "mentor a team", "hướng dẫn BA junior" → Mentoring; "influence stakeholders" → Stakeholder Management; "xây dựng kịch bản kiểm thử" → Test Case Design; "viết tài liệu HDSD" → Technical Documentation (3); "recommendation systems" → Recommender Systems; "tuning performance" → Query Optimization; "load balancers" → Nginx |
| Viết tắt | 9 | "Ps, Ai, Pr" (vj_023), "PTS - Ai" (vj_040), "AI, InDesign" (vj_047: AI là Illustrator) → Photoshop, Illustrator; "BA" → Phân tích nghiệp vụ (vj_033); "S3, RDS, Lambda" sau "AWS:" (vj_034) |
| Hai kỹ năng viết dính bằng dấu "/" | 4 | "Agile/Scrum" chỉ ra Agile (vj_012, vj_015, vj_021, vj_039). Nguyên nhân: `agile/scrum` đang là alias của Agile, nên FlashText khớp cả cụm và Scrum mất |
| JD viết sai chính tả | 4 | "ISTBQ" → ISTQB (vj_004); "Kubenetes" → Kubernetes, "GRP" → gRPC (vj_026); "Unreal.." → Unreal Engine (vj_008) |
| Tên chỉ có dạng gần đúng | 4 | "Shell" → Bash, "Windows 2012/2016" → Windows Server (vj_018); "IAM" → IAM & SSO (vj_020); "Word" → Tin học văn phòng (vj_026) |
| Luật ngữ cảnh chặn từ nhập nhằng | 1 | "AI" trong "kinh nghiệm trong các dự án về AI" (vj_031) không thành thẻ Trí tuệ nhân tạo |
| Nhận ra nhưng gắn `mentioned` | 11 | "Business Analyst" ở câu kinh nghiệm (vj_012, vj_037, vj_041); "Data Analyst" ở mục Ưu tiên (vj_000); "QC/QA", "Automation" (vj_021) |

### 3. Đã gắn, nhưng dưới tên chuẩn khác (38 dòng, không tính là bỏ sót)

Từ điển đang gộp các tên này vào một kỹ năng cha, nên khi người đọc ghi tên cụ thể thì script thấy máy đã có thẻ. Đây là cùng hiện tượng D05 ghi nhận ở 11% số mục "thiếu".

| Tên JD ghi | Thẻ máy |
|---|---|
| SAP, SAP S/4HANA, SAP FICO, Microsoft Dynamics | ERP |
| Visio, BPMN, Miro, Draw.io | UML |
| macOS | Windows |
| Unix | Linux |
| CCNA, CCNP | Cisco |
| qTest | TestRail |
| Nagios | Zabbix |
| GitOps | Argo CD |
| LDAP | Active Directory |
| Salesforce | CRM |
| "lập kế hoạch" | Quản lý thời gian |
| IT Helpdesk | Phần cứng máy tính |

Một số gộp hợp lý (CCNA → Cisco), một số làm thẻ hiện sai tên với tin (macOS → Windows, Visio → UML, LDAP → Active Directory). Cách chấm hiện tại không phạt các trường hợp này, nên F1 0,794 hơi lạc quan với người xem thẻ.

### 4. Thẻ sai (2/396)

| JD | Thẻ | Máy khớp từ | Vì sao sai |
|---|---|---|---|
| vj_025 | Machine Learning | "Khoa **học Máy** tính" | Alias "học máy" khớp giữa cụm "khoa học máy tính" |
| vj_024 | Lãnh đạo | "represent ... to the **leadership** team" | Nhắc ban lãnh đạo, không phải yêu cầu kỹ năng lãnh đạo |

Lỗi "Khoa học máy tính" còn xuất hiện ở **vj_013** và **vj_046**, nhưng nhãn D04 ở hai câu đó lại ghi `required` nên script tính là thẻ đúng. Ở vj_026, câu này làm thẻ Machine Learning thành `required` trong khi JD chỉ nêu học máy ở mục Ưu tiên. Sửa nhãn D04 cho ba câu này thì precision còn 0,990 (392/396) và F1 0,791. Nhãn D04 nằm trong `data/eval/gold_mentions.csv` (không lên git); báo cáo này chưa sửa file đó.

### 5. Sai mức (5 thẻ trong 394 thẻ đúng)

| JD | Thẻ | Máy | Chuẩn | Nguyên nhân |
|---|---|---|---|---|
| vj_002 | Photoshop, Illustrator | preferred | required | Cả mục Yêu cầu là một đoạn liền bắt đầu bằng "Ưu tiên tốt nghiệp...", luật mức áp "ưu tiên" cho cả đoạn |
| vj_020 | Terraform, CloudFormation | preferred | required | "Có khả năng triển khai IaC (Terraform, CloudFormation), CI/CD security là lợi thế": "là lợi thế" thuộc về CI/CD security nhưng máy áp cho cả câu |
| vj_047 | Photoshop | required | preferred | "Sử dụng thành thạo photoshop, biết ... AI, InDesign là lợi thế": nhãn D04 ghi preferred, nhưng theo câu thì Photoshop là bắt buộc. Có thể nhãn D04 sai |

## Đối chiếu với 14 tin production (S2-D05)

| | D05: 14 tin production | D07: 50 JD tập gold |
|---|---|---|
| Phiên bản gắn thẻ | `…rules-v1-eb5abe00+no-model` | `…rules-v1-eb5abe00+jev_local_v1` |
| Độ chính xác thẻ | 94,3% (99/105) | 99,5% (394/396) |
| Đúng mức trong các thẻ đúng | 99,0% | 98,7% (389/394) |
| Độ phủ | 44,0% (xấp xỉ) | 66,0% |
| Bỏ sót do ngoài từ điển | 63% | 66% |
| Bỏ sót do có trong từ điển nhưng không bắt được | 3% bộ trích + 4% gắn `mentioned` | 34% (28% bộ trích + 6% `mentioned`) |
| Bỏ sót do nội dung tin bị cắt | 17% (VietnamWorks) | 0% (tập gold có nội dung đầy đủ) |

- **Precision chênh** vì 6 thẻ sai ở D05 đều do alias quá rộng (Solid, thiết kế hệ thống, SSL...). 50 JD này ít gặp các từ đó. Lỗi cùng loại vẫn có ở đây: "học máy" trong "khoa học máy tính".
- **Độ phủ chênh** vì D05 có 17% mục thiếu do VietnamWorks bị cắt nội dung, và người kiểm D05 ghi cả kỹ năng ở phần Mô tả. Bỏ hai yếu tố đó, hai lần đo cùng kết luận: nguyên nhân lớn nhất là từ điển, và tin không phải IT kéo độ phủ xuống mạnh (D07: 0,44 so với 0,72 ở tin IT).
- **Phần "bắt không được" ở D07 lớn hơn nhiều so với D05** (34% so với 7%) vì ở D07 người đọc so từng câu với từ điển. Ở D05, nhiều trường hợp như "làm việc theo nhóm" có thể đã bị bỏ qua hoặc xếp vào nhóm "ngoài từ điển". Đây là phần sửa rẻ nhất: chỉ cần thêm alias.

## Việc cần làm ở sprint sau

| Việc | Người | Ảnh hưởng ước tính |
|---|---|---|
| Thêm alias cho kỹ năng mềm và cách viết tiếng Anh/Việt phổ biến: "work as part of a team", "làm việc theo nhóm", "self-learn", "tự tìm hiểu", "mentor", "kịch bản kiểm thử", "viết tài liệu"... | Duy (S2-D08) | Khoảng 35 thẻ; cùng các việc bên dưới, F1 lên tới 0,871 |
| Bỏ `agile/scrum` khỏi alias Agile, cho FlashText ra cả hai kỹ năng; kiểm các alias dính "/" khác (`html/css`, `sass/scss`) | Duy (S2-D08) | 4 thẻ Scrum |
| Bắt viết tắt theo ngữ cảnh: Ps / Ai / Pr / Ae / PTS khi đứng cạnh nhau hoặc cạnh "phần mềm thiết kế"; "BA" khi có ngữ cảnh phân tích nghiệp vụ; dịch vụ con sau "AWS:" | Duy (S2-D08) | 9 thẻ |
| Chặn "học máy" khi nằm trong "khoa học máy tính"; chặn "leadership team" | Duy (S2-D08) | 2 thẻ sai đã đếm + 2 thẻ đang bị nhãn D04 tính là đúng |
| Sửa nhãn D04 cho câu "Khoa học máy tính" ở vj_013, vj_026, vj_046 rồi chấm lại | Duy | Số liệu sạch hơn cho lần 2 |
| Thêm kỹ năng IT hay gặp chưa có: Chef, Puppet, SDLC, UAT, Patroni, CloudTrail, GuardDuty, CloudFront, Route 53, chứng chỉ CBAP / PMI-PBA / MCSA / LPIC | Duy (S2-D08) | Khoảng 25 thẻ |
| Tách các gộp làm thẻ hiện sai tên: macOS ≠ Windows, Visio / Draw.io / Miro ≠ UML, LDAP ≠ Active Directory, SAP thành kỹ năng riêng (con của ERP) | Duy (S2-D08) | Nối tiếp việc tách gộp của D05 |
| Luật mức: chỉ áp "là lợi thế" cho vế đứng ngay trước nó, không áp cho cả câu; đoạn Yêu cầu liền một khối bắt đầu bằng "Ưu tiên" thì tách câu trước khi gán mức | Duy | 4 thẻ sai mức |
| Quyết định phạm vi từ điển với tin thiết kế và bán hàng (40 + 13 thẻ bỏ sót). D05 đã nêu, D07 xác nhận: tin không phải IT có recall 0,44 | Cả nhóm | Lọc ở crawler, hoặc mở rộng từ điển sang nhóm thiết kế / dựng phim |
| Người thứ hai kiểm chéo `bo_sot.csv` (ít nhất 10 JD) trước khi dùng `skills_gold.csv` làm mốc cho lần chấm 2 | Thịnh hoặc Tùng | Đo độ lệch giữa người gán |

## Cách chạy lại

```bash
uv run python scripts/evaluate_extraction.py score                       # ghi đè eval_extraction_lan1
uv run python scripts/evaluate_extraction.py score --name eval_extraction_lan2   # lần chấm sau khi sửa từ điển
```

File đầu vào `data/eval/bo_sot.csv` và `data/eval/gold_mentions.csv` có câu JD nên không lên git. Danh sách lỗi từng thẻ ở `data/eval/extraction_errors.csv`.
