"""Explicit, pinned local-bench dependency backport. Never a deployment hook."""
import json
import os
from pathlib import Path
import subprocess


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout


def main():
    if os.environ.get('SISU_LOCAL_SECURITY_UPGRADE') != '1':
        raise SystemExit('Set SISU_LOCAL_SECURITY_UPGRADE=1 for an explicit local upgrade.')
    bench = Path('/home/frappe/workspace/frappe-bench')
    config = json.loads((bench/'sites/common_site_config.json').read_text())
    config.update(json.loads((bench/'sites/sisuacademylk.com/site_config.json').read_text()))
    if not Path('/.dockerenv').exists() or config.get('db_host') != 'mariadb' or config.get('host_name') != 'http://127.0.0.1:5400':
        raise SystemExit('Only the named local Docker bench is supported.')
    here = Path(__file__).resolve().parent
    revisions = {
        'frappe': '980bdb0aa497ef787679353e0dbc16fd7cefbb36',
        'lms': '389d8a2720bfbd4b2e0de3f0f3c15d4cf0485d1e',
    }
    pending = []
    for app, revision in revisions.items():
        root = bench/'apps'/app
        if run('git', 'rev-parse', 'HEAD', cwd=root).strip() != revision:
            raise SystemExit(f'{app}: revision changed; review compatibility before applying.')
        patch = str(here/(app+'.patch'))
        reverse = subprocess.run(['git','apply','--reverse','--check',patch],cwd=root,capture_output=True)
        if reverse.returncode == 0:
            print(app + ': dependency patch already present')
        else:
            run('git','apply','--check',patch,cwd=root)
            pending.append((root, patch))
    backup = bench.parent/'security-dependency-backup-20261117'
    backup.mkdir(exist_ok=True)
    freeze = backup/'requirements-before.txt'
    if not freeze.exists():
        freeze.write_text(run('uv','pip','freeze','--python',str(bench/'env/bin/python')))
    for app in revisions:
        path = backup/(app+'-pyproject.toml')
        if not path.exists():
            path.write_text((bench/'apps'/app/'pyproject.toml').read_text())
    for root, patch in pending:
        run('git','apply',patch,cwd=root)
    subprocess.run(['uv','pip','install','--python',str(bench/'env/bin/python'),
        '-e','apps/frappe','-e','apps/lms','-e','apps/institute_lms',
        '-c',str(here/'constraints.txt')],cwd=bench,check=True)
    subprocess.run(['uv','pip','check','--python',str(bench/'env/bin/python')],check=True)
    print('Dependency update complete. Restart local services and run the documented checks.')


if __name__ == '__main__':
    main()
