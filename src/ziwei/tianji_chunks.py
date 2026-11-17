"""Deterministic section chunks; provenance is kept in the same retrieval row."""
import hashlib
import json
from collections import OrderedDict


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_chunks(records, size=500, overlap=20):
    if not 0 <= overlap < size:
        raise ValueError('overlap must be smaller than chunk size')
    groups = OrderedDict()
    for position, row in enumerate(records, 1):
        row = dict(row)
        row.setdefault('original_id', row.get('id', position))
        key = (row['book'], row['h2'], row.get('h3') or '')
        groups.setdefault(key, []).append(row)
    chunks, catalog = [], []
    for (book, h2, h3), rows in groups.items():
        section_id = sha(json.dumps([book, h2, h3], ensure_ascii=False))
        body, sources = '', []
        for row in rows:
            if body:
                body += '\n'
            start = len(body)
            body += row['quote']
            sources.append(row | {'start': start, 'end': len(body)})
        prefix = f'来源：{book}\n章节：{h2}\n小节：{h3 or "（无小节）"}\n\n'
        starts = [0]
        while starts[-1] + size < len(body):
            starts.append(starts[-1] + size - overlap)
        catalog.append({'section_id': section_id, 'book': book, 'h2': h2, 'h3': h3,
                        'intro': body[:180], 'sample': body[:1300], 'characters': len(body)})
        for index, start in enumerate(starts, 1):
            end = min(start + size, len(body))
            text = prefix + body[start:end]
            chunk_id = sha(f'{section_id}:{size}:{overlap}:{index}:{sha(body)}')
            provenance = [source for source in sources if source['start'] < end and source['end'] > start]
            first = provenance[0]
            chunks.append({'id': int(chunk_id[:12], 16) + 1000000000,
                'chunk_id': chunk_id, 'section_id': section_id, 'book': book, 'h2': h2, 'h3': h3,
                'tianji_chunk': text, 'body': body[start:end], 'chunk_index': index,
                'chunk_total': len(starts), 'body_start': start, 'body_end': end,
                'content_hash': sha(text), 'sources': provenance,
                **{key: first.get(key) for key in ('bvid', 'part', 'section', 't_hms')},
                'note': '同一章节连续原文；完整视频与时间定位见 sources。'})
    if len({row['id'] for row in chunks}) != len(chunks):
        raise ValueError('numeric chunk ID collision')
    return chunks, catalog


def make_catalog(sections):
    books = OrderedDict()
    chapters = OrderedDict()
    for row in sections:
        books.setdefault(row['book'], []).append(row['h2'])
        chapters.setdefault((row['book'], row['h2']), []).append(row)
    return {'version': 1, 'intro_method': '原文摘录与真实目录，非模型补写',
        'books': [{'book': book, 'intro': '本书讲解：' + '、'.join(dict.fromkeys(titles))[:600]}
                  for book, titles in books.items()],
        'chapters': [{'book': book, 'h2': h2,
            'intro': ('小节：' + '、'.join(row['h3'] for row in rows if row['h3']) + '。' + rows[0]['intro'])[:350]}
            for (book, h2), rows in chapters.items()],
        'sections': [{key: value for key, value in row.items() if key != 'sample'} for row in sections]}


def reference_sources(rows):
    """Keep chunk citations and all original video locations independently linkable."""
    expanded = []
    for row in rows:
        expanded.append(row)
        for source in row.get('sources') or []:
            if source.get('original_id'):
                expanded.append(source | {'id': source['original_id']})
    return expanded


def catalog_from_chunks(rows):
    """Rebuild introductions from PG, without shipping a copy of corpus text."""
    sections = OrderedDict()
    for row in rows:
        section = sections.setdefault(row['section_id'], {
            'section_id': row['section_id'], 'book': row['book'],
            'h2': row['h2'], 'h3': row['h3'], 'body': ''})
        # The query supplies chunk order; skip overlap already present in the body.
        offset = len(section['body']) - row['body_start']
        if not 0 <= offset <= len(row['body']):
            raise ValueError('Corpus chunks are incomplete or out of order')
        section['body'] += row['body'][offset:]
    return make_catalog([{
        **{key: row[key] for key in ('section_id', 'book', 'h2', 'h3')},
        'intro': row['body'][:180], 'characters': len(row['body'])
    } for row in sections.values()])
