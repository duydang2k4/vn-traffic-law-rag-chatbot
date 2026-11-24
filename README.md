# RAG hỏi đáp pháp luật giao thông đường bộ

## Chạy baseline

Từ thư mục gốc, dùng Python 3.11 có SQLite FTS5. Chế độ mặc định chạy cục bộ bằng thư viện chuẩn. Nếu chỉ mục đã được tạo, có thể chạy ngay lệnh `ask` hoặc `chat`.

```powershell
.\.venv\Scripts\python.exe scripts/baseline_rag.py build
.\.venv\Scripts\python.exe scripts/baseline_rag.py ask "Khoản 1a Điều 6 Nghị định 168 quy định gì?"
.\.venv\Scripts\python.exe scripts/baseline_rag.py chat
.\.venv\Scripts\python.exe scripts/evaluate_rag.py
```

`ask` và `chat` nhận `--top-k 1` đến `--top-k 10`. Mỗi câu hỏi được tra cứu độc lập. Thêm `--json` để lấy câu trả lời, đoạn bằng chứng, số hiệu văn bản, vị trí khối trong DOCX, mã băm và URL. Mặc định, hệ thống trả đoạn phù hợp nhất kèm ngữ cảnh điều/khoản. Nếu đã chạy Ollama tại cổng 11434, thêm `--model <tên-model-đã-cài>` để tổng hợp câu trả lời từ các đoạn tìm được. Nếu Ollama không kết nối được hoặc trả về số trích dẫn không hợp lệ, hệ thống chuyển về trích nguyên văn. Số trích dẫn hợp lệ chưa chứng minh nội dung do mô hình sinh khớp nguồn.

Chỉ mục SQLite trong `data/rag/` dùng BM25, chuẩn hóa tiếng Việt có và không dấu, địa chỉ điều/khoản/điểm và ngữ cảnh cha. Đơn vị tìm kiếm là khối văn bản hoặc hàng bảng có tiêu đề. Với 151 và 168, chỉ mục dùng bản ghép trong `data/consolidated/`. Có thể hỏi trực tiếp 236 hoặc 238 bằng số nghị định. Phần hiệu lực và chuyển tiếp của hai nghị định sửa đổi cũng được đưa vào phạm vi tìm kiếm mặc định. Điểm xếp hạng thể hiện độ khớp từ vựng. Với truy vấn ngày tháng mà hệ thống nhận diện được, câu trả lời chỉ cung cấp bằng chứng để đối chiếu.

Khi đổi DOCX, cập nhật danh mục, chạy lại các bước trích xuất, chia chunk và hợp nhất bên dưới, sau đó chạy `build`. Lệnh này kiểm tra dữ liệu đầu vào trước khi thay chỉ mục đang dùng. Bộ đánh giá nhỏ trong `scripts/evaluate_rag.py` đo thứ hạng văn bản và điều khoản đích, cùng các tình huống từ chối trả lời hoặc cần kiểm tra hiệu lực.

## Danh mục và trích xuất văn bản

## Bản nháp hợp nhất

Chạy `python scripts/consolidate_documents.py` sau bước trích xuất để tạo hai tệp JSON trong `data/consolidated/`. Luồng dùng bản 151 đã được người dùng cập nhật phần liên quan tới Nghị định 184. Bảng đối chiếu `registry/consolidation_edits.json` gắn từng chỉ dẫn của 236 và 238 với vị trí trong đúng phiên bản DOCX. Khi đổi tệp nguồn, cần rà soát lại bảng này. Chạy `python scripts/test_consolidate_documents.py` để kiểm tra trên dữ liệu dự án.

`actions` ghi chỉ dẫn, đích và thao tác. Địa chỉ `50/3/a#2` nghĩa là đoạn thứ hai của điểm a khoản 3 Điều 50. Các khoảng `base` và `payload` đếm từ 1, gồm cả hai đầu. Các khối trong `blocks` mang vị trí mới và thông tin truy về nguồn trong `source`. Bảng phụ lục giữ hàng và ô theo dữ liệu trích xuất. Khoản 5 Điều 16 của 236 nhắm tới 184 nên được ghi với trạng thái `external_document`.

