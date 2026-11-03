-- Chạy tự động một lần khi volume pgdata còn trống.
CREATE EXTENSION IF NOT EXISTS vector;

-- vector(3) cho dễ tính tay; dự án thật dùng vector(1024) của bge-m3.
CREATE TABLE IF NOT EXISTS demo_item (
    id        serial PRIMARY KEY,
    name      text NOT NULL,
    embedding vector(3) NOT NULL
);

INSERT INTO demo_item (name, embedding) VALUES
    ('backend-python', '[1, 0, 0]'),
    ('backend-java',   '[0.9, 0.1, 0]'),
    ('frontend-react', '[0, 1, 0]'),
    ('data-engineer',  '[0.6, 0, 0.8]'),
    ('mobile-flutter', '[0, 0.7, 0.7]');
