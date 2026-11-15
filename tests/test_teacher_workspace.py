import hashlib
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch
from contextlib import nullcontext
from test_upload_provisioning import function


class TeacherWorkspaceTests(TestCase):
    def setUp(self):
        self.user = 'teacher@example.invalid'
        self.profile = NS(user=self.user, kind='Teacher', status='Pending', workspace=None,
                          display_name='Test Teacher')
        self.member = Mock(name='member'); self.member.role='Teacher'; self.member.active=1
        self.inst = Mock(); self.inst.name='personal'
        self.f = NS(session=NS(user=self.user), db=Mock(), get_all=Mock(return_value=[]),
                    get_doc=Mock(), PermissionError=PermissionError)
        self.f.throw=lambda message,error: (_ for _ in ()).throw(error(message))
        self.f.db.exists.return_value=False
        self.f.db.get_value.side_effect=lambda dt,*a,**kw: self.member if dt=='IL Member' else 'profile' if dt=='IL Public Profile' else '+94700000000'
        self.created=[]
        def doc(value,*args):
            if isinstance(value,str):return self.profile
            self.created.append(value)
            return self.inst if value['doctype']=='IL Institute' else self.member
        self.f.get_doc.side_effect=doc
        self.allowed=Mock(return_value=True);self.verified=Mock(return_value=True)
        self.ensure=function('teacher_workspace','ensure',{'frappe':self.f,'hashlib':hashlib,
            'enabled':self.allowed,'eligible':self.verified})
        self.save=Mock();self.billing=Mock()
        self.modules=patch.dict('sys.modules',{
            'institute_lms.campus_provisioning':NS(institute_insert=lambda doc:nullcontext()),
            'institute_lms.membership_write':NS(authorized_insert=lambda doc:nullcontext()),
            'institute_lms.profiles':NS(write=self.save),
            'institute_lms.account_billing':NS(account=self.billing)})
        self.modules.start();self.addCleanup(self.modules.stop)

    def test_verified_identity_gets_personal_teacher_not_admin_or_badge(self):
        self.assertEqual(self.ensure(self.user),'personal')
        self.assertEqual(self.created[1]['role'],'Teacher')
        self.assertEqual(self.created[1]['user'],self.user)
        self.assertEqual(self.profile.status,'Pending')
        self.assertEqual(self.profile.workspace,'personal')
        self.assertRegex(self.created[0]['code'],r'^[A-Z][A-Z0-9]{1,11}$')
        self.billing.assert_called_once_with(self.inst,self.member,create=True)
        self.f.db.commit.assert_not_called()

    def test_repeated_open_does_not_create_membership_or_restart_trial(self):
        self.profile.workspace='personal'
        self.f.get_all.return_value=[NS(user=self.user,role='Teacher')]
        self.assertEqual(self.ensure(self.user),'personal')
        self.assertEqual(self.created,[])
        self.billing.assert_not_called()

    def test_disabled_feature_grants_nothing(self):
        self.allowed.return_value=False
        with self.assertRaises(PermissionError):self.ensure(self.user)
        self.f.get_doc.assert_not_called()

    def test_cannot_provision_another_user(self):
        with self.assertRaises(PermissionError):self.ensure('other@example.invalid')
        self.f.get_doc.assert_not_called()

    def test_unverified_identity_grants_nothing(self):
        self.verified.return_value=False
        with self.assertRaises(PermissionError):self.ensure(self.user)
        self.f.get_doc.assert_not_called()

    def test_rejected_profile_cannot_open(self):
        self.profile.status='Rejected'
        with self.assertRaises(PermissionError):self.ensure(self.user)
        self.assertEqual(self.created,[])

    def test_revoked_membership_cannot_be_reactivated(self):
        self.profile.workspace='personal';self.member.active=0
        with self.assertRaises(PermissionError):self.ensure(self.user)
        self.member.save.assert_not_called()

    def test_institute_or_another_teachers_workspace_is_never_adopted(self):
        self.profile.workspace='foreign';self.f.db.exists.return_value=True
        with self.assertRaises(PermissionError):self.ensure(self.user)
        self.f.db.exists.return_value=False
        self.f.get_all.return_value=[NS(user='someone-else',role='Teacher')]
        with self.assertRaises(PermissionError):self.ensure(self.user)
        self.billing.assert_not_called()

    def test_code_collision_requires_review_instead_of_reusing_workspace(self):
        self.f.db.exists.return_value=True
        with self.assertRaises(PermissionError):self.ensure(self.user)
        self.assertEqual(self.created,[])
