import ast
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import Mock, patch
from contextlib import nullcontext

from institute_lms.student_renewal_rules import paid_through, reminder_due
from institute_lms.commercial_rules import access_window

NOW = datetime(2026, 11, 16, 12)


class PeriodRules(unittest.TestCase):
    def test_remaining_days_and_prepaid_adjacent_month_are_preserved(self):
        end = NOW + timedelta(days=3)
        periods = [(NOW-timedelta(days=27),end),(end,end+timedelta(days=30))]
        self.assertEqual(paid_through(periods,NOW),end+timedelta(days=30))

    def test_expired_period_does_not_shorten_new_month(self):
        self.assertEqual(paid_through([(NOW-timedelta(days=31),NOW-timedelta(days=1))],NOW),NOW)

    def test_future_gap_does_not_grant_unpaid_days(self):
        self.assertEqual(paid_through([(NOW+timedelta(days=2),NOW+timedelta(days=32))],NOW),NOW)

    def test_reminder_window(self):
        for seconds,expected in [(-1,False),(0,False),(1,True),(259200,True),(259201,False)]:
            with self.subTest(seconds=seconds):
                self.assertEqual(reminder_due(NOW+timedelta(seconds=seconds),NOW),expected)


class R(dict):
    def __getattr__(self,k):return self.get(k)


class Grants(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/'institute_lms/commercial.py').read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='grant')
        self.invoice=R(name='invoice',status='Paid',enrollment='enroll',student='student',amount=5)
        self.enrollment=R(student='student',classroom='class',institute='institute')
        self.room=R(name='class',institute='institute',billing_type='Monthly',access_duration_days=30)
        self.coverage=Mock(return_value=NOW+timedelta(days=3))
        self.saved=Mock(side_effect=lambda row:row)
        self.db=N(get_value=Mock(return_value=None))
        def deny(message,*args):raise PermissionError(message)
        self.env={'frappe':N(db=self.db,get_doc=lambda *a:R(a[0]) if isinstance(a[0],dict) else R(name=a[1]),throw=deny,PermissionError=PermissionError),
            'account_for':lambda room:R(name='account'),'locked':lambda *a:self.enrollment,
            'get_datetime':lambda t:t,'now_datetime':lambda:NOW,
            'configured_access':lambda room,start:(start,start+timedelta(days=room.access_duration_days)),
            'access_window':access_window,'save':self.saved,'money_minor':lambda n:int(n*100),'__name__':'institute_lms.commercial'}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'commercial.py','exec'),self.env)
        self.module=patch.dict(sys.modules,{'institute_lms.student_renewals':N(coverage_end=self.coverage)})
        self.module.start();self.addCleanup(self.module.stop)

    def grant(self,channel='Bank transfer'):
        return self.env['grant'](self.invoice,self.room,NOW,NOW+timedelta(days=30),channel)

    def test_early_bank_renewal_retains_three_days(self):
        result=self.grant();self.assertEqual(result.ends_at,NOW+timedelta(days=33))
        self.assertEqual(result.starts_at,NOW+timedelta(days=3))

    def test_card_uses_same_renewal_rule(self):
        self.assertEqual(self.grant('Card').ends_at,NOW+timedelta(days=33))

    def test_calendar_month_uses_old_expiry_as_anchor(self):
        self.room['access_duration_days']=None;self.room['paid_access_kind']='Month'
        self.coverage.return_value=datetime(2027,1,31,12)
        self.assertEqual(self.grant().ends_at,datetime(2027,2,28,12))

    def test_replayed_payment_does_not_extend_twice(self):
        self.db.get_value.return_value='existing'
        self.assertEqual(self.grant().name,'existing');self.saved.assert_not_called()

    def test_unpaid_cannot_get_access(self):
        self.invoice['status']='Unpaid'
        with self.assertRaises(PermissionError):self.grant()
        self.saved.assert_not_called()

    def test_other_students_enrollment_is_rejected(self):
        self.enrollment['student']='other'
        with self.assertRaises(PermissionError):self.grant()

    def test_programme_installments_do_not_add_months(self):
        self.enrollment['programme_enrollment']='programme'
        self.assertEqual(self.grant().ends_at,NOW+timedelta(days=30));self.coverage.assert_not_called()

    def test_one_time_access_unchanged(self):
        self.room['billing_type']='One-time'
        self.assertEqual(self.grant().ends_at,NOW+timedelta(days=30));self.coverage.assert_not_called()


class ReminderDelivery(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).parents[1]/'institute_lms/student_renewals.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='deliver_sms')
        self.row=R(channel='SMS',status='Queued',event='event',recipient='student',institute='institute',attempts=0,body='Renew class',event_key='unique')
        self.row.save=Mock()
        self.event=R(event_type='class.renewal',classroom='class',institute='institute',user='student@example.com',recipient='student',event_key='expected')
        self.room=R(name='class',institute='institute')
        self.member=R(name='student',institute='institute',user='student@example.com')
        self.state=Mock(return_value=NOW+timedelta(days=3));self.sms=Mock(return_value={'provider_id':'accepted'})
        self.db=N(get_value=Mock(return_value='+94704276212'),commit=Mock())
        docs={'IL Notification':self.row,'IL Notification Event':self.event,'IL Classroom':self.room,'IL Member':self.member}
        env={'__name__':'institute_lms.student_renewals','frappe':N(db=self.db,get_doc=lambda dt,*a,**kw:docs[dt],cache=N(lock=lambda *a,**kw:nullcontext()),conf={'il_sms_adapter':'configured'}),
             'EVENT':'class.renewal','reminder_state':self.state,'now_datetime':lambda:NOW,'reminder_key':lambda *a:'key'}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'student_renewals.py','exec'),env)
        self.deliver=env['deliver_sms']
        patcher=patch.dict(sys.modules,{'institute_lms.saas_rules':N(notification_key=lambda *a:'expected'),'institute_lms.providers':N(sms=self.sms)})
        patcher.start();self.addCleanup(patcher.stop)

    def test_accepted_sms_is_not_sent_again(self):
        self.deliver('n');self.deliver('n')
        self.sms.assert_called_once();self.assertEqual(self.row.status,'Accepted');self.assertEqual(self.row.attempts,1)

    def test_renewed_student_does_not_receive_stale_reminder(self):
        self.state.return_value=None;self.deliver('n')
        self.sms.assert_not_called();self.assertEqual(self.row.status,'Skipped')

    def test_foreign_recipient_is_not_sent_sms(self):
        self.event['user']='other@example.com';self.deliver('n')
        self.sms.assert_not_called();self.assertEqual(self.row.status,'Skipped')

    def test_unverified_number_is_not_sent_sms(self):
        self.db.get_value.return_value=None;self.deliver('n');self.sms.assert_not_called()

    def test_uncertain_delivery_is_not_automatically_retried(self):
        self.sms.side_effect=TimeoutError();self.deliver('n');self.deliver('n')
        self.sms.assert_called_once();self.assertEqual(self.row.status,'Review')
