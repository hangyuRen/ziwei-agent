import csv
import io
import json

import pytest

from ziwei import datasets
from ziwei.models import SECTIONS
from ziwei.tianji_chunks import build_chunks, catalog_from_chunks, make_catalog


def test_year_selection_is_bounded_and_deduplicated():
    assert datasets.parse_years('2001,2000-2002,2026') == [2000, 2001, 2002, 2026]
    for invalid in ('', '1999', '2027', '2002-2000', '2000;echo x', '2000,'):
        with pytest.raises(ValueError):
            datasets.parse_years(invalid)


def test_chart_csv_preserves_multiline_unicode_and_metadata():
    obj = {'k': '2000-01-01-0-male', 'y': 2000, 'm': 1, 'd': 1,
           'h': 0, 'g': 'male', 'c': {key: '内容,"引号"\n下一行' for key in SECTIONS}}
    values = datasets.chart_values(obj, 2000)
    stream = io.StringIO()
    csv.writer(stream).writerow(values)
    result = next(csv.reader(io.StringIO(stream.getvalue())))
    assert json.loads(result[6]) == obj['c']
    with pytest.raises(ValueError):
        datasets.chart_values(obj, 2001)
    with pytest.raises(ValueError):
        datasets.chart_values(obj | {'h': 12}, 2000)


def test_download_does_not_publish_corrupt_bytes(tmp_path, monkeypatch):
    path = tmp_path / 'shard'
    path.write_bytes(b'old-cache')
    monkeypatch.setattr(datasets, 'urlopen', lambda *a, **kw: io.BytesIO(b'tampered'))
    monkeypatch.setattr(datasets.time, 'sleep', lambda _: None)
    with pytest.raises(ValueError, match='SHA-256'):
        datasets.download('https://example.org/file', path, datasets.sha('expected'))
    assert path.read_bytes() == b'old-cache'
    assert sorted(item.name for item in tmp_path.iterdir()) == ['shard']
    monkeypatch.setattr(datasets, 'urlopen', lambda *a, **kw: io.BytesIO(b'expected'))
    datasets.download('https://example.org/file', path, datasets.sha('expected'))
    monkeypatch.setattr(datasets, 'urlopen', lambda *a, **kw: pytest.fail('verified cache should be offline'))
    assert datasets.download('https://example.org/file', path, datasets.sha('expected')) == path


def test_corpus_uses_validated_sources_and_reproducible_ids(tmp_path):
    path = tmp_path / 'entries.jsonl'
    row = {'book': '书', 'h2': '章', 'quote': '测试文字' * 180,
           'bvid': 'BV-example', 'part': 2, 't_hms': '00:01:23'}
    path.write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
    chunks = datasets.corpus_chunks(path)
    assert chunks == datasets.corpus_chunks(path)
    assert all(c['sources'][0]['original_id'] > 1000000000 for c in chunks)
    assert all(c['sources'][0]['t_hms'] == '00:01:23' for c in chunks)
    path.write_text('{"book":"书","h2":"章","quote":""}')
    with pytest.raises(ValueError):
        datasets.corpus_chunks(path)


def test_database_catalog_matches_original_and_requires_complete_chunks():
    chunks, sections = build_chunks([
        {'book': '书', 'h2': '章', 'quote': '甲' * 1200},
        {'book': '书', 'h2': '另一章', 'quote': '乙' * 10}])
    assert catalog_from_chunks(chunks) == make_catalog(sections)
    with pytest.raises(ValueError):
        catalog_from_chunks(chunks[1:])
    assert catalog_from_chunks([])['sections'] == []
