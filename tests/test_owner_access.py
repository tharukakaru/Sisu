import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class OwnerAccessTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.conf = {'il_owner_email': 'primary@example.test', 'il_owner_provisioned': True}
        self.f.session = types.SimpleNamespace(user='primary@example.test')
        self.f.db = Mock()
        self.f.db.get_value.return_value = 1
        self.f.db.exists.return_value = False
        self.f.PermissionError = PermissionError
        self.f.whitelist = lambda **kw: lambda fn: fn
        def fail(message, kind=ValueError):
            raise kind(message)
        self.f.throw = fail
        self.patch = patch.dict(sys.modules, {'frappe': self.f})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        path = Path(__file__).parents[1] / 'institute_lms/owner_access.py'
        spec = importlib.util.spec_from_file_location('owner_access_under_test', path)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_primary_requires_enabled_user_and_provisioning(self):
        self.assertTrue(self.m.is_owner())
        self.f.db.get_value.return_value = 0
        self.assertFalse(self.m.is_owner())
        self.f.db.get_value.return_value = 1
        self.f.conf['il_owner_provisioned'] = False
        self.assertFalse(self.m.is_owner())

    def test_role_label_does_not_grant_access(self):
        self.f.session.user = 'institute-admin@example.test'
        self.assertFalse(self.m.is_owner())
        with self.assertRaises(PermissionError):
            self.m.require_primary()

    def test_revoked_delegate_loses_access_on_next_request(self):
        self.f.session.user = 'delegate@example.test'
        self.f.db.exists.return_value = True
        self.assertTrue(self.m.is_owner())
        self.f.db.exists.assert_called_with('IL Owner Access', {'user': 'delegate@example.test', 'enabled': 1})
        self.f.db.exists.return_value = False
        self.assertFalse(self.m.is_owner())

    def test_delegate_cannot_manage_access(self):
        self.f.session.user = 'delegate@example.test'
        self.f.db.exists.return_value = True
        with self.assertRaises(PermissionError):
            self.m.add('other@example.test', 'Escalate')
        with self.assertRaises(PermissionError):
            self.m.remove('primary@example.test', 'Remove')

    def test_guest_denied_without_database_lookup(self):
        self.f.session.user = 'Guest'
        self.assertFalse(self.m.is_owner())
        self.f.db.get_value.assert_not_called()


class AccessLevelTests(OwnerAccessTests):
    def test_system_administrator_can_manage(self):
        self.f.session.user = 'Administrator'
        self.f.db.exists.return_value = True
        self.assertEqual(self.m.access_level(), 'Primary')
        self.assertTrue(self.m.can_manage())

    def test_full_authority_delegate_can_manage(self):
        self.f.session.user = 'boss@example.test'
        self.f.db.exists.return_value = True
        self.f.db.get_value.side_effect = lambda doctype, filters, field=None: 'Administrator' if doctype == 'IL Owner Access' else 1
        self.assertTrue(self.m.can_manage())
        self.m.require_manager()

    def test_admin_level_cannot_manage_or_promote(self):
        self.f.session.user = 'admin@example.test'
        self.f.db.exists.return_value = True
        self.f.db.get_value.side_effect = lambda doctype, filters, field=None: 'Admin' if doctype == 'IL Owner Access' else 1
        self.assertEqual(self.m.access_level(), 'Admin')
        with self.assertRaises(PermissionError):
            self.m.set_level('admin@example.test', 'Administrator')

    def test_protected_accounts_cannot_be_removed(self):
        self.f.session.user = 'primary@example.test'
        with self.assertRaises(ValueError):
            self.m.remove('primary@example.test', 'x')
        with self.assertRaises(ValueError):
            self.m.remove('Administrator', 'x')


class DeleteRuleTests(OwnerAccessTests):
    def levels(self, me_level, target):
        def get_value(doctype, filters, field=None):
            if doctype == 'IL Owner Access':
                return me_level if filters.get('user') == self.f.session.user else target
            return 1
        self.f.db.exists.return_value = True
        self.f.db.get_value.side_effect = get_value

    def test_primary_can_delete_and_demote_administrators(self):
        self.levels(None, 'Administrator')
        p = self.m.permissions_for('boss@example.test')
        self.assertEqual(p, {'can_remove': True, 'can_promote': False, 'can_demote': True})

    def test_full_authority_can_delete_and_promote_admins_only(self):
        self.f.session.user = 'boss@example.test'
        self.levels('Administrator', 'Admin')
        self.assertEqual(self.m.permissions_for('a@example.test'), {'can_remove': True, 'can_promote': True, 'can_demote': False})
        self.levels('Administrator', 'Administrator')
        self.assertEqual(self.m.permissions_for('peer@example.test'), {'can_remove': False, 'can_promote': False, 'can_demote': False})
        with self.assertRaises(PermissionError):
            self.m.remove('peer@example.test', 'x')
        with self.assertRaises(PermissionError):
            self.m.set_level('peer@example.test', 'Admin')

    def test_nobody_acts_on_self_or_protected(self):
        self.levels(None, 'Admin')
        for target in ('primary@example.test', 'Administrator'):
            self.assertFalse(any(self.m.permissions_for(target).values()))
