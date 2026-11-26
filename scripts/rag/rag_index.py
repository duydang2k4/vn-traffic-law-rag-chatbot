"""Build the offline, source-addressable corpus used by baseline_rag.py."""
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

from scripts import ROOT
from scripts.pipeline.chunk_documents import read
from scripts.pipeline.consolidate_documents import consolidate

INDEX = ROOT / 'data/rag/baseline.sqlite3'
REGISTRY = ROOT / 'registry/document_registry.json'
VERSION = '2'


def fold(text):
    letters = unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(c for c in letters if not unicodedata.combining(c))))


def fingerprint():
    paths = [REGISTRY, ROOT / 'registry/consolidation_edits.json']
    for entry in read(REGISTRY)['documents']:
        paths += [ROOT / entry['raw_file']]
        for folder in ['processed', 'chunks']:
            paths.append(ROOT / 'data' / folder / (entry['id'] + '.json'))
    for spec in read(paths[1]).values():
        paths.append(ROOT / 'data/consolidated' / (spec['base_document'] + '.json'))
    digest = hashlib.sha256(VERSION.encode())
    for path in paths:
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def part(pattern, text):
    match = re.match(pattern, text)
    return match.group(1) if match else ''


def passages(entry, chunks, edition, implementation_start=None, payload_positions=()):
    """One source block per passage with its legal parent headings as context."""
    article = clause = point = ''
    article_block = clause_block = None
    annex = None
    for chunk_id, blocks, article_meta, clause_meta in chunks:
        for block in blocks:
            body = block['text'].strip()
            if not body:
                continue
            pos = block['position']
            origin = block.get('source', {'document_id': entry['id'], 'position': pos})
            item = {'text': body, 'source': origin}
            if re.fullmatch(r'Phụ lục\s+[IVXLCDM]+', body, re.I):
                annex = body
            if edition == 'source':
                article = article_meta['number'] if article_meta and not annex else ''
                clause = clause_meta['number'] if clause_meta and not annex else ''
                point = part(r'^([a-zđ]\d*)\)', body) if clause else ''
                context = [(m['heading'], int(m['id'].rsplit(':', 1)[1])) for m in
                           (article_meta, clause_meta) if m and not annex]
                parents = [{'text': t, 'source': {'document_id': entry['id'], 'position': p}}
                           for t, p in context if p != pos]
            else:
                if re.match(r'^(Chương |Mục |Phụ lục\s|Nơi nhận:|TM\. CHÍNH PHỦ)', body, re.I):
                    article = clause = point = ''
                    article_block = clause_block = None
                new_article = part(r'^Điều\s+(\d+[a-z]?)\s*[.:]', body)
                new_clause = part(r'^(\d+[a-z]?)\.\s', body)
                if not annex and pos not in payload_positions:
                    if new_article:
                        article, clause, point = new_article, '', ''
                        article_block, clause_block = item, None
                    elif article and new_clause:
                        clause, point, clause_block = new_clause, '', item
                    elif clause:
                        point = part(r'^([a-zđ]\d*)\)', body) or point
                parents = [parent for parent in (article_block, clause_block) if parent and parent is not item]
            scope = 'explicit' if edition == 'amendment' and not (
                implementation_start and implementation_start[0] <= pos <= implementation_start[1]) else 'default'
            record = {'id': f"{chunk_id}:b{pos}", 'document_id': entry['id'], 'number': entry['number'],
                   'article': article, 'clause': clause, 'point': point, 'annex': annex,
                   'edition': edition, 'scope': scope, 'text': body, 'source': origin, 'parents': parents}
            rows = block.get('rows', [])
            if len(rows) > 1:
                header = ' | '.join(rows[0])
                for i, row in enumerate(rows[1:], 2):
                    if any(cell.strip() for cell in row):
                        yield dict(record, id=record['id'] + f':r{i}', row=i,
                                   text=header + '\n' + ' | '.join(row))
            else:
                yield record


def build(path=INDEX):
    entries = {e['id']: e for e in read(REGISTRY)['documents']}
    rules = read(ROOT / 'registry/consolidation_edits.json')
    amendments = {r['base_document']: key for key, r in rules.items()}
    snapshot = fingerprint()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    os.close(fd)
    conn = sqlite3.connect(tmp)
    count = 0
    try:
        conn.executescript("""
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE docs (id TEXT PRIMARY KEY, number TEXT, url TEXT, hash TEXT, filename TEXT);
            CREATE TABLE evidence (doc TEXT, article TEXT, clause TEXT, point TEXT, scope TEXT, payload TEXT);
            CREATE INDEX address ON evidence(doc,article,clause,point);
            CREATE VIRTUAL TABLE search USING fts5(body, context);
        """)
        for key, entry in entries.items():
            raw_hash = hashlib.sha256((ROOT / entry['raw_file']).read_bytes()).hexdigest()
            parsed = read(ROOT / 'data/processed' / (key + '.json'))
            file = read(ROOT / 'data/chunks' / (key + '.json'))
            if not (raw_hash == entry['sha256'] == parsed['sha256'] == file['source_sha256']):
                raise ValueError(f'Stale input: {key}')
            if [b for c in file['chunks'] for b in c['blocks']] != parsed['blocks']:
                raise ValueError(f'Incomplete chunks: {key}')
            conn.execute('INSERT INTO docs VALUES (?,?,?,?,?)',
                         (key, entry['number'], entry['source_url'], raw_hash, entry['raw_file']))
            edition = 'amendment' if key in rules else 'source'
            window = rules[key]['implementation_blocks'] if key in rules else None
            quoted = {i for a in rules.get(key, {}).get('actions', []) if 'payload' in a
                      for i in range(a['payload'][0], a['payload'][1] + 1)}
            if key in amendments:
                amendment = read(ROOT / 'data/processed' / (amendments[key] + '.json'))
                merged = read(ROOT / 'data/consolidated' / (key + '.json'))
                if merged != consolidate(parsed, amendment):
                    raise ValueError(f'Stale consolidation: {key}')
                edition = 'consolidated'
                chunks = [(key + ':merged', merged['blocks'], None, None)]
            else:
                chunks = ((c['id'], c['blocks'], c['article'], c['clause']) for c in file['chunks'])
            for p in passages(entry, chunks, edition, window, quoted):
                if edition == 'consolidated':
                    p['amendment_id'] = amendments[key]
                cursor = conn.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?)',
                                      (key, p['article'], p['clause'], p['point'], p['scope'],
                                       json.dumps(p, ensure_ascii=False)))
                context = ' '.join(b['text'] for b in p['parents'])
                conn.execute('INSERT INTO search(rowid,body,context) VALUES (?,?,?)',
                             (cursor.lastrowid, fold(p['text']), fold(context)))
                count += 1
        if fingerprint() != snapshot:
            raise ValueError('Source files changed during build')
        conn.execute('INSERT INTO metadata VALUES (?,?)', ('snapshot', snapshot))
        conn.commit()
        conn.close()
        os.replace(tmp, path)
    finally:
        conn.close()
        Path(tmp).unlink(missing_ok=True)
    return count

