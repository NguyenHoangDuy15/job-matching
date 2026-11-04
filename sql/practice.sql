-- Spike TASK-U006: thực hành SQL trên PostgreSQL 16 + pgvector.
-- Toàn bộ dữ liệu là dữ liệu tự viết để học. Chạy lại nhiều lần vẫn cho cùng kết quả.

SET client_min_messages = warning;

DROP TABLE IF EXISTS job_embedding;
DROP TABLE IF EXISTS job;
DROP TABLE IF EXISTS company;

CREATE TABLE company (
    company_id INT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE job (
    job_id INT PRIMARY KEY,
    company_id INT REFERENCES company (company_id),
    title TEXT NOT NULL,
    job_group TEXT NOT NULL,
    city TEXT NOT NULL,
    salary_min_million INT,
    posted_at DATE NOT NULL
);

INSERT INTO company (company_id, name, city) VALUES
    (1, 'Alpha Tech', 'Hà Nội'),
    (2, 'Beta Soft', 'Hà Nội'),
    (3, 'Gamma Data', 'Hồ Chí Minh'),
    (4, 'Delta Cloud', 'Hồ Chí Minh'),
    (5, 'Epsilon Labs', 'Đà Nẵng'),
    (6, 'Zeta Startup', 'Đà Nẵng');

INSERT INTO job (job_id, company_id, title, job_group, city, salary_min_million, posted_at) VALUES
    (1, 1, 'Java Developer', 'software_dev', 'Hà Nội', 20, '2026-10-01'),
    (2, 1, 'Senior Java Developer', 'software_dev', 'Hà Nội', 40, '2026-10-05'),
    (3, 1, 'Manual Tester', 'qa_test', 'Hà Nội', 12, '2026-10-07'),
    (4, 1, 'Business Analyst', 'ba_pm', 'Hà Nội', NULL, '2026-10-09'),
    (5, 2, 'Python Developer', 'software_dev', 'Hà Nội', 25, '2026-10-02'),
    (6, 2, 'Data Analyst', 'data_ai', 'Hà Nội', 18, '2026-10-12'),
    (7, 2, 'Automation Tester', 'qa_test', 'Hà Nội', 22, '2026-10-15'),
    (8, 3, 'Data Engineer', 'data_ai', 'Hồ Chí Minh', 35, '2026-10-03'),
    (9, 3, 'ML Engineer', 'data_ai', 'Hồ Chí Minh', 45, '2026-10-08'),
    (10, 3, 'BI Developer', 'data_ai', 'Hồ Chí Minh', 28, '2026-10-20'),
    (11, 3, 'Project Manager', 'ba_pm', 'Hồ Chí Minh', NULL, '2026-10-21'),
    (12, 4, 'DevOps Engineer', 'infra_support', 'Hồ Chí Minh', 38, '2026-10-04'),
    (13, 4, 'Cloud Engineer', 'infra_support', 'Hồ Chí Minh', 38, '2026-10-16'),
    (14, 4, 'IT Helpdesk', 'infra_support', 'Hồ Chí Minh', 11, '2026-10-22'),
    (15, 5, 'Mobile Developer', 'software_dev', 'Đà Nẵng', 24, '2026-10-06'),
    (16, 5, 'Frontend Developer', 'software_dev', 'Đà Nẵng', 20, '2026-10-18'),
    (17, 5, 'QC Engineer', 'qa_test', 'Đà Nẵng', 15, '2026-10-19'),
    (18, 5, 'Business Analyst', 'ba_pm', 'Hà Nội', 23, '2026-10-23'),
    (19, NULL, 'Fullstack Developer', 'software_dev', 'Hà Nội', 30, '2026-10-24'),
    (20, NULL, 'IT Sales', 'it_sales', 'Hồ Chí Minh', 10, '2026-10-25');

\echo '=== Q1. INNER JOIN: tin có công ty và lương từ 35 triệu ==='
SELECT j.job_id, j.title, c.name AS company, j.salary_min_million
FROM job AS j
JOIN company AS c ON c.company_id = j.company_id
WHERE j.salary_min_million >= 35
ORDER BY j.salary_min_million DESC, j.job_id;

\echo '=== Q2. LEFT JOIN: giữ cả tin chưa gắn công ty ==='
SELECT j.job_id, j.title, COALESCE(c.name, '(chưa có công ty)') AS company
FROM job AS j
LEFT JOIN company AS c ON c.company_id = j.company_id
WHERE j.posted_at >= '2026-10-22'
ORDER BY j.job_id;

\echo '=== Q3. Anti-join: công ty chưa có tin nào ==='
SELECT c.company_id, c.name
FROM company AS c
LEFT JOIN job AS j ON j.company_id = c.company_id
WHERE j.job_id IS NULL
ORDER BY c.company_id;

\echo '=== Q4. GROUP BY: số tin theo thành phố ==='
SELECT city, COUNT(*) AS n_jobs
FROM job
GROUP BY city
ORDER BY n_jobs DESC, city;

\echo '=== Q5. GROUP BY + HAVING: công ty từ 3 tin và lương trung bình ==='
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

\echo '=== Q6. GROUP BY + HAVING + FILTER: nhóm nghề có tin từ 30 triệu ==='
SELECT
    job_group,
    COUNT(*) AS n_jobs,
    COUNT(*) FILTER (WHERE salary_min_million >= 30) AS n_from_30m
FROM job
GROUP BY job_group
HAVING COUNT(*) FILTER (WHERE salary_min_million >= 30) >= 1
ORDER BY n_from_30m DESC, job_group;

\echo '=== Q7. ROW_NUMBER: top 2 lương trong mỗi công ty ==='
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

\echo '=== Q8. ROW_NUMBER: 2 tin mới nhất ở mỗi thành phố ==='
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

\echo '=== Q9. CREATE EXTENSION: bật pgvector ==='
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

\echo '=== Q10. <=>: 3 tin gần vector truy vấn nhất theo cosine distance ==='
SELECT
    j.job_id,
    j.title,
    ROUND((e.embedding <=> '[1, 0, 0]')::numeric, 4) AS cosine_distance
FROM job_embedding AS e
JOIN job AS j ON j.job_id = e.job_id
ORDER BY e.embedding <=> '[1, 0, 0]', j.job_id
LIMIT 3;