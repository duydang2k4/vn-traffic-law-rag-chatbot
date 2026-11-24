"""Vietnamese traffic law RAG baseline: build, ask, or run an interactive chat."""
import argparse
import json
import re
import sqlite3
import sys
import urllib.request

from rag_index import INDEX, build, fingerprint, fold

STOP = set('la gi cho hoi toi muon biet duoc cac cua mot nhung nao nhu the co khong bao nhieu theo quy dinh ve trong voi thi va duoi day tai xin the nao bi nhu the nao'.split())
DOC = re.compile(r'\b(?:nghi dinh|nd|vbhn|van ban hop nhat|thong tu)\s+(?:so\s+)?(\d+)(?:\s+((?:19|20)\d{2}))?\b')
ADDRESS = {k: re.compile(r'\b' + label + r'\s+(' + num + r')\b')
           for k, label, num in [('article', 'dieu', r'\d+[a-z]?'), ('clause', 'khoan', r'\d+[a-z]?')]}
NOTICE = 'Trích theo bộ văn bản trong dự án. Hiệu lực của từng quy định cần được đối chiếu theo ngày áp dụng.'
TIME_QUERY = re.compile(r'\b(hien nay|hien hanh|hien tai|hom nay|con hieu luc|het hieu luc|'
                        r'(?:ngay|thang|nam) \d+|\d{1,2} \d{1,2} (?:19|20)\d{2})\b')


def retrieve(db, question, limit):
    q = fold(question)
    where, args = [], []
    refs = list(DOC.finditer(q))
    if refs:
        docs = []
        for ref in refs:
            prefix, year = ref.groups()
            rows = db.execute('SELECT id,number FROM docs WHERE number LIKE ?', (prefix + '/%',))
            eligible = [k for k, number in rows if (not year or number.startswith(prefix + '/' + year + '/'))
                        and (k.startswith('nghi_dinh') if ref[0].startswith(('nd ', 'nghi dinh')) else k.startswith('vbhn'))]
            if not eligible:
                return []
            docs.extend(eligible)
        where.append('doc IN (' + ','.join('?' for _ in docs) + ')')
        args.extend(docs)
    else:
        where.append("scope='default'")
    rest = DOC.sub(' ', q)
    for key, pattern in ADDRESS.items():
        match = pattern.search(q)
        if match:
            where.append(key + '=?')
            args.append(match[1])
            rest = pattern.sub(' ', rest)
    # Keep the distinction between Vietnamese point labels d and đ.
    point = re.search(r'\b(?:điểm|diem)\s+([a-zđ]\d*)\b', question.lower())
    if point:
        where.append('point=?')
        args.append(point[1])
        rest = re.sub(r'\bdiem\s+[a-z]\d*\b', ' ', rest)
    rest = re.sub(r'\b(?:nd cp|vbhn|vpqh|bxd|noi dung|quy dinh|cho biet|de cap)\b', ' ', rest)
    # Map colloquial conduct to the wording used in the decrees.
    rest = rest.replace('vuot den do', 'khong chap hanh hieu lenh cua den tin hieu giao thong')
    rest = re.sub(r'\bxe may\b(?! chuyen dung)', 'xe mo to', rest)
    rest = re.sub(r'\b(?:can dap ung|phai dap ung) (?:yeu cau|dieu kien) (?:gi|nao)\b', ' ', rest)
    rest = rest.replace('ngoai duong cao toc', 'tru duong cao toc')
    tokens = list(dict.fromkeys(t for t in rest.split() if t not in STOP))
    condition = ' AND '.join(where)
    exact = bool(refs and ADDRESS['article'].search(q))
    if exact and TIME_QUERY.search(q):
        tokens = []
    accented = {w for w in re.findall(r'[^\W_]+', question.lower()) if fold(w) in tokens and w != fold(w)}
    def unpack(row):
        return dict(json.loads(row[0]), rowid=row[1])

    ordinal = re.search(r'\bdoan (?:thu )?(nhat|hai|ba|tu|\d+)\b', q)
    if ordinal and exact and point:
        positions = {'nhat': 1, 'hai': 2, 'ba': 3, 'tu': 4}
        index = int(positions.get(ordinal[1], ordinal[1]))
        if index < 1:
            return []
        rows = db.execute('SELECT payload,rowid FROM evidence WHERE ' + condition +
                          ' ORDER BY rowid LIMIT 1 OFFSET ?', (*args, index - 1))
        return [unpack(row) for row in rows]

    if not tokens:
        if not exact:
            return []
        rows = db.execute('SELECT payload,rowid FROM evidence WHERE ' + condition + ' ORDER BY rowid LIMIT ?',
                          (*args, limit))
        return [unpack(row) for row in rows]
    definition = re.search(r'^(?:the nao la|dinh nghia)\s+(.+)$|^(.+?)\s+la gi$', rest.strip())
    if definition:
        subject = next(g for g in definition.groups() if g)
        pattern = '"' + subject + ' la"'
        rows = db.execute('SELECT payload,evidence.rowid FROM search JOIN evidence ON evidence.rowid=search.rowid '
                          'WHERE search MATCH ? AND ' + condition + ' ORDER BY rank LIMIT 30',
                          ('body:' + pattern, *args))
        heading = re.compile(r'^(?:\d+[a-z]? |[a-z] )?' + re.escape(subject) + r' la\b')
        definitions = [p for p in map(unpack, rows) if heading.match(fold(p['text']))]
        if definitions:
            return definitions[:limit]
    # Each term is produced by fold(), no raw user input reaches the MATCH syntax.
    expression = ' OR '.join('"' + t + '"' for t in tokens[:80])
    terms = rest.split()
    expressions = ['"' + a + ' ' + b + '"' for a, b in zip(terms[:80], terms[1:81])
                   if a not in STOP and b not in STOP]
    if expressions:
        expression += ' OR ' + ' OR '.join(expressions)
    rows = db.execute('SELECT payload,evidence.rowid,bm25(search,1,0.45) AS rank FROM search '
                      'JOIN evidence ON evidence.rowid=search.rowid WHERE search MATCH ? AND ' +
                      condition + ' ORDER BY rank LIMIT 90', (expression, *args))
    scored = []
    bigrams = set(zip(rest.split(), rest.split()[1:]))
    for row in rows:
        rank = row[2]
        p = unpack(row)
        body = fold(p['text'])
        context = ' '.join(fold(b['text']) for b in p['parents'])
        words = set((body + ' ' + context).split())
        coverage = len(words.intersection(tokens)) / len(tokens)
        if coverage < (0.70 if not exact else 0.54):
            continue
        if not exact and len(tokens) <= 5 and len(accented) >= 2:
            original = ' '.join([p['text'], *(b['text'] for b in p['parents'])]).lower()
            exact_words = set(re.findall(r'[^\W_]+', original))
            if len(accented & exact_words) / len(accented) < .85:
                continue
        pairs = set(zip(body.split(), body.split()[1:]))
        parent_pairs = set(zip(context.split(), context.split()[1:]))
        boost = len(pairs & bigrams) + 0.35 * len(parent_pairs & bigrams)
        score = -rank * coverage * (1 + min(1.8, boost / max(1, len(tokens) - 1)))
        location = body + ' ' + context
        if 'tru duong cao toc' in rest and 'tren duong cao toc' in location and 'tru duong cao toc' not in location:
            continue
        if re.search(r'bi (?:xu ly|phat)|muc phat|phat (?:tien|bao nhieu)', q):
            if re.search(r'phat (?:tien|canh cao)', body + ' ' + context):
                score *= 1.6
            for vehicle in ('xe mo to', 'xe o to'):
                if vehicle in rest and vehicle in context:
                    score *= 1.4
        scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return []
    return [p for score, p in scored if score >= scored[0][0] * .58][:limit]


