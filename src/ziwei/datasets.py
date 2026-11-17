"""Verified upstream downloads and CSV streams consumed by psql's client-side COPY.

No database credentials, user records, model calls, or corpus text are bundled here.
"""
import argparse
import calendar
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from .models import ChartRow, TianjiRow
from .tianji_chunks import build_chunks, sha

CHART_BASE = 'https://github.com/Renhuai123/ziwei-doushu/releases/download/v4.0-13d'
SUMS_SHA256 = '897b532dd13df7c2dc118701277400c33c8b521effbe7f3e2e30eb7030bd3d19'
TIANJI_COMMIT = '462faa4c70af40b8b87ad82ffa82a5823a485e94'
TIANJI_URL = f'https://raw.githubusercontent.com/Renhuai123/nihai-tianji-corpus/{TIANJI_COMMIT}/data/entries.jsonl'
TIANJI_SHA256 = 'f6c49b98084fab7a2d44482dc6fd8ce43b518a439dfcfeba3b2d480d582c8aae'
CHART_COLUMNS = ('chart_key', 'birth_year', 'birth_month', 'birth_day', 'birth_hour',
                 'gender', 'content', 'raw_meta')
TIANJI_COLUMNS = ('id', 'chunk_id', 'section_id', 'book', 'h2', 'h3', 'tianji_chunk',
                 'body', 'chunk_index', 'chunk_total', 'body_start', 'body_end',
                 'sources', 'bvid', 'part', 'section', 't_hms', 'note', 'content_hash')


def file_sha(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def download(url, path, expected):
    """Reuse only verified cache files; publish completed downloads atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and file_sha(path) == expected:
        return path
    for attempt in range(3):
        temporary = None
        try:
            print(f'Downloading {path.name}', file=sys.stderr, flush=True)
            with urlopen(Request(url, headers={'User-Agent': 'ziwei-agent-data-import/1.0'}), timeout=60) as response:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
                    temporary = Path(target.name)
                    for block in iter(lambda: response.read(1024 * 1024), b''):
                        target.write(block)
            if file_sha(temporary) != expected:
                raise ValueError(f'SHA-256 mismatch: {path.name}')
            temporary.replace(path)
            return path
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise RuntimeError('Download failed')


def parse_years(value):
    years = set()
    for part in value.split(','):
        if not re.fullmatch(r'\d{4}(?:-\d{4})?', part.strip()):
            raise ValueError('ZIWEI_CHART_YEARS must look like 2000-2026 or 2000,2026')
        bounds = [int(n) for n in part.strip().split('-')]
        start, end = bounds[0], bounds[-1]
        if not 2000 <= start <= end <= 2026:
            raise ValueError('This application supports chart years 2000–2026')
        years.update(range(start, end + 1))
    return sorted(years)


def chart_values(obj, year):
    row = ChartRow.model_validate(obj)
    if row.y != year or not 0 <= row.h <= 11:
        raise ValueError('Chart year/hour does not match its shard')
    return (row.k, row.y, row.m, row.d, row.h, row.g,
            json.dumps(row.c, ensure_ascii=False),
            json.dumps({'ms': row.ms, 't': row.t}, ensure_ascii=False))


def stream_charts(cache, years):
    manifest = download(f'{CHART_BASE}/SHA256SUMS.txt', cache / 'SHA256SUMS.txt', SUMS_SHA256)
    sums = {}
    for line in manifest.read_text().splitlines():
        checksum, name = line.split(maxsplit=1)
        sums[name.lstrip('*')] = checksum
    for year in years:
        name = f'year-{year}.jsonl.zst'
        path = download(f'{CHART_BASE}/{name}', cache / name, sums[name])
        seen = set()
        with subprocess.Popen(['zstd', '-dc', '--long=27', str(path)],
                              stdout=subprocess.PIPE, text=True, encoding='utf-8') as process:
            try:
                for line in process.stdout:
                    values = chart_values(json.loads(line), year)
                    if values[0] in seen:
                        raise ValueError('Duplicate chart key in upstream shard')
                    seen.add(values[0])
                    yield values
                if process.wait() != 0:
                    raise RuntimeError(f'zstd failed: {name}')
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
        expected = (366 if calendar.isleap(year) else 365) * 24
        if len(seen) != expected:
            raise ValueError(f'Incomplete shard {name}: {len(seen)} != {expected}')
        print(f'Validated {name}: {expected} charts', file=sys.stderr, flush=True)


def corpus_chunks(path):
    records = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = TianjiRow.model_validate_json(line).model_dump()
        if not row['book'].strip() or not row['h2'].strip() or not row['quote'].strip():
            raise ValueError('Empty corpus book, heading or quote')
        identity = json.dumps([row.get(key) or '' for key in
                              ('book', 'h2', 'h3', 'quote', 'bvid', 'part', 't_hms')], ensure_ascii=False)
        row['original_id'] = int(sha('source:' + identity)[:12], 16) + 1000000000
        records.append(row)
    if not records:
        raise ValueError('Empty corpus')
    return build_chunks(records)[0]


def stream_tianji(cache):
    path = download(TIANJI_URL, cache / 'entries.jsonl', TIANJI_SHA256)
    for chunk in corpus_chunks(path):
        yield tuple(json.dumps(chunk[key], ensure_ascii=False) if key == 'sources' else chunk[key]
                    for key in TIANJI_COLUMNS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['chart', 'tianji'])
    args = parser.parse_args()
    cache = Path(os.environ.get('ZIWEI_DATA_DIR', 'data/upstream')).resolve()
    rows = (stream_charts(cache, parse_years(os.environ.get('ZIWEI_CHART_YEARS', '2000-2026')))
            if args.kind == 'chart' else stream_tianji(cache))
    writer = csv.writer(sys.stdout, lineterminator='\n')
    for row in rows:
        writer.writerow(['\\N' if value is None else value for value in row])


if __name__ == '__main__':
    main()
