"""Git's actual ignore semantics must preserve runtime assets in fresh clones."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_git_ignores_downloads_but_keeps_location_resources(tmp_path):
    git = shutil.which('git')
    if git is None:
        pytest.skip('Git is needed to check ignore semantics')
    subprocess.run([git, 'init', '-q', str(tmp_path)], check=True)
    shutil.copyfile(ROOT / '.gitignore', tmp_path / '.gitignore')
    resources = [str(path.relative_to(ROOT)) for path in (ROOT / 'src/ziwei/data').iterdir()]
    assert len(resources) == 7
    private = ['data/upstream/entries.jsonl', 'data/upstream/year-2000.jsonl.zst',
               'src/ziwei/data/tianji_catalog.json', '.env', '.env.docker',
               'deploy/certbot/conf/live/example/privkey.pem']
    candidates = resources + private + ['.env.example']
    result = subprocess.run([git, 'check-ignore', '--verbose', '--stdin'], cwd=tmp_path,
                            input='\n'.join(candidates) + '\n', capture_output=True, text=True)
    assert result.returncode == 0
    ignored = set()
    for line in result.stdout.splitlines():
        rule, name = line.split('\t', 1)
        if not rule.split(':', 2)[2].startswith('!'):
            ignored.add(name)
    assert ignored == set(private)
    # Staging, rather than only looking at files on disk, reproduces a fresh checkout.
    for name in resources:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    subprocess.run([git, 'add', 'src/ziwei/data'], cwd=tmp_path, check=True)
    tracked = subprocess.check_output([git, 'ls-files'], cwd=tmp_path, text=True)
    assert set(tracked.splitlines()) == set(resources)