Đầu ra ghép câu chữ của các bản DOCX, bao gồm cả sửa đổi có ngày áp dụng riêng. Khi tra cứu theo ngày, cần xét `implementation_provisions` cùng Điều 53 của bản 168. Luồng chia chunk hiện tại vẫn đọc các văn bản trong `data/processed/`.

Danh mục tại `registry/document_registry.json` ghi nguồn chính thức, ngày ban hành, ngày hiệu lực nếu có, quan hệ đã xác định và mã SHA-256 của 10 tệp gốc. Trường tình trạng pháp lý để chưa xác minh đầy đủ; danh sách quan hệ không được hiểu là đầy đủ. Văn bản hợp nhất không có một ngày hiệu lực chung: cần kiểm tra từng văn bản thành phần và từng điều khoản.

Chạy tại thư mục gốc dự án với Python 3.11:

```powershell
python scripts/parse_documents.py
python scripts/verify_output.py
```

JSON được tạo trong `data/processed/`, mỗi tệp chứa danh sách khối theo thứ tự nguồn, vị trí khối trong `word/document.xml`, cấu trúc dự kiến Chương/Mục/Điều/Khoản/Điểm, bảng theo hàng/ô, nội dung chú thích và danh sách hình ảnh. Các ID gắn với vị trí khối của phiên bản DOCX được băm SHA-256; khi tệp gốc thay đổi, ID có thể thay đổi. `inventory.json` thống kê các tệp. `data/` đang được `.gitignore` loại trừ.

## Giới hạn cần xử lý tiếp

- Chưa xác minh đầy đủ tình trạng hiệu lực và bãi bỏ.
- Phân cấp dùng mẫu văn bản, có thể nhận nhầm nội dung trích dẫn sửa đổi, đánh số trong phụ lục hoặc bỏ sót đánh số tự động. Bảng giữ văn bản theo hàng và ô nhưng chưa tái hiện ô gộp, bố cục và hình ảnh. Số chú thích và văn bản đã trích xuất chưa được nối đầy đủ với vị trí tham chiếu trong thân văn bản.
- Kiểm tra tự động xác nhận hash, khối nguồn và tham chiếu ID, không chứng minh tính đúng đắn của phân cấp hay tính đầy đủ so với bản chính thức.
- Văn bản hợp nhất 144/2026/VBHN-LQ-VPQH có nội dung sửa đổi có hiệu lực từ 01/03/2027; không giả định toàn bộ nội dung đã có hiệu lực tại ngày 21/11/2026.

## Bước 2: chia đoạn và quan hệ sửa đổi (chưa hoàn tất)

Chạy `python scripts/chunk_documents.py` sau bước 1, rồi `python scripts/verify_chunks.py`. Kết quả nằm trong `data/chunks/` (không được Git theo dõi). Mỗi chunk có các khối gốc, thông tin văn bản, Điều/Khoản và ngữ cảnh cha nếu nhận diện được; kiểm tra so sánh toàn bộ khối đầu ra với đầu vào theo thứ tự, bao gồm bảng và khối rỗng. Ngữ cảnh cha là metadata nên không tính là nội dung lặp. Các khối không xác định được Điều/Khoản vẫn được lưu. Tên và phân cấp Điều/Khoản kế thừa kết quả tạm thời của bước 1, đặc biệt có thể sai trong trích dẫn sửa đổi và phụ lục; chú thích và hình ảnh ngoài thân văn bản chưa nằm trong chunk.

`registry/amendment_mapping.json` ghi quan hệ cấp văn bản đã kiểm tra theo nguồn Chính phủ; danh sách phiên bản quy định đã kiểm chứng hiện còn rỗng. Nghị định 151 còn được sửa bởi Nghị định 184/2025, chưa có trong tập DOCX. Nghị định 238 có các quy định áp dụng theo thời điểm riêng. Chưa thể xác định đầy đủ phiên bản và khoảng hiệu lực hoặc áp dụng ngày chung cho từng đoạn. Do đó `valid_from` và `valid_until_exclusive` đều để null với trạng thái `unverified`; `document_effective_date` chỉ là metadata của văn bản, không phải hiệu lực từng quy định. Cần đối chiếu thủ công từng sửa đổi, các văn bản trung gian và điều khoản hiệu lực/chuyển tiếp trước khi sử dụng để trả lời theo thời gian.
