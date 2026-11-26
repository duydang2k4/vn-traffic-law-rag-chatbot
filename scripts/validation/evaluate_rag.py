"""Small, repeatable Vietnamese retrieval benchmark on the repository corpus."""
import sqlite3
import sys

from scripts.rag.baseline_rag import answer
from scripts.rag.rag_index import INDEX, fingerprint

# Gold document/article/clause/point, assigned from headings and the edited provisions.
# Empty components leave that level unrestricted.
CASES = [
    ('Khoản 1a Điều 6 Nghị định 168 quy định gì?', '168', '6', '1a', ''),
    ('Chở trẻ em dưới 10 tuổi trên ô tô không sử dụng thiết bị an toàn phù hợp bị xử lý thế nào?', '168', '6', '1a', ''),
    ('Xe máy vượt đèn đỏ bị phạt bao nhiêu?', '168', '7', '7', 'c'),
    ('khoan 1 dieu 42 nghi dinh 168', '168', '42', '1', ''),
    ('Thủ tục cấp phép hoạt động phương tiện giao thông thông minh theo Nghị định 151', '151', '25a', '', ''),
    ('Giám sát hành trình xe vận tải nội bộ theo Điều 27 Nghị định 151', '151', '27', '', ''),
    ('Điều 18 Nghị định 236 quy định gì?', '236', '18', '', ''),
    ('Điều 13 Nghị định 238 sửa đổi gì?', '238', '13', '', ''),
    ('khoang cach an toan la gi', '74', '3', '8', ''),
    ('Thế nào là đường đôi?', '74', '3', '2', ''),
    ('Người đứng đầu cơ sở đào tạo lái xe ô tô cần đáp ứng yêu cầu gì?', '94', '7', '', ''),
    ('Phải nhường đường tại nơi đường giao nhau như thế nào?', '55', '22', '', ''),
    ('Tốc độ tối đa của xe máy chuyên dùng ngoài đường cao tốc', '74', '7', '', ''),
    ('Cơ sở dạy lái xe mô tô phải đáp ứng tiêu chuẩn gì theo VBHN 27?', '27', '8', '', ''),
    ('Quy tắc đổi tên và số hiệu đường bộ', '65', '8', '', ''),
    ('Luật Đường bộ phân loại đường theo chức năng phục vụ ra sao?', '144', '9', '', ''),
    ('Đoạn thứ hai điểm a khoản 3 Điều 50 Nghị định 168 nói về thẩm quyền nào?', '168', '50', '3', 'a'),
    ('Đơn vị nào tiếp nhận hồ sơ của doanh nghiệp lữ hành quốc tế cho xe nước ngoài vào Việt Nam theo Nghị định 151?', '151', '33', '', ''),
]
CONTROLS = [
    ('Thời tiết Đà Nẵng ngày mai thế nào?', 'abstain'),
    ('Cách trồng cây sầu riêng?', 'abstain'),
    ('Điều 18 Nghị định 151 quy định gì?', 'abstain'),
    ('Khoản 1 Điều 6 Nghị định 999 quy định gì?', 'abstain'),
    ('Khoản 1a Điều 6 Nghị định 168 có hiệu lực vào ngày 01/07/2025 không?', 'temporal_review'),
]


def main():
    from scripts.rag.baseline_rag import retrieve
    if not INDEX.is_file():
        sys.exit('Build the index first')
    db = sqlite3.connect(INDEX)
    if db.execute("SELECT value FROM metadata WHERE key='snapshot'").fetchone() != (fingerprint(),):
        sys.exit('Index is stale; rebuild before evaluating')
    ranks = []
    for q, doc, article, clause, point in CASES:
        hits = retrieve(db, q, 3)
        rank = next((i for i, h in enumerate(hits, 1) if h['number'].split('/')[0] == doc and
                     h['article'] == article and (not clause or h['clause'] == clause) and
                     (not point or h['point'] == point)), 0)
        ranks.append(rank)
        print(f'{"MISS" if not rank else rank}  {q}')
    print(f'Hit@1 {ranks.count(1)}/{len(ranks)}; Hit@3 {sum(bool(r) for r in ranks)}/{len(ranks)}; '
          f'MRR@3 {sum(1/r for r in ranks if r)/len(ranks):.3f}')
    for q, expected in CONTROLS:
        actual = answer(db, q)['mode']
        if actual != expected:
            sys.exit(f'{q}: expected {expected}, got {actual}')
    print(f'Controls: {len(CONTROLS)}/{len(CONTROLS)}')
    db.close()


if __name__ == '__main__':
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding='utf-8')
    main()

