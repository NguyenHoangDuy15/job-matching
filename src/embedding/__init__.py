"""Embedding tin tuyển dụng theo đoạn ≤ 300 token (S3-D07, EN-03) → core.job_chunks.

chunker:  tin → đoạn (summary + description/requirements/preferred), đếm token bằng tokenizer bge-m3
embedder: Embedder Protocol; Workers AI (bge-m3), chạy tại chỗ (sentence-transformers), Fake (test)
store:    chọn tin cần làm, ghi theo giao dịch, dọn tin đã đóng, báo cáo độ phủ
"""
