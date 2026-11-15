"""The password step must be unlocked by server-side SMS verification."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, MagicMock, patch


class AdminInviteVerificationTests(unittest.TestCase):
    def setUp(self):
        f = types.ModuleType('frappe')
        f.whitelist = lambda **kwargs: lambda fn: fn
        f.conf = {'encryption_key': 'unit-test-only'}
        f.local = types.SimpleNamespace(request_ip='127.0.0.1')
        f.session = types.SimpleNamespace(user='Guest')
        f.PermissionError = PermissionError
        f.db = Mock()
        f.cache = Mock()
        def fail(message, kind=ValueError):
            raise kind(message)
        f.throw = fail
        utils = types.ModuleType('frappe.utils')
        utils.add_to_date = Mock()
        utils.get_datetime = Mock()
        utils.now_datetime = Mock()
        owner = types.ModuleType('institute_lms.owner_access')
        owner.LEVELS = ('Admin', 'Administrator')
        owner.primary_email = Mock()
        owner.require_manager = Mock()
        owner.can_manage = Mock(return_value=True)
        self.owner = owner
        self.modules = patch.dict(sys.modules, {'frappe': f, 'frappe.utils': utils,
                                                'institute_lms.owner_access': owner})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location('institute_lms.admin_invites_under_test',
            Path(__file__).parents[1] / 'institute_lms/admin_invites.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.raw_pending = self.m.pending
        self.raw_throttle = self.m.throttle
        self.f = f
        self.doc = types.SimpleNamespace(token_hash='unit-token-hash', email='invite@example.test')
        self.phone = '+94700000000'
        self.saved = {'phone': self.phone, 'digest': self.m.code_digest(self.doc, self.phone, '123456'),
                      'created': self.m.time.time(), 'attempts': 0}
        f.cache.get_value.return_value = self.saved
        self.m.pending = Mock(return_value=self.doc)
        self.m.throttle = Mock()

    def test_verify_returns_no_access_or_code(self):
        result = self.m.verify_code('token', self.doc.email, '0700000000', '123456')
        self.assertEqual(set(result), {'verified', 'phone_hint'})
        self.assertTrue(result['verified'])
        self.m.pending.assert_called_once_with('token', lock=True)
        self.assertEqual(self.saved['attempts'], 0)

    def test_wrong_code_exhausts_shared_attempt_limit(self):
        for _ in range(5):
            with self.assertRaisesRegex(ValueError, 'did not match'):
                self.m.check_code(self.doc, self.phone, '999999')
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.m.check_code(self.doc, self.phone, '123456')

    def test_correct_fifth_attempt_can_be_rechecked_when_saving(self):
        self.saved['attempts'] = 4
        self.m.check_code(self.doc, self.phone, '123456')
        self.m.check_code(self.doc, self.phone, '123456')
        self.assertEqual(self.saved['attempts'], 4)

    def test_expired_challenge_does_not_unlock_password(self):
        self.saved['created'] -= 601
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.m.verify_code('token', self.doc.email, self.phone, '123456')

    def test_phone_cannot_be_swapped(self):
        with self.assertRaisesRegex(ValueError, 'same mobile'):
            self.m.verify_code('token', self.doc.email, '+94700000001', '123456')

    def test_email_cannot_be_swapped(self):
        with self.assertRaisesRegex(ValueError, 'same email'):
            self.m.verify_code('token', 'other@example.test', self.phone, '123456')

    def test_missing_or_resend_replaced_code_is_rejected(self):
        self.f.cache.get_value.return_value = None
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.m.check_code(self.doc, self.phone, '123456')
        self.f.cache.get_value.return_value = self.saved
        self.saved['digest'] = self.m.code_digest(self.doc, self.phone, '654321')
        with self.assertRaisesRegex(ValueError, 'did not match'):
            self.m.check_code(self.doc, self.phone, '123456')

    def test_accept_rechecks_sms_before_creating_account(self):
        self.m.check_password = Mock()
        self.saved['created'] -= 601
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.m.accept('token', self.doc.email, self.phone, '123456', 'test phrase', 'test phrase')

    def test_existing_session_cannot_enter_any_invitation_endpoint(self):
        self.f.session.user = 'admin@example.test'
        for fn, args in [(self.m.details, ('token',)),
                         (self.m.send_code, ('token', self.doc.email, self.phone)),
                         (self.m.verify_code, ('token', self.doc.email, self.phone, '123456')),
                         (self.m.accept, ('token', self.doc.email, self.phone, '123456', 'password', 'password'))]:
            with self.assertRaises(PermissionError):
                fn(*args)
        self.m.pending.assert_not_called()
        self.m.throttle.assert_not_called()

    def test_revoked_inviter_cannot_leave_a_usable_invitation(self):
        self.doc.status = 'Pending'
        self.doc.expires_at = 'future'
        self.doc.invited_by = 'revoked@example.test'
        self.f.get_doc = Mock(return_value=self.doc)
        self.m.get_datetime.return_value = 2
        self.m.now_datetime.return_value = 1
        self.owner.can_manage.return_value = False
        with self.assertRaisesRegex(ValueError, 'no longer authorized'):
            self.raw_pending('token')
        self.owner.can_manage.assert_called_with('revoked@example.test')

    def test_existing_admin_cannot_be_overwritten_by_old_invitation(self):
        self.m.check_password = Mock()
        self.f.db.exists.return_value = True
        with self.assertRaisesRegex(ValueError, 'already has admin access'):
            self.m.accept('token', self.doc.email, self.phone, '123456', 'password', 'password')
        self.f.db.exists.assert_called_once_with('IL Owner Access', {'user': self.doc.email, 'enabled': 1})

    def test_rate_limit_uses_atomic_redis_transaction(self):
        self.f.cache.pipeline = MagicMock()
        pipe = self.f.cache.pipeline.return_value.__enter__.return_value
        pipe.incr.return_value = pipe
        pipe.expire.return_value = pipe
        pipe.execute.return_value = (6, True)
        with self.assertRaisesRegex(ValueError, 'Too many'):
            self.raw_throttle('unit-key', 60, 5)
        self.f.cache.pipeline.assert_called_once_with(transaction=True)
        self.f.cache.set_value.assert_not_called()


if __name__ == '__main__':
    unittest.main()
