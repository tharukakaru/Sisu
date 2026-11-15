from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock
from test_upload_provisioning import function


class TeacherTrial(TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 17, 21)
        self.member = NS(role='Teacher')
        self.account = NS(trial_until=self.now + timedelta(days=14))
        self.lookup = Mock(return_value=self.account)
        self.state = Mock(return_value={'state': 'Trial'})
        self.read = function('account_billing', 'teacher_trial', dict(
            actor=lambda: ('own-workspace', self.member), account=self.lookup,
            state=self.state, get_datetime=lambda value: value, now_datetime=lambda: self.now))

    def test_own_teacher_trial_uses_server_time_without_mutation(self):
        self.assertEqual(self.read(), {'active': True, 'remaining_ms': 14 * 86400000})
        self.lookup.assert_called_once_with('own-workspace', self.member)
        self.now += timedelta(days=13, hours=23)
        self.assertEqual(self.read()['remaining_ms'], 3600000)

    def test_paid_suspended_and_expired_accounts_have_no_trial_counter(self):
        for state in ('Active', 'Suspended', 'Payment required'):
            self.state.return_value = {'state': state}
            self.assertEqual(self.read(), {'active': False})
        self.state.return_value = {'state': 'Trial'}
        self.now += timedelta(days=15)
        self.assertEqual(self.read(), {'active': False, 'remaining_ms': 0})

    def test_other_roles_do_not_read_a_teacher_account(self):
        for role in ('Student', 'Admin'):
            self.member.role = role
            self.assertEqual(self.read(), {'active': False})
        self.lookup.assert_not_called()
