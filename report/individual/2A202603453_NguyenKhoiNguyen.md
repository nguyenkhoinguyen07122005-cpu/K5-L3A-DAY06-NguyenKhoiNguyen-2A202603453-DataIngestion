# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:** tài liệu đặc tả và quy ước của Python, gồm 6 PEP: PEP 1 (*PEP Purpose and Guidelines*, Process), PEP 8 (*Style Guide*, Process), PEP 257 (*Docstring Conventions*, Informational), PEP 498 (*f-strings*, Standards Track, 3.6), PEP 572 (*Assignment Expressions*, Standards Track, 3.8), PEP 636 (*Pattern Matching Tutorial*, Informational, 3.10). Nguồn là repo `github.com/python/peps`, snapshot commit `155e5bee7d98…` (2026-11-12), truy cập ngày 2026-11-13. Mục *Copyright* của từng file ghi "placed in the public domain" (PEP 1 và 636 ghi thêm CC0-1.0), nên được phép tái phân phối và đưa vào repo. File RST không có trang vật lý, vì vậy áp dụng quy tắc của GUIDE: bỏ header preamble và các mục chỉ chứa tài liệu tham khảo hoặc giấy phép (*Copyright*, *References*, *Footnotes*), chuẩn hóa văn bản, tách thành đoạn, rồi gộp các đoạn **theo thứ tự** thành đơn vị. Một đơn vị đóng lại ngay khi đạt **≥ 1.500 ký tự**; phần dư ngắn hơn được gộp vào đơn vị trước. Kết quả: **111 đơn vị** (PEP 1: 23, PEP 8: 28, PEP 257: 5, PEP 498: 14, PEP 572: 27, PEP 636: 14), đơn vị ngắn nhất 1.500 ký tự, tổng 185.650 ký tự. Không nhân bản nội dung. ID, ranh giới `char_start/char_end` và số ký tự của từng đơn vị nằm trong `data/manifest.json`. `page` của chunk là số thứ tự đơn vị trong tài liệu.
- **Chuẩn hóa, lỗi và giới hạn:** dùng Unicode NFC, chuyển CRLF thành LF, tab thành 4 dấu cách, bỏ NBSP/ZWSP/BOM và khoảng trắng cuối dòng, gộp từ 3 dòng trống trở lên. Heading RST (dòng tiêu đề và dòng gạch dưới) được đổi thành `#`/`##`/`###` để giữ cấu trúc. Các role `:pep:`, `:ref:`, `:file:`… được đổi thành chữ thường; link `` `text <url>`_ `` và ref chú thích `[1]_` bị bỏ. Directive `code-block`, `image`, `contents`, các link target và khối comment cuối file cũng bị bỏ. Lỗi và giới hạn được ghi nhận trong `results/run_log.jsonl` và `processing_log` của manifest:
  1. Sơ đồ trạng thái PEP trong PEP 1 là ảnh nên mất hẳn. Câu "The possible paths of the status of PEPs are as follows:" vì thế đứng trơ trọi.
  2. Còn sót vài marker RST hiếm như `Docutils_` và `Doc-SIG_`.
  3. Heading "References and Footnotes" của PEP 257 không khớp tên trong danh sách loại trừ nên được giữ lại, nhưng mục này rỗng.
  4. Hai lỗi chuẩn hóa ở bản đầu đã được phát hiện khi đọc corpus và sửa **trước khi** viết benchmark: regex xóa link `word_` làm hỏng `__future__`, và block bắt đầu bằng `\n` làm lệch `section`.
  Corpus không có trang rỗng và không cần OCR.
- **Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí:** `sentence-transformers/all-MiniLM-L6-v2` chạy local trên CPU qua sentence-transformers 6.3.0 (torch 2.15.0). Model có 384 chiều, mean pooling + L2-normalize, `max_seq_length` = 256 token; query và document mã hóa giống nhau, không dùng prefix. SHA-256 của `model.safetensors` là `53aa5117…d9db`; vector "Hello world" khớp vector tham chiếu công bố của model. Vector store là PostgreSQL 16.15 + pgvector 0.6.0, bảng `day6_chunks`, khóa chính `(strategy, chunk_id)`. Metric là cosine distance `<=>`, score = 1 − distance, **exact search** (không có index ANN). Filter được áp bằng SQL `WHERE` trước khi xếp hạng, giá trị truyền qua tham số, tên cột lấy từ whitelist. Lệnh chạy: `python -m src.run ingest | benchmark --split dev | select | benchmark --split test | audit-prep` (xem README). Chi phí **$0**. Thời gian trên container 2 vCPU: load model 3,9 s; embed A 6,23 s (460 chunk), B 6,00 s (369 chunk), C 0 s vì dùng lại vector của B; ghi DB khoảng 0,06 s mỗi strategy; truy vấn 1,6–3,1 ms/câu.
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:** trường bắt buộc gồm `document_id` (vd `pep-0008`), `source` (`python/peps@155e5bee7d98:peps/pep-0008.rst`), `page` (int, số đơn vị) và `unit_id` (`pep-0008:u18`). Thêm `char_start/char_end` (int, offset trong văn bản đã chuẩn hóa) để truy vết chính xác. Trường lọc: **`pep_type`** (text: `Process` / `Informational` / `Standards Track`), lấy nguyên từ header `Type:` của từng file, không suy đoán. Trường này được chọn vì đó là cách người đọc PEP thực sự duyệt (theo danh mục), mỗi giá trị phủ đúng 2 tài liệu nên filter không làm lộ gold, và nó tách được các chủ đề trùng từ vựng (docstring có trong PEP 8 và PEP 257; "wildcard" có trong import của PEP 8 và pattern của PEP 636). Các trường phụ: `status` và `python_version` (từ header; để `NULL` khi header không có, không đoán), `created_year` (từ `Created:`), `section` (đường dẫn heading tại vị trí đầu chunk).

