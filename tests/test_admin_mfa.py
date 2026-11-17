"""Security checks for the platform's opt-in SMS second factor."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

import pyotp


class Cache:
    def __init__(self):
        self.data = {}
        self.commands = []
    def make_key(self, key): return 'site|' + key
    def get(self, key): return self.data.get(key)
    def ttl(self, key): return 60
    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data: return False
        self.data[key] = value
        return True
    def delete(self, *keys):
        for key in keys: self.data.pop(key, None)
    def eval(self, script, n, key): return self.data.pop(key, None)
    def pipeline(self, **kwargs): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def incr(self, key):
        self.data[key] = self.data.get(key, 0) + 1
        self.commands.append(self.data[key])
        return self
    def expire(self, key, seconds):
        self.commands.append(True)
        return self
    def execute(self):
        result, self.commands = self.commands, []
        return result


class Flags(dict):
    def __setattr__(self, key, value): self[key] = value


class AdminMfaTests(unittest.TestCase):
    def setUp(self):
        self.f = f = types.ModuleType('frappe')
        f.conf = {'il_control_plane': 1, 'il_admin_sms_mfa_enabled': 1}
        f.cache = Cache()
        f.flags = Flags()
        f.form_dict = {}
        f.AuthenticationError = PermissionError
        f.safe_decode = lambda v: v.decode() if isinstance(v, bytes) else v
        f.throw = lambda message, error: (_ for _ in ()).throw(error(message))
        self.user = 'admin@example.test'
        self.manager = types.SimpleNamespace(user=self.user)
        f.flags.il_admin_mfa_login_manager = self.manager
        f.local = types.SimpleNamespace(login_manager=self.manager, request_ip='127.0.0.1', response={})
        owner = types.ModuleType('institute_lms.owner_access')
        owner.is_owner = lambda user: user == self.user
        owner.access_level = lambda user: 'Admin' if user == self.user else None
        self.owner = owner
        invite = types.ModuleType('institute_lms.admin_invites')
        invite.throttle = Mock()
        notify = types.ModuleType('institute_lms.notify_platform')
        notify.send = Mock(return_value={'accepted': True})
        self.notify = notify
        self.modules = patch.dict(sys.modules, {'frappe': f, 'institute_lms.owner_access': owner,
            'institute_lms.admin_invites': invite, 'institute_lms.notify_platform': notify})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location('institute_lms.mfa_under_test',
            Path(__file__).parents[1] / 'institute_lms/admin_mfa.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.secret = pyotp.random_base32()
        self.counter = 123456
        self.otp = pyotp.HOTP(self.secret).at(self.counter)

    def challenge(self):
        self.m.send_token(self.secret, self.counter, '+94700000000')
        for key, value in {'_usr': self.user, '_pwd': 'test-only', '_otp_secret': self.secret,
                           '_token': str(self.counter)}.items():
            self.f.cache.set('test' + key, value)
        self.f.form_dict.update(tmp_id='test', otp=self.otp)

    def test_password_only_and_oauth_cannot_create_admin_session(self):
        with self.assertRaisesRegex(PermissionError, 'SMS verification'):
            self.m.validate_login(self.manager)

    def test_delivered_code_is_single_use_and_credentials_are_cleared(self):
        self.challenge()
        self.m.before_login(self.manager)
        self.m.validate_login(self.manager)
        self.assertTrue(self.f.flags['il_admin_mfa_verified'])
        self.assertIsNone(self.f.cache.get('test_pwd'))
        with self.assertRaises(PermissionError): self.m.validate_login(self.manager)
        with self.assertRaises(PermissionError): self.m.before_login(self.manager)

    def test_five_wrong_guesses_invalidate_challenge(self):
        self.challenge()
        self.f.form_dict['otp'] = 'invalid'
        for _ in range(5):
            with self.assertRaises(PermissionError): self.m.before_login(self.manager)
        self.f.form_dict['otp'] = self.otp
        with self.assertRaises(PermissionError): self.m.before_login(self.manager)
        self.assertIsNone(self.f.cache.get('test_pwd'))

    def test_correct_fifth_guess_is_allowed(self):
        self.challenge()
        self.f.form_dict['otp'] = 'invalid'
        for _ in range(4):
            with self.assertRaises(PermissionError): self.m.before_login(self.manager)
        self.f.form_dict['otp'] = self.otp
        self.m.before_login(self.manager)
        self.m.validate_login(self.manager)

    def test_expired_native_challenge_cannot_use_totp_fallback(self):
        self.challenge()
        self.f.cache.delete('test_token')
        with self.assertRaises(PermissionError): self.m.before_login(self.manager)

    def test_expired_delivery_proof_is_rejected(self):
        self.challenge()
        self.f.cache.delete(self.m.proof_key(self.user, self.secret, self.otp))
        with self.assertRaises(PermissionError): self.m.before_login(self.manager)

    def test_failed_sms_never_produces_login_proof(self):
        self.notify.send.return_value = {'accepted': False}
        with self.assertRaises(PermissionError): self.m.send_token(self.secret, self.counter, '+94700000000')
        self.assertIsNone(self.f.cache.get(self.m.proof_key(self.user, self.secret, self.otp)))

    def test_resend_cooldown_does_not_send_twice(self):
        self.challenge()
        with self.assertRaisesRegex(PermissionError, 'one minute'):
            self.m.send_token(self.secret, self.counter, '+94700000000')
        self.assertEqual(self.notify.send.call_count, 1)
        self.assertEqual(self.f.local.response['mfa_retry_after_seconds'], 60)

    def test_missing_phone_fails_closed(self):
        with self.assertRaises(PermissionError): self.m.send_token(self.secret, self.counter, None)
        self.notify.send.assert_not_called()

    def test_proof_cannot_be_used_by_another_user(self):
        self.challenge()
        self.m.before_login(self.manager)
        self.manager.user = 'other-admin@example.test'
        self.owner.access_level = lambda user: 'Admin'
        with self.assertRaises(PermissionError): self.m.validate_login(self.manager)

    def test_non_admin_is_unchanged(self):
        self.manager.user = 'student@example.test'
        self.m.validate_login(self.manager)
        self.assertFalse(self.f.flags.get('il_admin_mfa_verified'))

    def test_full_administrators_do_not_require_sms(self):
        for level in ('Primary', 'Administrator'):
            with self.subTest(level=level):
                self.owner.access_level = lambda user: level
                self.assertFalse(self.m.required(self.user))
                self.m.validate_login(self.manager)
        self.assertFalse(self.m.required('Administrator'))
        self.notify.send.assert_not_called()

    def test_access_level_change_is_rechecked(self):
        self.assertTrue(self.m.required(self.user))
        self.owner.access_level = lambda user: 'Administrator'
        self.assertFalse(self.m.required(self.user))
        self.owner.access_level = lambda user: 'Admin'
        with self.assertRaises(PermissionError):
            self.m.validate_login(self.manager)

    def test_disabled_flag_and_campus_are_unchanged(self):
        for key in ('il_control_plane', 'il_admin_sms_mfa_enabled'):
            with self.subTest(key=key):
                original = self.f.conf[key]
                self.f.conf[key] = 0
                self.m.validate_login(self.manager)
                self.assertFalse(self.m.required(self.user))
                self.f.conf[key] = original

    def test_disabled_site_keeps_framework_sms_delivery(self):
        self.f.conf['il_admin_sms_mfa_enabled'] = 0
        with patch.object(self.m, 'framework_sms', return_value=True) as fallback:
            self.assertTrue(self.m.send_token(self.secret, self.counter, '+94700000000'))
            fallback.assert_called_once_with(self.secret, self.counter, '+94700000000')
        self.notify.send.assert_not_called()

    def test_new_invited_admin_enrolls_with_verified_phone(self):
        doc = types.SimpleNamespace(enabled=1, user=self.user, phone='+94700000000',
                                    get=lambda field: 'verified timestamp')
        with patch.object(self.m, 'enroll') as enroll:
            self.m.sync_access(doc)
            enroll.assert_called_once_with(self.user, '+94700000000')

    def test_revoked_access_does_not_enroll(self):
        doc = types.SimpleNamespace(enabled=0)
        with patch.object(self.m, 'enroll') as enroll:
            self.m.sync_access(doc)
            enroll.assert_not_called()


if __name__ == '__main__': unittest.main()
