# Vận hành và tái tạo dữ liệu

Chạy các lệnh dưới đây từ thư mục gốc bằng PowerShell. Dự án dùng Python 3.11 có SQLite FTS5 và thư viện chuẩn. Nếu chưa có môi trường ảo, tạo bằng `python -m venv .venv` với bản Python phù hợp. Giữ các DOCX trong `data/raw/` theo đúng tên và SHA-256 trong [danh mục nguồn](../registry/document_registry.json). Thư mục `data/raw/` và chỉ mục `data/rag/` được Git bỏ qua. Các JSON trích xuất, chunk và bản ghép hiện có trong kho mã nguồn.

## Tái tạo dữ liệu và xây chỉ mục

```powershell
$python = '.\.venv\Scripts\python.exe'
& $python -m scripts.pipeline.parse_documents
& $python -m scripts.validation.verify_output
& $python -m scripts.pipeline.chunk_documents
& $python -m scripts.validation.verify_chunks
& $python -m scripts.pipeline.consolidate_documents
& $python -m scripts.rag.baseline_rag build
```

Chạy từng lệnh và xử lý lỗi trước khi sang bước kế tiếp. Chia đoạn và hợp nhất cùng đọc dữ liệu trích xuất. Lệnh `build` cần đầu ra của cả hai nhánh.

Khi thay DOCX, cập nhật danh mục theo phiên bản nguồn. Với một trong các bản dùng để hợp nhất, đối chiếu lại vị trí khối, nội dung thay thế và các băm trong [bảng sửa đổi](../registry/consolidation_edits.json) trước khi chạy quy trình. Việc cập nhật băm cần đi kèm rà soát ánh xạ vì số vị trí có thể thay đổi giữa hai phiên bản DOCX.

## Sử dụng

```powershell
# Tra cứu một lượt, kèm dữ liệu nguồn dạng JSON
& $python -m scripts.rag.baseline_rag ask "Thế nào là đường đôi?" --json

# Tra cứu nhiều lượt trong terminal, nhập /quit để thoát
& $python -m scripts.rag.baseline_rag chat

# Chạy giao diện web bằng chỉ mục hiện tại
& $python -m scripts.rag.web_server
```

Mở `http://127.0.0.1:8000` để dùng giao diện. Dùng `--port 8001` nếu cổng mặc định đã được sử dụng. Với CLI, `--top-k` nhận giá trị từ 1 đến 10 và mặc định là 3. Cấu hình model và hạn mức Gemini cho web và CLI theo [hướng dẫn bật LLM](../README.md#bật-trả-lời-bằng-llm).

| Dấu hiệu | Điểm kiểm tra |
| --- | --- |
| Thiếu dữ liệu đầu vào | So sánh tên tệp và SHA-256 trong danh mục với DOCX cục bộ, sau đó chạy lại trích xuất. |
| `Stale input` hoặc `Incomplete chunks` | Kiểm tra băm DOCX, JSON trích xuất và chunk. Chạy lại trích xuất và chia đoạn trước khi xây chỉ mục. |
| `Stale consolidation` hoặc lỗi phiên bản DOCX | Đối chiếu bảng sửa đổi, sau đó tạo lại bản ghép từ đúng phiên bản nguồn. |
| Chỉ mục chưa sẵn sàng hoặc dữ liệu đã đổi | Xác nhận đầu ra của từng bước và chạy lại `build`. |
| `no such module: fts5` | Dùng bản Python có thư viện SQLite hỗ trợ FTS5. |

Xem lệnh đánh giá và dữ liệu đầu vào trong [báo cáo kiểm thử](kiem-thu.md).