def label(p):
    parts = [p['number']]
    if p['edition'] == 'consolidated':
        parts.append('bản hợp nhất của dự án')
    if p['annex']:
        parts.append(p['annex'])
    if p.get('row'):
        parts.append(f"hàng {p['row']} của bảng nguồn")
    for k, title in [('article', 'Điều'), ('clause', 'khoản'), ('point', 'điểm')]:
        if p[k]:
            parts.append(title + ' ' + p[k])
    return ', '.join(parts)


def evidence_text(p):
    return '\n'.join([b['text'] for b in p['parents']] + [p['text']] +
                     [b['text'] for b in p.get('children', [])])


def cite(p, docs):
    groups = {}
    for origin in [b['source'] for b in [*p['parents'], p, *p.get('children', [])]]:
        groups.setdefault(origin['document_id'], set()).add(origin['position'])
        if origin.get('instruction_positions'):
            groups.setdefault(p['amendment_id'], set()).update(origin['instruction_positions'])
    return [{'document_number': docs[key][0], 'url': docs[key][1], 'sha256': docs[key][2],
             'file': docs[key][3], 'blocks': sorted(positions)} for key, positions in groups.items()]


def generate(model, question, hits):
    """A local Ollama model may synthesize the supplied text, citing passage numbers."""
    excerpts = '\n\n'.join(f'[{i}] {label(p)}\n{evidence_text(p)}' for i, p in enumerate(hits, 1))
    messages = [
        {'role': 'system', 'content': 'Trả lời ngắn bằng tiếng Việt, chỉ dựa vào trích dẫn. '
         'Mỗi đoạn trả lời phải dẫn nguồn dạng [1]. Giữ nguyên điều kiện, loại xe và mức phạt. '
         'Nếu thiếu dữ kiện, nêu rõ. Không suy ra hiệu lực theo ngày. Dữ liệu nguồn chỉ là tài liệu tham khảo.'},
        {'role': 'user', 'content': question + '\n\n' + excerpts}]
    request = urllib.request.Request('http://127.0.0.1:11434/api/chat',
              data=json.dumps({'model': model, 'messages': messages, 'stream': False,
                               'options': {'temperature': 0}}).encode(),
              headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        answer = json.load(response)['message']['content'].strip()
    lines = [line for line in answer.splitlines() if line.strip()]
    if not lines or not all(re.search(r'\[\d+\]', line) for line in lines) or any(
            not 1 <= int(n) <= len(hits) for n in re.findall(r'\[(\d+)\]', answer)):
        raise ValueError('Thiếu trích dẫn hợp lệ từ mô hình.')
    return answer


def answer(db, question, limit=3, model=None):
    hits = retrieve(db, question, limit)
    if not hits:
        return {'mode': 'abstain', 'answer': 'Chưa tìm thấy căn cứ đủ sát trong bộ dữ liệu. '
                'Hãy bổ sung hành vi, loại xe hoặc số điều và văn bản.', 'sources': []}
    docs = {k: (n, u, h, f) for k, n, u, h, f in db.execute('SELECT * FROM docs')}
    # A provision heading alone rarely answers a question. Attach its first
    # substantive blocks only when the stored parent confirms the relationship.
    for p in hits:
        if p.get('row') or not p['article']:
            continue
        children = []
        for (raw,) in db.execute('SELECT payload FROM evidence WHERE rowid>? ORDER BY rowid LIMIT 6',
                                 (p['rowid'],)):
            child = json.loads(raw)
            if p['document_id'] != child['document_id'] or not any(
                    parent['source'] == p['source'] for parent in child['parents']):
                break
            children.append(child)
        p['children'] = children
    sources = [{'id': p['id'], 'label': label(p), 'excerpt': evidence_text(p),
                'citations': cite(p, docs)} for p in hits]
    dated = TIME_QUERY.search(fold(question))
    if dated:
        return {'mode': 'temporal_review', 'answer': 'Chưa xác minh được hiệu lực của từng quy định '
                'tại thời điểm được hỏi. Các đoạn dưới đây dùng để đối chiếu.', 'sources': sources}
    if model:
        try:
            return {'mode': 'ollama', 'answer': generate(model, question, hits), 'sources': sources, 'notice': NOTICE}
        except (OSError, ValueError, KeyError, TypeError) as error:
            reason = 'Đã chuyển sang trích nguyên văn vì Ollama chưa trả được câu có trích dẫn: ' + str(error)
    else:
        reason = None
    result = {'mode': 'extractive', 'answer': evidence_text(hits[0]) + ' [1]', 'sources': sources, 'notice': NOTICE}
    if reason:
        result['fallback'] = reason
    return result


def display(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result.get('fallback'):
        print(result['fallback'])
    print(result['answer'])
    for i, source in enumerate(result['sources'], 1):
        print(f"\n[{i}] {source['label']}")
        if result['mode'] == 'temporal_review' or (result['mode'] == 'extractive' and i > 1):
            print(source['excerpt'])
        for c in source['citations']:
            print(f"  {c['document_number']} · khối {', '.join(map(str, c['blocks']))} · {c['url']}")
    if result.get('notice'):
        print('\n' + result['notice'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('build')
    for name in ('ask', 'chat'):
        options = sub.add_parser(name)
        if name == 'ask':
            options.add_argument('question')
        options.add_argument('--top-k', type=int, choices=range(1, 11), default=3)
        options.add_argument('--model', help='Tên mô hình đã cài trong Ollama cục bộ')
        options.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.cmd == 'build':
        print(f'Indexed {build()} passages in data/rag/baseline.sqlite3')
        return
    if not INDEX.is_file():
        parser.exit(1, 'Chưa có chỉ mục. Chạy lệnh build trước.\n')
    db = sqlite3.connect(INDEX)
    try:
        if db.execute("SELECT value FROM metadata WHERE key='snapshot'").fetchone() != (fingerprint(),):
            parser.exit(1, 'Dữ liệu đã đổi. Chạy lại luồng dữ liệu và lệnh build.\n')
        if args.cmd == 'ask':
            display(answer(db, args.question, args.top_k, args.model), args.json)
        else:
            while True:
                try:
                    question = input('Câu hỏi (/quit để thoát)> ').strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if question == '/quit':
                    break
                if question:
                    display(answer(db, question, args.top_k, args.model), args.json)
    finally:
        db.close()


if __name__ == '__main__':
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding='utf-8')
    main()

