"""Build a source-only release without relying on local Git metadata."""
import argparse
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'README.md', 'LICENSE', 'NOTICE', 'CONTRIBUTING.md', 'pyproject.toml',
    'uv.lock', 'MANIFEST.in', 'Dockerfile', 'compose.yaml', 'compose.dev.yaml',
    '.env.example', '.gitignore', '.dockerignore',
}
DIRECTORIES = {'src', 'static', 'sql', 'scripts', 'tests', 'docs', 'deploy', '.github'}
EXCLUDED = {'__pycache__', '.pytest_cache', 'certbot', 'node_modules', '.DS_Store'}
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{24,}')
REQUIRED_RESOURCES = {
    Path('src/ziwei/data') / name for name in (
        'china_divisions.json', 'division_names_snapshot.json',
        'taiwan_townships_snapshot.json', 'README.md', 'LICENSE-AreaCity.txt',
        'LICENSE-mumuy.txt', 'LICENSE-taiwan-atlas.txt',
    )
}


def source_files():
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if relative.parts[0] not in FILES | DIRECTORIES:
            continue
        if any(part in EXCLUDED or part.endswith('.egg-info') for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f'Release cannot include symlinks: {relative}')
        if not path.is_file():
            continue
        if path.suffix in {'.pyc', '.pyo', '.pem', '.key', '.zst', '.jsonl', '.log'}:
            continue
        if path.name.startswith('.env') and relative.as_posix() != '.env.example':
            continue
        if path.name == 'tianji_catalog.json':
            continue
        if SECRET.search(path.read_bytes()):
            raise ValueError(f'Potential secret in {relative}; review before publishing')
        yield path, relative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/ziwei-agent-source.tar.gz'))
    args = parser.parse_args()
    # Validate all input before opening output; never publish a partial checked set.
    files = list(source_files())
    missing = REQUIRED_RESOURCES - {relative for _, relative in files}
    if missing:
        raise ValueError('Required location resources are missing: ' +
                         ', '.join(str(path) for path in sorted(missing)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output, 'w:gz') as archive:
        for path, relative in files:
            info = archive.gettarinfo(str(path), arcname='ziwei-agent/' + relative.as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            with path.open('rb') as stream:
                archive.addfile(info, stream)
    print(f'Created {args.output}: {len(files)} files, {args.output.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