## Cấu hình và benchmark

- **A / B / C:**
  - **A:** cửa sổ ký tự cố định 500, overlap 50, cắt trong phạm vi từng đơn vị; không lọc.
  - **B:** chunk theo đoạn/heading. Heading luôn mở chunk mới và dính với nội dung sau nó; các đoạn liền nhau được gộp tới **800 ký tự** (giới hạn mềm, heading có thể làm vượt một chút); đoạn dài hơn 800 được tách theo dòng; không lọc. Mức 800 được chọn trước khi chạy để phần lớn chunk nằm dưới 256 token: thực tế chỉ 1/369 chunk vượt (273 token, bị model cắt đuôi).
  - **C:** dùng **đúng chunk và vector của B**, chỉ thêm `WHERE pep_type = <giá trị>` khi câu hỏi có filter. 20/25 câu không có filter nên C chạy y như B ở những câu đó.
  - A–B chỉ khác cách chunk; B–C chỉ khác việc lọc.
- **≥20 câu:** 25 câu, chia **19 dev / 6 test** trước khi chạy. Benchmark được đóng băng lúc 02:25:50Z với SHA-256 `b1d2df1d…dad9`; lần ingest đầu chạy lúc 02:28:53Z. Loại câu: 7 trực tiếp, 6 diễn đạt lại, 7 điều kiện/ngoại lệ, 5 cần metadata filter (3 dev: d17–d19; 2 test: t05, t06). Mỗi filter là ngữ cảnh duyệt danh mục do người dùng cung cấp trước khi truy xuất (`filter_context`), không lấy từ gold. Các câu filter được viết sao cho mơ hồ nếu không lọc. Dev và test chia theo **mục** (test dùng mục mà dev không chạm tới); các tài liệu vẫn xuất hiện ở cả hai split, nên có rủi ro rò rỉ về văn phong và từ vựng. Evidence được kiểm chứng bằng `scripts/verify_benchmark.py`: mỗi `evidence_quote`, kể cả alternative, phải là chuỗi con của đơn vị gold sau khi gộp khoảng trắng, giá trị filter phải tồn tại và gold phải nằm trong phạm vi filter. Kết quả 25/25 đạt (`results/benchmark_verification.json`). Có 7 câu ghi nhiều nguồn hợp lệ (`alternatives`).
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test:** (1) dev Evidence Hit@3 cao nhất → (2) dev Hit@1 → (3) ít chunk hơn (`benchmark/README.md`). Áp lên dev, **B và C hòa ở cả 3 tiêu chí** (14/19, 10/19, 369 chunk) và đều hơn A. Quy tắc không phân định được hòa, nên `selection.json` ghi B theo thứ tự cố định và kèm ghi chú hòa. Sau đó test được chạy **một lần**. Không có bước chỉnh sửa nào dựa trên test.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian (embed + ghi DB) | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 7/19 | 14/19 | 460 | 6,23 s + 0,07 s | $0 |
| A | test | 0/6 | 2/6 | 460 | (cùng index) | $0 |
| B | dev | 10/19 | 14/19 | 369 | 6,00 s + 0,06 s | $0 |
| B | test | 3/6 | 5/6 | 369 | (cùng index) | $0 |
| C | dev | 10/19 | 14/19 | 369 | 0 s (dùng vector B) + 0,05 s | $0 |
| C | test | 3/6 | 5/6 | 369 | (cùng index) | $0 |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,90 (10) | 18/18 | test 1/2 (dev 2/3) | 3/1/2 → 0,83 |
| B | 1,70 (10) | 18/18 | test 1/2 (dev 1/3) | 1/0/5 → 1,67 |
| C | 1,70 (10) | 18/18 | test 2/2 (dev 3/3) | 1/0/5 → 1,67 |

