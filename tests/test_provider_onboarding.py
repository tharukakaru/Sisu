import importlib
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from institute_lms.onboarding_navigation import workspace_registration


class RegistrationBoundary(unittest.TestCase):
    def row(self, **changes):
        details = dict(flow='public-account-v1', email='a@test.invalid', kind='Individual Teacher',
            teaching_path='individual', onboarding_version=2, onboarding_profile_completed=True)
        details.update(changes)
        return {'details': json.dumps(details)}

    def test_own_completed_provider_only(self):
        self.assertTrue(workspace_registration([self.row()], 'a@test.invalid', 'Teacher'))
        self.assertTrue(workspace_registration([self.row(kind='Institute')], 'a@test.invalid', 'Institute'))
        for changes in ({'email':'other@test.invalid'}, {'teaching_path':'institute'},
                        {'onboarding_profile_completed':False}, {'flow':'unknown'}, {'kind':'Student'}):
            self.assertFalse(workspace_registration([self.row(**changes)], 'a@test.invalid', 'Teacher'))
        for rows in ([], [{'details':'bad'}], [{'details':'[]'}]):
            self.assertFalse(workspace_registration(rows, 'a@test.invalid', 'Institute'))


class ProvisionBoundary(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.PermissionError = PermissionError
        def throw(message, kind=ValueError): raise kind(message)
        self.f.throw = throw
        self.f.db = MagicMock()
        self.f.session = types.SimpleNamespace(user='a@test.invalid', data={})
        self.f.local = types.SimpleNamespace(session_obj=MagicMock())
        self.profile = types.SimpleNamespace(kind='Teacher', status='Pending', workspace='own', display_name='A')
        self.member = types.SimpleNamespace(name='member', role='Teacher', active=1)
        self.phone = types.SimpleNamespace(phone='+94700000000', verified_at='2026-11-15')
        self.f.db.get_value.side_effect = lambda dt,*a,**kw: {'IL Public Profile':'profile','IL Member':self.member,'IL Verified Phone':self.phone}[dt]
        self.f.get_doc = MagicMock(side_effect=lambda dt,name: self.profile if dt=='IL Public Profile' else types.SimpleNamespace(name='own'))
        self.f.get_all = MagicMock(return_value=[RegistrationBoundary().row()])
        campus = types.ModuleType('institute_lms.campus_context')
        campus.require_user = lambda: 'a@test.invalid'
        campus.SESSION_KEY = 'selected'
        self.patch = patch.dict(sys.modules, {'frappe':self.f,'institute_lms.campus_context':campus})
        self.patch.start()
        sys.modules.pop('institute_lms.provider_onboarding',None)
        self.mod = importlib.import_module('institute_lms.provider_onboarding')

    def tearDown(self):
        sys.modules.pop('institute_lms.provider_onboarding',None)
        self.patch.stop()

    def test_existing_owned_membership_is_reused_without_mutation(self):
        self.assertEqual(self.mod.continue_to_workspace(), {'ready':True})
        self.assertEqual(self.f.session.data, {'selected':'own'})
        self.f.db.set_value.assert_not_called()

    def test_new_workspace_is_locked_and_retry_does_not_restart_trial(self):
        from contextlib import nullcontext
        self.profile.workspace = None
        self.f.db.exists.return_value = False
        institute = types.SimpleNamespace(name='new', code='PTEST', insert=MagicMock())
        member = types.SimpleNamespace(name='new-member', role='Teacher', active=1, insert=MagicMock())
        self.f.get_doc.side_effect = lambda *a,**kw: (institute if a[0]['doctype']=='IL Institute' else member) if isinstance(a[0],dict) else (self.profile if a[0]=='IL Public Profile' else institute)
        billing=types.ModuleType('institute_lms.account_billing')
        subscription=types.SimpleNamespace(onboarding_payment_required=0, trial_started='original')
        billing.account=MagicMock(return_value=subscription);billing.save=MagicMock()
        profiles=types.ModuleType('institute_lms.profiles');profiles.write=MagicMock()
        provisioning=types.ModuleType('institute_lms.campus_provisioning');provisioning.institute_insert=lambda doc:nullcontext()
        memberships=types.ModuleType('institute_lms.membership_write');memberships.authorized_insert=lambda doc:nullcontext()
        with patch.dict(sys.modules, {'institute_lms.account_billing':billing,'institute_lms.profiles':profiles,
                'institute_lms.campus_provisioning':provisioning,'institute_lms.membership_write':memberships}):
            self.mod.continue_to_workspace()
            self.assertEqual(subscription.onboarding_payment_required,1)
            self.assertEqual(subscription.trial_started,'original')
            self.assertEqual(self.profile.status,'Pending')
            self.mod.continue_to_workspace()
            institute.insert.assert_called_once()
            member.insert.assert_called_once()
            billing.save.assert_called_once()

    def test_revoked_or_wrong_role_is_not_restored(self):
        for role, active in [('Teacher',0),('Student',1),('Admin',1)]:
            self.member.role=role;self.member.active=active
            with self.assertRaises(PermissionError): self.mod.continue_to_workspace()
        self.assertEqual(self.f.session.data,{})

    def test_institute_teacher_cannot_self_provision(self):
        self.f.get_all.return_value=[RegistrationBoundary().row(teaching_path='institute')]
        with self.assertRaises(PermissionError): self.mod.continue_to_workspace()
        self.assertEqual(self.f.session.data,{})

    def test_incomplete_profile_phone_or_rejected_identity_denied(self):
        self.phone.verified_at=None
        with self.assertRaises(PermissionError): self.mod.continue_to_workspace()
        self.phone.verified_at='2026-11-15';self.profile.status='Rejected'
        with self.assertRaises(PermissionError): self.mod.continue_to_workspace()
        self.assertEqual(self.f.session.data,{})

if __name__=='__main__': unittest.main()
