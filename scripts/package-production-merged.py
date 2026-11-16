"""Package committed application changes since the confirmed production release."""
import ast
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'f013d40'
TEXT = {'.py', '.json', '.vue', '.js', '.mjs', '.css', '.html', '.toml', '.txt'}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def fingerprint(name, data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if Path(name).suffix in TEXT else data).hexdigest()


def main():
    commit = git('rev-parse', 'HEAD').decode().strip()
    names = git('diff', '--name-only', '--diff-filter=AM', BASELINE, commit,
                '--', 'institute_lms', 'frontend', 'pyproject.toml').decode().splitlines()
    deleted = git('diff', '--name-only', '--diff-filter=D', BASELINE, commit,
                  '--', 'institute_lms', 'frontend', 'pyproject.toml').decode().splitlines()
    if any(not p.startswith('institute_lms/public/portal/') for p in deleted):
        raise RuntimeError('Source deletion needs an explicit migration plan')
    names = [p for p in names if not p.startswith('frontend/tests/')]
    # Previous deployments uploaded selected bundles, so a Git baseline does
    # not guarantee that unchanged generated assets exist on the server.
    assets = git('ls-tree', '-r', '--name-only', commit, '--', 'institute_lms/public/portal').decode().splitlines()
    names = sorted(set(names) | set(assets))
    manifest = {'commit': commit, 'baseline': git('rev-parse', BASELINE).decode().strip(),
                'files': {}, 'required_assets': {}}
    payload = {}
    for name in names:
        data = git('show', commit + ':' + name)
        if name.endswith('.py'):
            ast.parse(data.decode('utf-8-sig'))
        old = subprocess.run(['git', 'show', BASELINE + ':' + name], cwd=ROOT, capture_output=True)
        manifest['files'][name] = {'before': fingerprint(name, old.stdout) if old.returncode == 0 else None,
            'sha256': hashlib.sha256(data).hexdigest(),
            'generated': name.startswith('institute_lms/public/portal/') or name == 'institute_lms/www/campus.html'}
        payload[name] = data
    for name in assets:
        data = payload[name]
        manifest['required_assets'][name] = hashlib.sha256(data).hexdigest()
    raw = json.dumps(manifest, sort_keys=True, indent=2).encode()
    output = ROOT.parent / 'release-candidate/sisu-production-merged.tgz'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as archive:
        for name, data in {**payload, 'manifest.json': raw}.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(data))
    installer = ROOT / 'scripts/deploy-production-merged.py'
    source = installer.read_text(encoding='utf-8')
    source = re.sub(r"MANIFEST_DIGEST = '[^']+'", "MANIFEST_DIGEST = '" + hashlib.sha256(raw).hexdigest() + "'", source)
    installer.write_text(source, encoding='utf-8')
    print('PACKAGED:', commit, len(payload), 'files;', output.stat().st_size, 'compressed bytes')
    print('Required assets included in archive:', len(manifest['required_assets']))


if __name__ == '__main__':
    main()
