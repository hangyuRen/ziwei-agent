"""Real psql checks in a disposable schema; synthetic data, no model calls."""
import asyncio
import csv
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from uuid import uuid4

import asyncpg

from ziwei.datasets import CHART_COLUMNS, TIANJI_COLUMNS, chart_values
from ziwei.models import SECTIONS
from ziwei.tianji_chunks import build_chunks

ROOT = Path(__file__).resolve().parents[1]


def csv_text(rows):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    for row in rows:
        writer.writerow(['\\N' if value is None else value for value in row])
    return output.getvalue()


async def main():
    url = os.environ['DATABASE_URL']
    conn = await asyncpg.connect(url)
    namespace = 'importcheck_' + uuid4().hex[:16]
    await conn.execute(f'CREATE SCHEMA "{namespace}"')
    environment = dict(os.environ, PGOPTIONS=f'-c search_path={namespace},public')
    try:
        with tempfile.TemporaryDirectory(prefix='ziwei-import-') as directory:
            temporary = Path(directory)
            def psql(path, succeeds=True):
                result = subprocess.run(['psql', url, '-X', '-f', str(path)], cwd=ROOT,
                                        env=environment, capture_output=True, text=True)
                if (result.returncode == 0) != succeeds:
                    raise AssertionError(result.stdout + result.stderr)
            def import_script(kind, output, fails=False):
                helper = temporary / f'{kind}_producer.py'
                helper.write_text('import sys\nsys.stdout.write(' + repr(output) +
                                  ')\nsys.stdout.flush()\nsys.exit(' + ('9' if fails else '0') + ')\n')
                script = (ROOT / 'sql' / f'import_{kind}.sql').read_text()
                program = 'uv run --quiet --no-sync python ' + shlex.quote(str(helper))
                original = 'uv run --quiet --no-sync python scripts/data_stream.py ' + ('chart' if kind == 'charts' else 'tianji')
                assert original in script
                path = temporary / f'{kind}.sql'
                path.write_text(script.replace(original, program))
                return path
            psql(ROOT / 'sql' / 'init.sql')
            psql(ROOT / 'sql' / 'init.sql')
            await conn.execute(f'SET search_path TO "{namespace}",public')
            obj = {'k': '2000-01-01-0-male', 'y': 2000, 'm': 1, 'd': 1, 'h': 0,
                   'g': 'male', 'c': {key: '合成测试,"引号"\n第二行' for key in SECTIONS}}
            chart_sql = import_script('charts', csv_text([chart_values(obj, 2000)]))
            psql(chart_sql)
            psql(chart_sql)
            assert await conn.fetchval('SELECT count(*) FROM chart') == 1
            assert json.loads(await conn.fetchval('SELECT content FROM chart')) == obj['c']
            owner = await conn.fetchval("INSERT INTO auth_user(username,password_hash) VALUES('keep-me','synthetic') RETURNING id")
            chunks, _ = build_chunks([{'book': '测试书', 'h2': '测试章', 'quote': '合成语料' * 180,
                                      'bvid': 'BV-test', 'part': 2, 't_hms': '00:01:00'}])
            records = [tuple(json.dumps(row[key], ensure_ascii=False) if key == 'sources' else row[key]
                             for key in TIANJI_COLUMNS) for row in chunks]
            corpus_sql = import_script('tianji', csv_text(records))
            psql(corpus_sql)
            assert await conn.fetchval('SELECT count(*) FROM tianji_embedding WHERE embedding IS NULL') == len(chunks)
            vector = json.dumps([0.1] * 1024)
            await conn.execute("UPDATE tianji_embedding SET embedding=$1::vector,model='test-model'", vector)
            psql(corpus_sql)
            assert await conn.fetchval("SELECT count(*) FROM tianji_embedding WHERE embedding IS NOT NULL AND model='test-model'") == len(chunks)
            # Exercise invalid CSV and a producer that fails AFTER writing valid CSV.
            broken = obj | {'k': '2000-01-02-0-male', 'd': 2}
            psql(import_script('charts', csv_text([chart_values(broken, 2000)]), fails=True), succeeds=False)
            assert await conn.fetchval('SELECT count(*) FROM chart') == 1
            psql(import_script('charts', 'not,a,valid,row\n'), succeeds=False)
            assert await conn.fetchval('SELECT count(*) FROM chart') == 1
            assert await conn.fetchval('SELECT id FROM auth_user WHERE username=$1', 'keep-me') == owner
    finally:
        await conn.execute(f'DROP SCHEMA "{namespace}" CASCADE')
        await conn.close()
    print('PASS: psql init/import, CSV fidelity, idempotence, vector reuse, producer-failure rollback, malformed-row rollback; isolated schema removed')


if __name__ == '__main__':
    asyncio.run(main())