Tài nguyên: A lưu 203.100 ký tự / 48.990 token (khoảng 9% là phần overlap lặp lại), B/C lưu 185.140 ký tự / 44.336 token. Chunk A có median 500 ký tự (110 token); chunk B có median 537 ký tự (123 token), tối đa 800.

**Nạp lại** (`results/reingest_check.json`): chạy lại cùng phiên bản cho 0 embedding mới, 0 xóa, số dòng giữ nguyên (460/369/369). Khi mô phỏng PEP 257 bị xóa mục *Handling Docstring Indentation*, chỉ các chunk của PEP 257 thay đổi (A: 3 cập nhật, 8 xóa; B: 3 cập nhật, 6 xóa). Khôi phục bản gốc thì số dòng trở lại 460/369/369. Cơ chế dùng ID ổn định `unit_id:chunker:cNN` + `content_hash`: hash không đổi thì không embed lại, chunk không còn trong tài liệu thì bị xóa.

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace top-3 đầy đủ (câu hỏi, chunk ID, text, score, metadata, nhãn hit, `evidence_coverage`) nằm ở `results/traces_dev.jsonl` và `results/traces_test.jsonl`; chỉ số ở `results/metrics_*.json`; bảng tổng ở `results/summary.md`.
- Coherence: `results/audit/coherence_sample.json` và `coherence_labels.csv`. 10 vị trí được cố định bằng quy tắc **trước khi xem điểm**: sắp 111 đơn vị theo `unit_id`, lấy chỉ số `round(i·111/10)` với i = 0..9, vị trí là điểm giữa đơn vị. Nếu nhiều chunk phủ vị trí (do overlap), chọn chunk có tâm gần vị trí nhất.
- Grounding: `grounding_labels.csv`, chấm cả 6 câu test × 3 strategy.
- Metadata: `metadata_check_test.csv`, 6 câu test × top-3 × 3 strategy = 54 bản ghi. So `source`, `page`, `pep_type`, `status`, `python_version`, `section` với file nguồn, và kiểm tra text của chunk nằm trong đúng đơn vị và tái tạo được bằng offset.
- Người chấm: các nhãn coherence và grounding do **trợ lý AI (Claude) soạn** theo thang 0–2 của GUIDE, có ghi lý do từng nhãn. Học viên đã/cần rà soát lại từng nhãn; nguy cơ thiên lệch được nêu ở phần Hạn chế. Phần metadata được kiểm tra bằng script đối chiếu với nguồn, không phải ước lượng.

## Phân tích và kết luận

- **So sánh A–B (chỉ đổi chunking):**
  - Trên dev, Hit@3 bằng nhau (14/19) nhưng Hit@1 tăng 7 → 10. Trên test, B hơn rõ: Hit@3 2/6 → 5/6, Hit@1 0/6 → 3/6.
  - Coherence tăng 0,9 → 1,7. A bị 1 điểm ở mọi vị trí vì cửa sổ cắt giữa từ/câu; P09 bị 0 vì câu kết luận "The less confusing option is to make `:=` bind more tightly than comma" bị cắt thành "n is to make…".
  - Grounding tăng 0,83 → 1,67. B cũng ít chunk hơn 20% và ít ký tự lưu hơn 9%.
  - Đánh đổi: với câu ngắn, trực tiếp, A có lợi. Thống kê hạng của chunk gold đầu tiên trong top-50 (`results/diagnostic_gold_rank.json`): d03 "4 spaces" A hạng 1, B hạng 9; d04 A 1, B 5; d06 A 2, B 47. Câu ngắn bị "pha loãng" trong chunk B dài nhiều code. Ngược lại, B vượt hẳn khi evidence là một đoạn mạch lạc: d10 A hạng 48, B hạng 1; t04 A 27, B 2.
