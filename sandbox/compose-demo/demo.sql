-- Chạy: docker compose -f sandbox/compose-demo/compose.yaml exec -T db psql -U demo -d demo < sandbox/compose-demo/demo.sql

-- 1. Extension đã bật chưa, phiên bản nào
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- 2. Ba toán tử khoảng cách (càng nhỏ càng gần)
--    <->  khoảng cách L2 (Euclid)
--    <=>  khoảng cách cosine = 1 - cosine similarity
--    <#>  tích vô hướng ÂM (-a·b), để ORDER BY tăng dần vẫn ra cái giống nhất
SELECT name,
       round((embedding <-> '[1, 0, 0]')::numeric, 4) AS l2,
       round((embedding <=> '[1, 0, 0]')::numeric, 4) AS cosine_dist,
       round((embedding <#> '[1, 0, 0]')::numeric, 4) AS neg_inner
FROM demo_item
ORDER BY id;

-- 3. Top-3 gần nhất theo cosine với một "CV" giả nghiêng backend + data
--    Đổi về similarity: 1 - (a <=> b)
SELECT name,
       round((1 - (embedding <=> '[0.8, 0, 0.6]'))::numeric, 4) AS cosine_sim
FROM demo_item
ORDER BY embedding <=> '[0.8, 0, 0.6]'
LIMIT 3;

-- 4. Sai số chiều bị từ chối (lỗi cố ý, xem docs/learning/docker-pgvector.md)
-- SELECT '[1, 0]'::vector(3);
