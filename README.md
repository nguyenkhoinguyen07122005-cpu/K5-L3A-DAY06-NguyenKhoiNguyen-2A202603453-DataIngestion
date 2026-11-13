# Day 06 · Data Ingestion Engineering — bài nộp cá nhân

Corpus **6 Python Enhancement Proposals (PEP)** → chuẩn hóa → chia 111 đơn vị nguồn (≥ 1.500 ký tự) → 3 chiến lược chunk/filter → embedding thật (`sentence-transformers/all-MiniLM-L6-v2`, local) → **PostgreSQL + pgvector** → benchmark 25 câu (19 dev / 6 test) với trace top-3 và audit thủ công.

Đề bài gốc: [docs/ASSIGNMENT_README.md](docs/ASSIGNMENT_README.md) · Báo cáo: [report/individual/2A202603453_NguyenKhoiNguyen.md](report/individual/2A202603453_NguyenKhoiNguyen.md) · Bảng kết quả: [results/summary.md](results/summary.md)

## Kết quả chính (đã chạy 2026-11-13)

| Strategy | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 | Chunks | Coherence /2 | Grounding test /2 | Filter tuân thủ (dev, test) |
|---|---|---|---|---|---|---|---|---|
| A fixed 500/50 | 7/19 | 14/19 | 0/6 | 2/6 | 460 | 0.9 | 0.83 | 2/3, 1/2 |
| B paragraph ≤800 | 10/19 | 14/19 | 3/6 | 5/6 | 369 | 1.7 | 1.67 | 1/3, 1/2 |
| C = B + filter `pep_type` | 10/19 | 14/19 | 3/6 | 5/6 | 369 | 1.7 | 1.67 | 3/3, 2/2 |

Bộ test chỉ có 6 câu, nên các số trên chỉ minh họa cho corpus này, không dùng để kết luận chiến lược nào tốt nhất nói chung.

## Cấu trúc

```text
STUDENT.md                      thông tin học viên
README.md                       file này: setup, chạy, đường dẫn
starter/src/                    code pipeline (ingestion, chunking, embeddings, store, evaluation, run, corpus)
starter/scripts/                verify_benchmark.py, reingest_check.sh, summarize.py, gold_rank_diagnostic.py, fetch_corpus.py, check_setup.py
starter/data/raw/               6 file PEP .rst (public domain / CC0) — snapshot python/peps@155e5be
starter/data/corpus.json        danh sách tài liệu + commit snapshot
data/manifest.json              manifest: nguồn, giấy phép, accessed_at, 111 unit (ID, ranh giới, số ký tự)
benchmark/                      questions.jsonl (25 câu, gold + evidence + filter) và README (split, quy tắc chọn)
artifacts/experiment_log.csv    cấu hình + giả thuyết + kết quả A/B/C
results/                        ingest_stats, metrics_dev/test, traces_dev/test (top-3 đầy đủ), selection, reingest_check,
                                run_log, chunks_A/B, summary.md/json, diagnostic_gold_rank
results/audit/                  coherence_sample + coherence_labels, grounding_sheet + grounding_labels, metadata_check_test.csv
report/individual/              báo cáo cá nhân
```

## Cách chạy lại

Yêu cầu: Python 3.11–3.14, Docker (cho pgvector), khoảng 2 GB đĩa cho torch và model. Không cần API key; chi phí $0.

```bash
cd starter
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                                       # EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py                              # -> Setup OK

python scripts/verify_benchmark.py      # 1. kiểm chứng evidence của benchmark (trước khi truy xuất)
python -m src.run ingest                # 2. corpus -> unit -> chunk A/B -> embedding -> pgvector (A, B, C)
bash scripts/reingest_check.sh          # 3. nạp lại cùng phiên bản + mô phỏng tài liệu thay đổi (PY=python)
python -m src.run benchmark --split dev # 4. trace + Hit@1/Hit@3 trên dev
python -m src.run select                # 5. chọn chiến lược theo quy tắc chốt trước (chỉ dùng dev)
python -m src.run benchmark --split test # 6. chạy test một lần
python -m src.run audit-prep            # 7. tạo bảng mẫu coherence / grounding / metadata
python scripts/summarize.py             # 8. gộp chỉ số + nhãn thủ công -> results/summary.md
```

`python -m src.run all` chạy liên tiếp các bước 2, 4, 5, 6 và 7. Nhãn thủ công nằm trong `results/audit/*_labels.csv`; code không sinh nhãn.

Nếu không tải được model từ Hugging Face, đặt `EMBEDDING_MODEL=<thư mục local>` chứa đúng các file của model. SHA-256 của `model.safetensors` đã dùng: `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`. Vector của câu "Hello world" đã được đối chiếu với vector tham chiếu công bố cho model này (`[-0.034477, 0.031023, 0.006735, 0.026109, -0.039362, …]`).

## Môi trường của lần chạy đã báo cáo

- Linux container, 2 vCPU, không có GPU. Python 3.13.18, sentence-transformers 6.3.0, transformers 5.22.2, torch 2.15.0, psycopg 3.3.8, pgvector-python 0.5.1.
- PostgreSQL 16.15 + pgvector **0.6.0**. Môi trường chạy không có Docker daemon, nên dùng PostgreSQL cài cục bộ ở cổng 55433, cùng user/db/password như `docker-compose.yml`. Image Docker của starter dùng pgvector 0.8.7. Truy vấn là exact search (`ORDER BY embedding <=> q`, không có index ANN), nên kết quả không phụ thuộc phiên bản pgvector.
- Thời gian embed (CPU): A 6.23 s / 460 chunk, B 6.00 s / 369 chunk, C dùng lại vector của B. Truy vấn mất khoảng 2–3 ms/câu.

## Dữ liệu và quyền sử dụng

PEP 1, 8, 257, 498, 572, 636 lấy từ <https://github.com/python/peps> tại commit `155e5bee7d985ef30555b496eb994d24a591f70b` (truy cập 2026-11-13). Mỗi file có mục *Copyright* ghi "placed in the public domain" (PEP 1 và 636 ghi thêm "or under CC0-1.0-Universal"), nên được phép tái phân phối và gửi qua xử lý. Corpus không chứa dữ liệu cá nhân hay secret. `.env` nằm trong `.gitignore`.
