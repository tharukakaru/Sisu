"""Installer ordering and failure boundaries; no SSH, database or network calls."""
import importlib.util
import io
import json
import os
import sys
from types import SimpleNamespace
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

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
            if installer.BACKUP_SITE in command:
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
        backup = next(i for i, c in enumerate(calls) if installer.BACKUP_SITE in c)
        migrate = next(i for i, c in enumerate(calls) if 'migrate' in c)
        self.assertLess(backup, migrate)
        self.assertEqual(health, 1)
        self.assertEqual(calls[-1], ['supervisorctl', 'start', installer.SERVICES[1]])
        self.assertEqual((self.root / 'backup/source' / self.name).read_bytes(), b'old = True\n')




class FrappeProbeWorkingDirectory(unittest.TestCase):
    def test_both_probes_run_from_sites_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            bench = Path(folder)
            (bench / 'sites').mkdir()
            patches = bench / 'apps/institute_lms/institute_lms/patches.txt'
            patches.parent.mkdir(parents=True)
            patches.write_text('')
            def connect():
                self.assertEqual(Path.cwd(), bench / 'sites')
                self.assertEqual((Path.cwd() / '../logs').resolve(), bench / 'logs')
            fake = SimpleNamespace(init=lambda **kw: None, connect=connect,
                get_installed_apps=lambda: ['institute_lms'], destroy=lambda: None,
                db=SimpleNamespace(sql=lambda *a: [], table_exists=lambda *a: True,
                    has_column=lambda *a: True))
            try:
                for probe in (installer.DATABASE_PREFLIGHT, installer.SCHEMA_CHECK):
                    os.chdir(bench)
                    with patch.dict(sys.modules, {'frappe': fake}), patch.object(sys, 'argv', ['probe', 'test']):
                        exec(probe, {})
            finally:
                os.chdir(original)


class PrivateBackupTests(unittest.TestCase):
    def test_full_backup_preserves_existing_directory_and_requires_all_artifacts(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            bench = Path(folder)
            historic = bench / 'sites/test/private/backups/pre-lkr50-migration'
            historic.mkdir(parents=True)
            marker = historic / 'keep.sql'
            marker.write_bytes(b'original backup')
            destination = bench / 'private-release'
            destination.mkdir()
            attrs = ('backup_path_db', 'backup_path_files', 'backup_path_private_files', 'backup_path_conf')
            paths = {attr: str(destination / attr) for attr in attrs}
            generator = Mock(**paths)
            def create(**kwargs):
                self.assertEqual(kwargs, {'ignore_files': False, 'force': True})
                for path in paths.values():
                    Path(path).write_bytes(b'backup')
            generator.get_backup.side_effect = create
            factory = Mock(return_value=generator)
            cleanup = Mock(side_effect=AssertionError('Historical cleanup must not run'))
            conf = SimpleNamespace(db_name='test', db_user='test', db_password='test',
                db_socket=None, db_host='localhost', db_port=3306, db_type='mariadb')
            frappe = SimpleNamespace(conf=conf, init=Mock(), connect=Mock(), destroy=Mock())
            modules = {'frappe': frappe, 'frappe.utils': SimpleNamespace(),
                'frappe.utils.backups': SimpleNamespace(BackupGenerator=factory,
                    delete_temp_backups=cleanup, new_backup=cleanup)}
            try:
                os.chdir(bench)
                with patch.dict(sys.modules, modules), patch.object(sys, 'argv', ['backup', 'test', str(destination)]):
                    exec(installer.BACKUP_SITE, {})
                    self.assertTrue(factory.call_args.kwargs['ignore_conf'])
                    self.assertEqual(marker.read_bytes(), b'original backup')
                    cleanup.assert_not_called()
                    # Missing uploads must stop deployment even with a DB dump.
                    Path(paths['backup_path_private_files']).unlink()
                    generator.get_backup.side_effect = None
                    os.chdir(bench)
                    with self.assertRaisesRegex(RuntimeError, 'artifact missing'):
                        exec(installer.BACKUP_SITE, {})
            finally:
                os.chdir(original)





class RecoveryTests(unittest.TestCase):
    def test_health_uses_authorized_catalog_not_generic_ping(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            entry = app / 'institute_lms/www/campus.html'
            entry.parent.mkdir(parents=True)
            assets = ['/assets/institute_lms/portal/assets/index-test.js', '/assets/institute_lms/portal/assets/index-test.css']
            html = ''.join('<script src="' + a + '"></script>' for a in assets).encode()
            entry.write_bytes(html)
            catalogue = {'message': {'plans': {}, 'currency': 'LKR'}}
            def request(url):
                self.assertNotIn('/api/method/ping', url)
                if url.endswith('public_catalog'): return json.dumps(catalogue).encode()
                if url.endswith('/campus'): return html
                return b'asset'
            manifest = {'required_assets': {'institute_lms/public/' + a.removeprefix('/assets/institute_lms/'): installer.sha(b'asset') for a in assets}}
            with patch.object(installer, 'APP', app), patch.object(installer, 'get_url', side_effect=request), patch.object(installer, 'check_owner_entry') as owner:
                installer.health(manifest, catalogue)
                owner.assert_called_once_with('platform.sisuacademylk.com')

    def test_recovery_checks_before_workers_without_migrations(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = root / 'app'; app.mkdir()
            file = app / 'institute_lms/test.py'; file.parent.mkdir(); file.write_bytes(b'code')
            manifest = {'commit': 'release'}
            (root / 'release.json').write_text(json.dumps(manifest))
            (root / 'catalog-before.json').write_text('{}')
            calls = []
            def run(cmd, *args): calls.append(cmd)
            def health(*args):
                self.assertFalse(any('start' in c for c in calls))
            with patch.object(installer, 'APP', app), patch.object(installer, 'run', side_effect=run), patch.object(installer, 'health', side_effect=health):
                installer.resume_checks(manifest, {'institute_lms/test.py': b'code'}, root)
                self.assertFalse(any('migrate' in c for c in calls))
                self.assertIn(['supervisorctl', 'start', installer.SERVICES[1]], calls)
                calls.clear()
                with patch.object(installer, 'health', side_effect=RuntimeError('unhealthy')):
                    with self.assertRaisesRegex(RuntimeError, 'unhealthy'):
                        installer.resume_checks(manifest, {'institute_lms/test.py': b'code'}, root)
                self.assertFalse(any('start' in c for c in calls))


class OwnerEntryTests(unittest.TestCase):
    def test_expected_login_redirect_required(self):
        response = Mock(status=200)
        response.geturl.return_value = 'https://platform.sisuacademylk.com/login?redirect-to=/campus'
        response.read.return_value = b'<body class="sisu-owner-login">'
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch.object(installer.urllib.request, 'urlopen', return_value=context):
            installer.check_owner_entry('platform.sisuacademylk.com')
            response.geturl.return_value = 'https://platform.sisuacademylk.com/error'
            with self.assertRaises(RuntimeError):
                installer.check_owner_entry('platform.sisuacademylk.com')


if __name__ == '__main__':
    unittest.main()
