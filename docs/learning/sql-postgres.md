# SQL + PostgreSQL 16 + pgvector (spike TASK-U006)

- Người học: Tùng · Sprint: 1
- Mã nguồn: `sql/practice.sql` (chỉ để học, dữ liệu tự viết; schema thật làm ở task khác)
- Môi trường: Windows, Docker, image `pgvector/pgvector:pg16`

## Chạy thử

    docker run -d --name pgtest -e POSTGRES_PASSWORD=pw -p 5433:5432 pgvector/pgvector:pg16
    docker exec -i pgtest psql -U postgres < sql\practice.sql

File chạy lại được nhiều lần vì mở đầu bằng `DROP TABLE IF EXISTS`.

## 10 truy vấn và kết quả

### Q1. INNER JOIN: tin có công ty và lương từ 35 triệu

```sql
SELECT j.job_id, j.title, c.name AS company, j.salary_min_million
FROM job AS j
JOIN company AS c ON c.company_id = j.company_id
WHERE j.salary_min_million >= 35
ORDER BY j.salary_min_million DESC, j.job_id;
```

```text
job_id |         title         |   company   | salary_min_million
--------+-----------------------+-------------+--------------------
      9 | ML Engineer           | Gamma Data  |                 45
      2 | Senior Java Developer | Alpha Tech  |                 40
     12 | DevOps Engineer       | Delta Cloud |                 38
     13 | Cloud Engineer        | Delta Cloud |                 38
      8 | Data Engineer         | Gamma Data  |                 35
(5 rows)
```

### Q2. LEFT JOIN: giữ cả tin chưa gắn công ty

```sql
SELECT j.job_id, j.title, COALESCE(c.name, '(chưa có công ty)') AS company
FROM job AS j
LEFT JOIN company AS c ON c.company_id = j.company_id
WHERE j.posted_at >= '2026-10-22'
ORDER BY j.job_id;
```

```text
job_id |        title        |      company
--------+---------------------+-------------------
     14 | IT Helpdesk         | Delta Cloud
     18 | Business Analyst    | Epsilon Labs
     19 | Fullstack Developer | (chưa có công ty)
     20 | IT Sales            | (chưa có công ty)
(4 rows)
```

### Q3. Anti-join: công ty chưa có tin nào

```sql
SELECT c.company_id, c.name
FROM company AS c
LEFT JOIN job AS j ON j.company_id = c.company_id
WHERE j.job_id IS NULL
ORDER BY c.company_id;
```

```text
company_id |     name
------------+--------------
          6 | Zeta Startup
(1 row)
```

### Q4. GROUP BY: số tin theo thành phố

```sql
SELECT city, COUNT(*) AS n_jobs
FROM job
GROUP BY city
ORDER BY n_jobs DESC, city;
```

```text
city     | n_jobs
-------------+--------
 Hà Nội      |      9
 Hồ Chí Minh |      8
 Đà Nẵng     |      3
(3 rows)
```

### Q5. GROUP BY + HAVING: công ty từ 3 tin và lương trung bình

```sql
SELECT
    c.name AS company,
    COUNT(*) AS n_jobs,
    COUNT(j.salary_min_million) AS n_with_salary,
    ROUND(AVG(j.salary_min_million), 1) AS avg_salary
FROM job AS j
JOIN company AS c ON c.company_id = j.company_id
GROUP BY c.name
HAVING COUNT(*) >= 3
ORDER BY avg_salary DESC, company;
```

```text
company    | n_jobs | n_with_salary | avg_salary
--------------+--------+---------------+------------
 Gamma Data   |      4 |             3 |       36.0
 Delta Cloud  |      3 |             3 |       29.0
 Alpha Tech   |      4 |             3 |       24.0
 Beta Soft    |      3 |             3 |       21.7
 Epsilon Labs |      4 |             4 |       20.5
(5 rows)
```

### Q6. GROUP BY + HAVING + FILTER: nhóm nghề có tin từ 30 triệu

```sql
SELECT
    job_group,
    COUNT(*) AS n_jobs,
    COUNT(*) FILTER (WHERE salary_min_million >= 30) AS n_from_30m
FROM job
GROUP BY job_group
HAVING COUNT(*) FILTER (WHERE salary_min_million >= 30) >= 1
ORDER BY n_from_30m DESC, job_group;
```

```text
job_group   | n_jobs | n_from_30m
---------------+--------+------------
 data_ai       |      4 |          2
 infra_support |      3 |          2
 software_dev  |      6 |          2
(3 rows)
```

### Q7. ROW_NUMBER: top 2 lương trong mỗi công ty

```sql
SELECT company, title, salary_min_million, rn
FROM (
    SELECT
        c.name AS company,
        j.title,
        j.salary_min_million,
        ROW_NUMBER() OVER (
            PARTITION BY c.company_id
            ORDER BY j.salary_min_million DESC NULLS LAST, j.job_id
        ) AS rn
    FROM job AS j
    JOIN company AS c ON c.company_id = j.company_id
) AS ranked
WHERE rn <= 2
ORDER BY company, rn;
```

