import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class AdminProfileTests(unittest.TestCase):
    def setUp(self):
        f=types.ModuleType('frappe')
        f.conf={'il_control_plane':1}
        f.session=types.SimpleNamespace(user='self@example.test')
        f.whitelist=lambda **kwargs:lambda fn:fn
        f.PermissionError=PermissionError
        f.throw=lambda message,error=ValueError:(_ for _ in ()).throw(error(message))
        f.db=Mock();f.get_doc=Mock();f.local=types.SimpleNamespace(login_manager=Mock())
        owner=types.ModuleType('institute_lms.owner_access');owner.is_owner=Mock(return_value=True)
        invite=types.ModuleType('institute_lms.admin_invites');invite.throttle=Mock()
        passwords=types.ModuleType('frappe.utils.password');passwords.check_password=Mock();passwords.update_password=Mock()
        user=types.ModuleType('frappe.core.doctype.user.user')
        user.test_password_strength=Mock(return_value={'feedback':{'password_policy_validation_passed':True}})
        user.is_password_reused=Mock(return_value=False)
        utils=types.ModuleType('frappe.utils');utils.today=lambda:'2026-11-15'
        modules=patch.dict(sys.modules,{'frappe':f,'frappe.utils':utils,'frappe.utils.password':passwords,
          'frappe.core.doctype.user.user':user,'institute_lms.owner_access':owner,'institute_lms.admin_invites':invite})
        modules.start();self.addCleanup(modules.stop)
        spec=importlib.util.spec_from_file_location('institute_lms.admin_profile_test',Path(__file__).parents[1]/'institute_lms/admin_profile.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.f=f;self.owner=owner;self.passwords=passwords;self.user=user;self.invite=invite
        self.new='test-only-unique-password-2026'

    def change(self,**kwargs):
        args={'current_password':'test-current','new_password':self.new,'confirm_password':self.new}
        args.update(kwargs);return self.m.change_password(**args)

    def test_success_targets_self_and_requires_fresh_login(self):
        result=self.change()
        self.passwords.check_password.assert_called_once_with('self@example.test','test-current',delete_tracker_cache=False)
        self.passwords.update_password.assert_called_once_with('self@example.test',self.new,logout_all_sessions=True)
        self.f.local.login_manager.logout.assert_called_once()
        self.assertEqual(result,{'changed':True,'redirect':'/login?redirect-to=/campus'})

    def test_non_admin_and_guest_denied(self):
        self.owner.is_owner.return_value=False
        with self.assertRaises(PermissionError):self.change()
        self.passwords.update_password.assert_not_called()

    def test_campus_denied(self):
        self.f.conf['il_control_plane']=0
        with self.assertRaises(PermissionError):self.change()

    def test_wrong_current_password_cannot_mutate(self):
        self.passwords.check_password.side_effect=PermissionError('Incorrect password')
        with self.assertRaises(PermissionError):self.change()
        self.passwords.update_password.assert_not_called()
        self.f.local.login_manager.logout.assert_not_called()

    def test_password_limits_and_confirmation(self):
        for args in ({'current_password':''},{'new_password':'short'},{'new_password':'x'*129},{'confirm_password':'different'}):
            with self.subTest(args=list(args)),self.assertRaises(ValueError):self.change(**args)
        self.passwords.update_password.assert_not_called()

    def test_weak_password_rejected(self):
        self.user.test_password_strength.return_value={'feedback':{'password_policy_validation_passed':False}}
        with self.assertRaises(ValueError):self.change()
        self.passwords.update_password.assert_not_called()

    def test_reused_password_rejected(self):
        self.user.is_password_reused.return_value=True
        with self.assertRaises(ValueError):self.change()
        self.passwords.update_password.assert_not_called()

    def test_throttle_happens_before_password_check(self):
        self.invite.throttle.side_effect=ValueError('Too many attempts')
        with self.assertRaises(ValueError):self.change()
        self.passwords.check_password.assert_not_called()


if __name__=='__main__':unittest.main()
