# Dữ liệu kiểm thử và kết quả hiện tại

Bộ kiểm tra dùng dữ liệu văn bản thật trong dự án. Kiểm tra pipeline đối chiếu DOCX, JSON trích xuất và chunk. Kiểm thử hợp nhất dùng bốn DOCX liên quan đến hai cặp sửa đổi. Đánh giá truy xuất dùng 18 câu hỏi có nhãn điều khoản và 5 tình huống đối chứng được khai báo trực tiếp trong mã Python.

## Văn bản dùng để kiểm tra pipeline

| Số hiệu | Vai trò trong dữ liệu kiểm thử |
| --- | --- |
| 151/2024/NĐ-CP | Bản đã cập nhật phần liên quan đến 184, dùng làm nền để ghép với 236. |
| 168/2024/NĐ-CP | Bản nền ghép với 238, dùng cho các câu hỏi về xử phạt và thẩm quyền. |
| 236/2026/NĐ-CP | Văn bản sửa đổi dùng trong bản ghép 151 và các truy vấn theo số hiệu 236. |
| 238/2026/NĐ-CP | Văn bản sửa đổi dùng trong bản ghép 168 và các truy vấn theo số hiệu 238. |
| 94/2026/NĐ-CP | Đích của câu hỏi về người đứng đầu cơ sở đào tạo lái xe ô tô. |
| 144/2026/VBHN-LQ-VPQH | Đích của câu hỏi về phân loại đường bộ theo chức năng phục vụ. |
| 27/VBHN-BXD | Đích của câu hỏi về cơ sở dạy lái xe mô tô. |
| 55/VBHN-VPQH | Đích của câu hỏi về nhường đường nơi giao nhau. |
| 65/2026/VBHN-NĐ-BXD | Đích của câu hỏi về đổi tên và số hiệu đường bộ. |
| 74/2026/VBHN-TT-BXD | Đích của các câu hỏi về khoảng cách an toàn, đường đôi và tốc độ xe máy chuyên dùng. |

Đường dẫn DOCX, nguồn và SHA-256 nằm trong [danh mục văn bản](../registry/document_registry.json). Bốn bài `unittest` dùng hai cặp 151–236 và 168–238 để kiểm tra độ bao phủ khối sửa đổi, thứ tự và tính duy nhất của nguồn, bãi bỏ và chèn Điều, giữ bảng phụ lục, ranh giới thay thế, sửa cụm từ và từ chối bản đầu vào đổi băm. Bài đổi băm tạo bản sao dữ liệu trong bộ nhớ. [Mã kiểm thử hợp nhất](../tests/test_consolidate_documents.py)

## 18 câu hỏi có nhãn truy xuất

Nhãn xác định số hiệu văn bản và Điều đích, kèm Khoản và Điểm nếu ca kiểm thử yêu cầu. Cấp không ghi trong bảng không được ràng buộc khi tính hạng.

| Câu hỏi | Đích |
| --- | --- |
| Khoản 1a Điều 6 Nghị định 168 quy định gì? | 168 · Điều 6 · Khoản 1a |
| Chở trẻ em dưới 10 tuổi trên ô tô không sử dụng thiết bị an toàn phù hợp bị xử lý thế nào? | 168 · Điều 6 · Khoản 1a |
| Xe máy vượt đèn đỏ bị phạt bao nhiêu? | 168 · Điều 7 · Khoản 7 · Điểm c |
| `khoan 1 dieu 42 nghi dinh 168` | 168 · Điều 42 · Khoản 1 |
| Thủ tục cấp phép hoạt động phương tiện giao thông thông minh theo Nghị định 151 | 151 · Điều 25a |
| Giám sát hành trình xe vận tải nội bộ theo Điều 27 Nghị định 151 | 151 · Điều 27 |
| Điều 18 Nghị định 236 quy định gì? | 236 · Điều 18 |
| Điều 13 Nghị định 238 sửa đổi gì? | 238 · Điều 13 |
| `khoang cach an toan la gi` | 74 · Điều 3 · Khoản 8 |
| Thế nào là đường đôi? | 74 · Điều 3 · Khoản 2 |
| Người đứng đầu cơ sở đào tạo lái xe ô tô cần đáp ứng yêu cầu gì? | 94 · Điều 7 |
| Phải nhường đường tại nơi đường giao nhau như thế nào? | 55 · Điều 22 |
| Tốc độ tối đa của xe máy chuyên dùng ngoài đường cao tốc | 74 · Điều 7 |
| Cơ sở dạy lái xe mô tô phải đáp ứng tiêu chuẩn gì theo VBHN 27? | 27 · Điều 8 |
| Quy tắc đổi tên và số hiệu đường bộ | 65 · Điều 8 |
| Luật Đường bộ phân loại đường theo chức năng phục vụ ra sao? | 144 · Điều 9 |
| Đoạn thứ hai điểm a khoản 3 Điều 50 Nghị định 168 nói về thẩm quyền nào? | 168 · Điều 50 · Khoản 3 · Điểm a |
| Đơn vị nào tiếp nhận hồ sơ của doanh nghiệp lữ hành quốc tế cho xe nước ngoài vào Việt Nam theo Nghị định 151? | 151 · Điều 33 |

## 5 tình huống đối chứng

| Câu hỏi | Chế độ mong đợi |
| --- | --- |
| Thời tiết Đà Nẵng ngày mai thế nào? | `abstain` |
| Cách trồng cây sầu riêng? | `abstain` |
| Điều 18 Nghị định 151 quy định gì? | `abstain` |
| Khoản 1 Điều 6 Nghị định 999 quy định gì? | `abstain` |
| Khoản 1a Điều 6 Nghị định 168 có hiệu lực vào ngày 01/07/2025 không? | `temporal_review` |

## Kết quả xác minh trên chỉ mục hiện tại

| Lệnh kiểm tra | Kết quả |
| --- | --- |
| `python -m scripts.validation.verify_output` | Đạt trên 10 tệp. Kiểm tra băm, khối nguồn và tham chiếu. |
| `python -m scripts.validation.verify_chunks` | Đạt trên 10 văn bản với 2.818 chunk. Các khối được bảo toàn đúng thứ tự. |
| `python -m unittest discover -s tests` | 4/4 bài kiểm thử hợp nhất đạt. |
| `python -m scripts.validation.evaluate_rag` | Hit@1 17/18, Hit@3 18/18, MRR@3 0,972 và 5/5 tình huống đối chứng đạt. |

Hit@1 và Hit@3 đếm số câu có đích xuất hiện ở vị trí đầu hoặc trong ba vị trí đầu. MRR@3 là trung bình nghịch đảo hạng của kết quả khớp đầu tiên, với 0 cho ca không tìm được trong ba kết quả. Câu về đổi tên và số hiệu đường bộ có đích ở hạng 2. Bộ hiện tại đo thứ hạng địa chỉ văn bản và chế độ phản hồi. Bài hỏi đoạn thứ hai được chấm theo nhãn đến cấp Điểm. Việc đánh giá độ chính xác của từng đoạn, thời điểm hiệu lực và câu trả lời do Ollama tổng hợp cần tiêu chí riêng. [Mã và nhãn đánh giá RAG](../scripts/validation/evaluate_rag.py)