```text
company    |         title         | salary_min_million | rn
--------------+-----------------------+--------------------+----
 Alpha Tech   | Senior Java Developer |                 40 |  1
 Alpha Tech   | Java Developer        |                 20 |  2
 Beta Soft    | Python Developer      |                 25 |  1
 Beta Soft    | Automation Tester     |                 22 |  2
 Delta Cloud  | DevOps Engineer       |                 38 |  1
 Delta Cloud  | Cloud Engineer        |                 38 |  2
 Epsilon Labs | Mobile Developer      |                 24 |  1
 Epsilon Labs | Business Analyst      |                 23 |  2
 Gamma Data   | ML Engineer           |                 45 |  1
 Gamma Data   | Data Engineer         |                 35 |  2
(10 rows)
```

### Q8. ROW_NUMBER: 2 tin mới nhất ở mỗi thành phố

```sql
WITH ranked AS (
    SELECT
        city,
        title,
        posted_at,
        ROW_NUMBER() OVER (PARTITION BY city ORDER BY posted_at DESC, job_id DESC) AS rn
    FROM job
)
SELECT city, title, posted_at, rn
FROM ranked
WHERE rn <= 2
ORDER BY city, rn;
```

```text
    city     |        title        | posted_at  | rn
-------------+---------------------+------------+----
 Đà Nẵng     | QC Engineer         | 2026-10-19 |  1
 Đà Nẵng     | Frontend Developer  | 2026-10-18 |  2
 Hà Nội      | Fullstack Developer | 2026-10-24 |  1
 Hà Nội      | Business Analyst    | 2026-10-23 |  2
 Hồ Chí Minh | IT Sales            | 2026-10-25 |  1
 Hồ Chí Minh | IT Helpdesk         | 2026-10-22 |  2
(6 rows)
```

### Q9. CREATE EXTENSION: bật pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;

SELECT extname FROM pg_extension WHERE extname = 'vector';

CREATE TABLE job_embedding (
    job_id INT PRIMARY KEY REFERENCES job (job_id),
    embedding vector(3) NOT NULL
);

INSERT INTO job_embedding (job_id, embedding) VALUES
    (1, '[0.90, 0.10, 0.00]'),
    (2, '[0.95, 0.05, 0.00]'),
    (5, '[0.70, 0.30, 0.10]'),
    (8, '[0.10, 0.90, 0.20]'),
    (9, '[0.05, 0.95, 0.30]'),
    (12, '[0.20, 0.20, 0.90]');
```

```text
CREATE EXTENSION
 extname
---------
 vector
(1 row)

CREATE TABLE
INSERT 0 6
```

### Q10. <=>: 3 tin gần vector truy vấn nhất theo cosine distance

```sql
SELECT
    j.job_id,
    j.title,
    ROUND((e.embedding <=> '[1, 0, 0]')::numeric, 4) AS cosine_distance
FROM job_embedding AS e
JOIN job AS j ON j.job_id = e.job_id
ORDER BY e.embedding <=> '[1, 0, 0]', j.job_id
LIMIT 3;
```

```text
job_id |         title         | cosine_distance
--------+-----------------------+-----------------
      2 | Senior Java Developer |          0.0014
      1 | Java Developer        |          0.0061
      5 | Python Developer      |          0.0887
(3 rows)
```

## Lỗi đã gặp

<!-- Tự chạy 3 lệnh dưới đây trên container, rồi dán đúng thông báo lỗi và ghi cách sửa. -->

1. **Cột trong SELECT thiếu ở GROUP BY.**

   `SELECT city, title, COUNT(*) FROM job GROUP BY city;`

   Lỗi: `column "job.title" must appear in the GROUP BY clause or be used in an aggregate function`. Sửa: thêm `title` vào `GROUP BY` hoặc dùng hàm tổng hợp.

2. **Dùng alias của window function trong WHERE.**

   `SELECT title, ROW_NUMBER() OVER (ORDER BY job_id) AS rn FROM job WHERE rn <= 2;`

   Lỗi: `column "rn" does not exist`. Sửa: tính `rn` trong subquery hoặc CTE rồi lọc ở ngoài, như Q7 và Q8.

3. **So sánh vector khác số chiều.**

   `SELECT embedding <=> '[1,0]' FROM job_embedding;`

   Lỗi: `different vector dimensions 3 and 2`. Sửa: vector truy vấn phải có cùng số chiều với cột.

## Bẫy không báo lỗi

- **`ORDER BY ... DESC` đưa NULL lên đầu.** Top 1 lương của Alpha Tech sẽ là tin chưa có lương. Q7 dùng `DESC NULLS LAST`.
- **`AVG` bỏ qua NULL.** Q5 cho thấy Alpha Tech có 4 tin nhưng chỉ 3 tin được tính lương trung bình.
- **`ROW_NUMBER` với giá trị bằng nhau.** Delta Cloud có hai tin cùng 38 triệu; thêm `job_id` vào `ORDER BY` để kết quả ổn định.
- **Lọc bảng bên phải của LEFT JOIN trong WHERE** làm mất các dòng không khớp, nên kết quả giống INNER JOIN. Muốn giữ các dòng đó, đặt điều kiện trong `ON`.
- **Thứ tự chuỗi phụ thuộc collation.** Cùng một `ORDER BY city`, môi trường khác có thể xếp `Đà Nẵng` ở vị trí khác. Không nên để test hoặc logic phụ thuộc vào thứ tự chuỗi khi chưa chỉ định collation.
