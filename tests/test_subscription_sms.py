import importlib.util
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import MagicMock, patch
import sys


class Row(dict):
    __getattr__=dict.get
    def __setattr__(self,key,value): self[key]=value
    def save(self,**kwargs):return self


class SubscriptionSMS(TestCase):
    def setUp(self):
        self.notices={}
        self.bill=Row(name='invoice',status='Paid',currency='LKR',amount_minor=500,plan='Individual',
                      period_end='2026-12-15 10:00:00',receipt_number='receipt',payment_channel='CyberSource live')
        self.account=Row(user='teacher@example.test',display_name='Teacher')
        self.f=SimpleNamespace(conf={'il_subscription_sms_enabled':True,'il_subscription_admin_sms_phone':'+94704276212'})
        self.f.db=SimpleNamespace(exists=lambda dt,f: f['notice_key'] in self.notices,
            get_value=self.value,commit=MagicMock())
        self.f.enqueue=MagicMock()
        self.f.cache=SimpleNamespace(lock=lambda *a,**k:nullcontext())
        self.f.get_doc=self.doc
        spec=importlib.util.spec_from_file_location('institute_lms.subscription_sms_test',Path(__file__).parents[1]/'institute_lms/subscription_sms.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.module)

    def value(self,dt,*args,**kwargs):
        return {'IL Public Profile':{'username':'teacher','display_name':'Demo Teacher','lms_id':'SISU-TC-000013'},
                'IL Verified Phone':'+94704276212','IL Account Invoice':self.bill.status}.get(dt)

    def doc(self,dt,name=None,**kwargs):
        if isinstance(dt,str):return self.notices[name]
        row=Row(dt);row.name=row.notice_key
        def insert(**kwargs):self.notices[row.name]=row;return row
        row.insert=insert
        return row

    def test_two_role_messages_are_queued_once_only_after_payment(self):
        self.bill.status='Draft';self.module.queue_paid(self.bill,self.account)
        self.assertFalse(self.notices)
        self.bill.status='Paid'
        self.module.queue_paid(self.bill,self.account);self.module.queue_paid(self.bill,self.account)
        self.assertEqual(len(self.notices),2);self.assertEqual(self.f.enqueue.call_count,2)
        admin=next(x for x in self.notices.values() if x.recipient=='admin')
        self.assertIn('SISU-TC-000013',admin.body);self.assertIn('@teacher',admin.body)
        self.assertIn('LKR 5.00',admin.body);self.assertIn('Individual',admin.body)

    def test_ambiguous_send_is_not_retried_and_payment_is_preserved(self):
        self.module.queue_paid(self.bill,self.account)
        notice=next(iter(self.notices));send=MagicMock(side_effect=TimeoutError())
        with patch.dict(sys.modules,{'institute_lms.providers':SimpleNamespace(sms=send)}):
            self.module.deliver(notice);self.module.deliver(notice)
        self.assertEqual(send.call_count,1);self.assertEqual(self.notices[notice].status,'Review')
        self.assertEqual(self.bill.status,'Paid')

    def test_accepted_send_does_not_repeat(self):
        self.module.queue_paid(self.bill,self.account);notice=next(iter(self.notices))
        send=MagicMock(return_value={'accepted':True})
        with patch.dict(sys.modules,{'institute_lms.providers':SimpleNamespace(sms=send)}):
            self.module.deliver(notice);self.module.deliver(notice)
        self.assertEqual(send.call_count,1);self.assertEqual(self.notices[notice].status,'Accepted')

    def test_sandbox_payment_never_sends_live_confirmation(self):
        self.bill.payment_channel='CyberSource sandbox';self.module.queue_paid(self.bill,self.account)
        self.assertFalse(self.notices)

    def test_institute_uses_active_billing_admin_for_confirmation(self):
        self.account.update(role='Institute',user=None,institute='academy',
                            billing_email='billing@example.test',display_name='Local QA Academy')
        self.f.get_all=MagicMock(return_value=['owner@example.test','billing@example.test'])
        self.module.queue_paid(self.bill,self.account)
        self.assertEqual(len(self.notices),2)
        self.assertTrue(all(n.user=='billing@example.test' for n in self.notices.values()))
        admin=next(n for n in self.notices.values() if n.recipient=='admin')
        self.assertIn('Local QA Academy',admin.body)
        self.f.get_all.assert_called_once_with('IL Member',filters={
            'institute':'academy','role':'Admin','active':1},pluck='user',order_by='creation asc, name asc')
        customer=next(n for n in self.notices.values() if n.recipient=='teacher')
        send=MagicMock(return_value={'accepted':True})
        with patch.dict(sys.modules,{'institute_lms.providers':SimpleNamespace(sms=send)}):
            self.module.deliver(customer.name);self.module.deliver(customer.name)
        self.assertEqual(send.call_count,1)
        self.assertEqual(customer.status,'Accepted')

    def test_institute_does_not_use_unrelated_billing_email_as_user(self):
        self.account.update(role='Institute',user=None,institute='academy',
                            billing_email='external@example.test')
        self.f.get_all=MagicMock(return_value=['owner@example.test'])
        self.assertEqual(self.module.customer_user(self.account),'owner@example.test')
        self.f.get_all.return_value=[]
        self.module.queue_paid(self.bill,self.account)
        self.assertFalse(self.notices)
