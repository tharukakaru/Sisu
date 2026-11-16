"""Installer ordering and failure boundaries; no SSH, database or network calls."""
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('merged_installer', Path(__file__).resolve().parents[1] / 'scripts/deploy-production-merged.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / 'app'
        self.app.mkdir()
        self.name = 'institute_lms/example.py'
        (self.app / 'institute_lms').mkdir()
        (self.app / self.name).write_bytes(b'old = True\n')
        self.data = b'new = True\n'
        self.manifest = {'commit': 'test', 'files': {self.name: {
            'before': installer.fingerprint(self.name, b'old = True\n'),
            'sha256': installer.sha(self.data), 'generated': False}}, 'required_assets': {}}

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, data=None, duplicate=False):
        raw = json.dumps(self.manifest).encode()
        path = self.root / 'release.tgz'
        with tarfile.open(path, 'w:gz') as bundle:
            pairs = [('manifest.json', raw), (self.name, self.data if data is None else data)]
            if duplicate:
                pairs.append(pairs[-1])
            for name, content in pairs:
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                bundle.addfile(entry, io.BytesIO(content))
        return path, installer.sha(raw)

    def test_baseline_and_already_applied_release_are_accepted(self):
        path, digest = self.archive()
        self.assertEqual(installer.inspect_release(path, self.app, digest)[1][self.name], self.data)
        (self.app / self.name).write_bytes(self.data)
        installer.inspect_release(path, self.app, digest)

    def test_unknown_production_edit_is_not_overwritten(self):
        path, digest = self.archive()
        (self.app / self.name).write_bytes(b'operator_hotfix = True\n')
        with self.assertRaisesRegex(RuntimeError, 'Source conflict'):
            installer.inspect_release(path, self.app, digest)
        self.assertIn(b'operator_hotfix', (self.app / self.name).read_bytes())

    def test_corrupt_payload_and_duplicate_entries_are_rejected(self):
        path, digest = self.archive(data=b'wrong')
        with self.assertRaisesRegex(RuntimeError, 'checksum'):
            installer.inspect_release(path, self.app, digest)
        path, digest = self.archive(duplicate=True)
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            installer.inspect_release(path, self.app, digest)

    def test_installer_and_required_asset_mismatches_stop_preflight(self):
        path, digest = self.archive()
        with self.assertRaisesRegex(RuntimeError, 'do not match'):
            installer.inspect_release(path, self.app, 'bad')
        self.manifest['required_assets']['institute_lms/public/portal/missing.js'] = 'bad'
        path, digest = self.archive()
        with self.assertRaisesRegex(RuntimeError, 'asset is missing'):
            installer.inspect_release(path, self.app, digest)

    def test_path_escape_is_rejected(self):
        for name in ('../other', '/etc/passwd', 'institute_lms/../../other', 'sites/site_config.json'):
            with self.assertRaises(RuntimeError):
                installer.safe_path(self.app, name)

    def apply(self, failure=None):
        bench = self.root / 'bench'
        (bench / 'sites/test').mkdir(parents=True)
        (bench / 'sites/test/site_config.json').write_text('{}')
        (bench / 'sites/common_site_config.json').write_text('{}')
        backup = self.root / 'backup'
        backup.mkdir()
        (backup / 'catalog-before.json').write_text('{}')
        calls = []

        def run(command, log, as_sisu=False):
            calls.append(command)
            if 'backup' in command:
                if failure == 'backup':
                    raise RuntimeError('Backup failed')
                (Path(command[-1]) / 'database.sql.gz').write_bytes(b'backup')
            if 'migrate' in command and failure == 'migration':
                raise RuntimeError('Migration failed')

        with patch.object(installer, 'APP', self.app), patch.object(installer, 'BENCH', bench), \
             patch.object(installer, 'SITES', ('test',)), patch.object(installer, 'run', run), \
             patch.object(installer.os, 'chown', create=True), patch.object(installer, 'health') as health, \
             patch.object(installer.subprocess, 'run') as stop:
            if failure:
                with self.assertRaises(RuntimeError):
                    installer.apply_release(self.manifest, {self.name: self.data}, backup, io.StringIO(), 1, 1)
            else:
                installer.apply_release(self.manifest, {self.name: self.data}, backup, io.StringIO(), 1, 1)
            return calls, health.call_count, stop.call_args

    def test_backup_failure_reopens_original_code_without_migration(self):
        calls, health, _ = self.apply('backup')
        self.assertFalse(any('migrate' in c for c in calls))
        self.assertEqual((self.app / self.name).read_bytes(), b'old = True\n')
        self.assertTrue(any(c[-2:] == ['set-maintenance-mode', 'off'] for c in calls))
        self.assertEqual(health, 0)

    def test_migration_failure_keeps_new_code_and_stops_services(self):
        calls, health, stop = self.apply('migration')
        self.assertEqual((self.app / self.name).read_bytes(), self.data)
        self.assertFalse(any(c[-2:] == ['set-maintenance-mode', 'off'] for c in calls))
        self.assertIn('stop', stop.args[0])
        self.assertEqual(health, 0)

    def test_success_backs_up_before_migration_and_checks_health_before_workers(self):
        calls, health, _ = self.apply()
        backup = next(i for i, c in enumerate(calls) if 'backup' in c)
        migrate = next(i for i, c in enumerate(calls) if 'migrate' in c)
        self.assertLess(backup, migrate)
        self.assertEqual(health, 1)
        self.assertEqual(calls[-1], ['supervisorctl', 'start', installer.SERVICES[1]])
        self.assertEqual((self.root / 'backup/source' / self.name).read_bytes(), b'old = True\n')


if __name__ == '__main__':
    unittest.main()