- **So sánh B–C (chỉ đổi filter):** Hit@1/Hit@3 **không đổi** trên cả dev và test, vì không câu filter nào đổi từ trượt sang trúng. Mức tuân thủ phạm vi tăng 1/3 → 3/3 (dev) và 1/2 → 2/2 (test). Hạng gold có cải thiện nhưng chưa vào top-3: d17 16 → 12, d18 36 → 27. Lợi ích chính của filter ở đây là loại nhiễu ngoài phạm vi, vd ở t05 hai chunk PEP 8 về comment ở hạng 2–3 được thay bằng chunk PEP 572/498 đúng danh mục. Filter không phải cách sửa lỗi xếp hạng.
- **Ví dụ sai:**
  1. **t02** (gold `pep-0001`, page 12, chunk `pep-0001:u12:para800:c00`): cả 3 strategy đều trượt top-3 (hạng gold: A 15, B/C 8). Câu hỏi "accepted PEP… status Final" khớp từ vựng mạnh với các đoạn liệt kê trạng thái ở u13/u14 (Accepted, Rejected, Withdrawn, "marked Final"). Các đoạn này nhắc "Final" nhưng không nêu điều kiện, nên grounding = 0. Đây là giới hạn của một model nhỏ, thuần dense; hybrid BM25 hoặc reranker có thể giúp.
  2. **d06** (gold `pep-0008`, page 22): ở B/C, quy tắc "Comparisons to singletons like None… `is` or `is not`" nằm cuối chunk c00 (chủ yếu nói về nối chuỗi), còn đoạn "Also, beware of writing `if x`…" sang c01. Model truy xuất c01, nên top-3 chỉ có phần cảnh báo (coverage 0,56), còn chunk gold xuống hạng 47. Ở A, cửa sổ 500 ký tự tình cờ chứa cả quy tắc lẫn cảnh báo nên trúng ở hạng 2. Chunking theo đoạn không đảm bảo giữ "quy tắc + diễn giải" cùng một chunk khi chúng là hai đoạn.
  3. **d18** (gold `pep-0572`, page 10): ở B, hạng 1 là chunk PEP 8 về khoảng trắng quanh `=`, ngoài phạm vi Standards Track. C lọc đúng phạm vi nhưng vẫn trượt, vì câu "This PEP recommends always putting spaces around `:=`" nằm cuối một chunk toàn ví dụ code.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:** chọn **B/C**: chunk theo đoạn/heading ≤ 800 ký tự, và bật filter `pep_type` (tức C) khi người dùng có ngữ cảnh danh mục. Quy tắc chốt trước chỉ phân biệt được {B, C} > A. C tương đương B khi không có filter và đảm bảo top-3 đúng phạm vi khi có, với chi phí gần như bằng 0 (cùng vector, thêm một điều kiện `WHERE`). Điều kiện áp dụng: tài liệu có cấu trúc heading/đoạn rõ, đoạn văn thường dưới 800 ký tự, và metadata danh mục lấy được tin cậy từ nguồn. Nếu truy vấn chủ yếu là tra cứu dữ kiện cực ngắn, A hoặc chunk nhỏ hơn có thể tốt hơn ở Hit@1.
- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - Test chỉ có 6 câu: 1 câu chênh lệch tương đương 17 điểm %, khoảng tin cậy rất rộng. Không suy rộng ngoài corpus này.
  - Dev và test chung tài liệu nên có rủi ro rò rỉ văn phong.
  - Câu hỏi do chính người làm bài viết, nên có thể nghiêng về cách diễn đạt gần nguồn.
  - Nhãn coherence/grounding do AI soạn và một người rà soát, không có người chấm độc lập thứ hai, không đo inter-rater agreement.
  - Hit dùng so khớp chuỗi con chính xác, nên một chunk diễn đạt tương đương nhưng không chứa nguyên văn evidence bị tính trượt. Một số câu đã khai báo alternative để giảm lỗi này.
  - Model tiếng Anh, `max_seq_length` 256; 1 chunk B bị cắt đuôi.
  - Thời gian đo trên một lần chạy, CPU 2 vCPU dùng chung, nên chỉ dùng để so sánh tương đối. Bản pgvector local (0.6.0) khác image Docker (0.8.7), nhưng exact search cho kết quả không phụ thuộc phiên bản.
- **Nếu làm lại hoặc mở rộng:**
  - Thêm hybrid BM25 + dense (giữ nguyên chunk và filter), chọn trọng số trên dev; kỳ vọng giúp các câu có từ khóa đặc thù như t02, d03, d06.
  - Chèn đường dẫn heading vào text khi embed, như một chiến lược D có kiểm soát.
  - Chunk B nên ưu tiên giữ "câu quy tắc + đoạn diễn giải kế tiếp" chung một chunk, hoặc thêm overlap một đoạn.
  - Thử model đa ngữ để hỏi bằng tiếng Việt.
  - Mở rộng test lên ≥ 20 câu, chia theo tài liệu để giảm rò rỉ, và nhờ người thứ hai chấm nhãn.

### Công cụ AI đã dùng (theo RULES.md)

Trợ lý AI (Claude) đã hỗ trợ viết code pipeline, soạn bộ câu hỏi từ corpus, soạn nhãn thủ công và bản nháp báo cáo này. Cách kiểm tra:
- Evidence được kiểm chứng tự động với nguồn.
- Metadata được đối chiếu bằng script.
- Mọi số liệu trong báo cáo lấy từ file trong `results/` do pipeline sinh ra; không có số nào tự điền.
- Học viên chịu trách nhiệm hiểu, chạy lại và rà soát toàn bộ nhãn trước khi nộp.
