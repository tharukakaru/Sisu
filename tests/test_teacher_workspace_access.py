from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch
from test_upload_provisioning import function


class WorkspaceAccess(TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 12)
        self.member = NS(name='teacher-member', user='teacher@test.invalid', role='Teacher')
        self.inst = NS(name='selected')
        self.personal = NS(plan='Individual', trial_until=self.now + timedelta(days=14))
        self.institute = NS(plan='Gold')
        self.provider = None
        self.f = NS(db=Mock(), get_doc=Mock(return_value=self.institute),
                    session=NS(user=self.member.user), local=NS(request=NS(path='/api/method/test')),
                    PermissionError=PermissionError)
        self.f.throw = lambda msg, exc: (_ for _ in ()).throw(exc(msg))
        self.f.db.get_value.side_effect = lambda dt, *a, **kw: self.provider if dt == 'IL Public Profile' else self.member if dt == 'IL Member' else 'subscription'
        self.account = Mock(return_value=self.personal)
        self.state = Mock(return_value={'state':'Trial', 'available':True})
        self.sponsor = Mock(return_value=None)
        self.patch = patch.dict('sys.modules', {
            'institute_lms.account_billing': NS(account=self.account, state=self.state),
            'institute_lms.institute_coverage': NS(sponsor=self.sponsor),
            'institute_lms.campus_context': NS(selected_institute=lambda:'selected'),
            'frappe.utils': NS(get_datetime=lambda value:value, now_datetime=lambda:self.now),
        })
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.context = function('teacher_workspace','billing_context',{'frappe':self.f})
        self.guard_context = {'kind':'Personal','available':False,'message':'Trial ended'}
        self.guard = function('teacher_workspace','enforce_request',{'frappe':self.f,
            'enabled':lambda:True,'billing_context':lambda *a:self.guard_context,
            'RECOVERY_METHODS':{'institute_lms.campus_context.select','institute_lms.teacher_workspace.summary'}})

    def test_personal_trial_retains_original_deadline(self):
        result = self.context(self.inst,self.member)
        self.assertEqual(result['remaining_ms'],14*86400000)
        self.assertEqual(result['kind'],'Personal')
        self.account.assert_called_once_with(self.inst,self.member)
        self.f.db.set_value.assert_not_called()

    def test_institute_cannot_borrow_personal_trial(self):
        self.provider=NS(display_name='Test Institute')
        result=self.context(self.inst,self.member)
        self.assertFalse(result['available'])
        self.assertEqual(result['plan'],'Gold')
        self.account.assert_not_called()

    def test_paid_institute_works_without_personal_plan(self):
        self.provider=NS(display_name='Test Institute')
        self.sponsor.return_value={'account':self.institute}
        self.state.return_value={'state':'Active','available':True}
        self.assertTrue(self.context(self.inst,self.member)['available'])
        self.account.assert_not_called()

    def test_expired_personal_blocks_teaching_even_direct_api(self):
        for method in ('institute_lms.api.classrooms','institute_lms.profiles.mine','frappe.client.get_list',''):
            with self.subTest(method=method), self.assertRaises(PermissionError):self.guard(method)

    def test_expired_personal_can_renew_switch_and_sign_out(self):
        for method in ('institute_lms.account_billing.status','institute_lms.account_billing.invoice',
                       'institute_lms.cybersource.start','institute_lms.campus_context.select',
                       'institute_lms.teacher_workspace.summary'):
            self.assertTrue(self.guard(method))

    def test_clearing_workspace_selection_cannot_bypass_expired_trial(self):
        self.provider='personal'
        with patch.dict('sys.modules',{'institute_lms.campus_context':NS(selected_institute=lambda:None)}):
            with self.assertRaises(PermissionError):self.guard('institute_lms.profiles.save_profile')
            self.assertTrue(self.guard('institute_lms.campus_context.select'))

    def test_institute_teacher_cannot_buy_personal_plan_in_wrong_context(self):
        self.guard_context={'kind':'Institute','available':True,'message':''}
        self.assertTrue(self.guard('institute_lms.api.classrooms'))
        with self.assertRaises(PermissionError):self.guard('institute_lms.account_billing.invoice')

    def test_usage_invoice_recovery_reaches_its_own_ownership_checks_after_expiry(self):
        self.f.conf={}
        self.f.form_dict={}
        guard=function('saas','guard_request',{'frappe':self.f})
        for method in ('status','document','request_activation'):
            self.f.form_dict['cmd']='institute_lms.usage_billing.'+method
            guard()

    def test_pending_or_unverified_institute_cannot_be_selected(self):
        selected=Mock()
        self.f.conf={'il_unified_teacher_signup':1,'il_public_signup_enabled':1,'il_shared_campus_enabled':1}
        self.member.institute='selected'
        choose=function('campus_context','select',{'frappe':self.f,'membership':lambda value:self.member,'_set_selection':selected})
        self.provider=NS(name='profile',status='Verified')
        self.f.db.exists.return_value=False
        with self.assertRaises(PermissionError):choose('selected')
        selected.assert_not_called()
        self.f.db.exists.return_value=True
        self.provider.status='Pending'
        with self.assertRaises(PermissionError):choose('selected')
        self.provider.status='Verified'
        self.assertEqual(choose('selected')['selected'],'selected')


class CancelInstituteRequest(TestCase):
    def setUp(self):
        self.doc=NS(user='teacher',kind='Teacher membership',status='Pending')
        self.saved=Mock()
        self.f=NS(db=Mock(),get_doc=Mock(return_value=self.doc),PermissionError=PermissionError)
        self.f.db.exists.return_value=True
        self.f.throw=lambda message,error=ValueError: (_ for _ in ()).throw(error(message))
        self.cancel=function('teacher_workspace','cancel_request',{'frappe':self.f,'enabled':lambda:True})
        modules=patch.dict('sys.modules',{'institute_lms.campus_context':NS(require_user=lambda:'teacher'),
            'institute_lms.profiles':NS(write=self.saved)})
        modules.start();self.addCleanup(modules.stop)

    def test_own_pending_application_is_withdrawn_without_deleting_history(self):
        self.assertEqual(self.cancel('request'),{'status':'Cancelled'})
        self.assertEqual(self.doc.status,'Left')
        self.assertEqual(self.doc.reviewed_by,'teacher')
        self.saved.assert_called_once_with(self.doc)
        self.f.db.sql.assert_called_once_with('SELECT name FROM `tabIL Profile Relationship` WHERE name=%s FOR UPDATE',('request',))
        self.f.db.delete.assert_not_called()

    def test_another_users_request_cannot_be_cancelled(self):
        self.f.db.exists.return_value=False
        with self.assertRaises(PermissionError):self.cancel('foreign')
        self.saved.assert_not_called()

    def test_concurrent_approval_is_not_revoked(self):
        self.doc.status='Active'
        with self.assertRaises(ValueError):self.cancel('request')
        self.assertEqual(self.doc.status,'Active')
        self.saved.assert_not_called()

    def test_duplicate_cancellation_is_idempotent(self):
        self.doc.status='Left'
        self.assertEqual(self.cancel('request'),{'status':'Cancelled'})
        self.saved.assert_not_called()
