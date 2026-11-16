import importlib
import sys
import types
import unittest
from datetime import datetime,date,timedelta
from unittest.mock import MagicMock

class ContactBoundaries(unittest.TestCase):
    def setUp(self):
        self.names=('frappe','frappe.utils','institute_lms.api','institute_lms.wallet','institute_lms.registration','institute_lms.contact','institute_lms.profiles','institute_lms.onboarding','institute_lms.private_contact','institute_lms.invitations','institute_lms.notifications','institute_lms.teacher_identity','institute_lms.invitation_notifications','institute_lms.campus_teachers')
        self.old={k:sys.modules.get(k) for k in self.names}
        self.f=types.ModuleType('frappe');self.f.conf={};self.f.whitelist=lambda **kw:lambda fn:fn;self.f.PermissionError=PermissionError
        def throw(msg,kind=ValueError):raise kind(msg)
        self.f.throw=throw;self.f.session=types.SimpleNamespace(user='teacher@example.invalid');self.f.db=MagicMock();self.f.get_doc=MagicMock();self.f.get_all=MagicMock()
        u=types.ModuleType('frappe.utils');u.now_datetime=lambda:datetime(2026,9,28);u.get_datetime=lambda d:d if isinstance(d,datetime) else datetime.fromisoformat(d);u.getdate=lambda:date(2026,9,28);u.get_url=lambda path='':'https://example.invalid'+path
        a=types.ModuleType('institute_lms.api');a.identity=lambda:(types.SimpleNamespace(name='I'),types.SimpleNamespace(role='Teacher',user=self.f.session.user));a.require_role=lambda m,*roles:None if m.role in roles else throw('Denied',PermissionError)
        w=types.ModuleType('institute_lms.wallet');w.signed_in=MagicMock()
        r=types.ModuleType('institute_lms.registration');r.limit=MagicMock()
        c=types.ModuleType('institute_lms.contact');c.email_address=lambda s:s
        p=types.ModuleType('institute_lms.profiles');p.required=lambda:types.SimpleNamespace(kind='Teacher');p.mine=lambda:types.SimpleNamespace(kind='Teacher',status='Verified');p.relate=MagicMock();p.write=MagicMock()
        o=types.ModuleType('institute_lms.onboarding');o.account_kind=lambda:'Student'
        sys.modules.update({'frappe':self.f,'frappe.utils':u,'institute_lms.api':a,'institute_lms.wallet':w,'institute_lms.registration':r,'institute_lms.contact':c,'institute_lms.profiles':p,'institute_lms.onboarding':o})
        for k in ('institute_lms.private_contact','institute_lms.invitations','institute_lms.notifications'):sys.modules.pop(k,None)
        campus=types.ModuleType('institute_lms.campus_teachers');campus.sync=MagicMock();sys.modules['institute_lms.campus_teachers']=campus
        identity=types.ModuleType('institute_lms.teacher_identity');identity.eligible=MagicMock(return_value=False);sys.modules['institute_lms.teacher_identity']=identity
        notices=types.ModuleType('institute_lms.invitation_notifications');notices.queue_response=MagicMock();sys.modules['institute_lms.invitation_notifications']=notices;self.notices=notices
        self.contact=importlib.import_module('institute_lms.private_contact');self.invites=importlib.import_module('institute_lms.invitations');self.profiles=p
    def tearDown(self):
        for k,v in self.old.items():
            if v is None:sys.modules.pop(k,None)
            else:sys.modules[k]=v
    def test_contact_read_is_always_current_user(self):
        self.f.db.get_value.return_value=None
        result=self.contact.get_details()
        self.f.db.get_value.assert_any_call('IL Private Contact',{'user':'teacher@example.invalid'},'name')
        self.assertEqual(result['login_email'],'teacher@example.invalid')
    def test_invitation_https_override_works_for_http_local_site_and_email_link(self):
        self.invites.get_url=lambda:'http://127.0.0.1:5400'
        self.f.conf['il_teacher_invitation_origin']='https://checkout.localhost:5440/'
        self.f.db.exists.return_value=True
        self.f.sendmail=MagicMock(return_value=True);self.f.enqueue=MagicMock()
        self.invites.require_mail()
        self.invites.send_notice('teacher@example.invalid','Invitation','Join',invitation='INV')
        self.assertIn('href="https://checkout.localhost:5440/campus#invitations"',self.f.sendmail.call_args.kwargs['message'])
        self.f.enqueue.assert_called_once()
    def test_invitation_rejects_insecure_and_malformed_origins(self):
        for origin in ['http://localhost:5400','https://user:secret@example.test','https://example.test/path','https://example.test?q=x','https://example.test#x','https://example.test:bad','https://bad host']:
            with self.subTest(origin=origin):
                self.f.conf['il_teacher_invitation_origin']=origin
                with self.assertRaisesRegex(ValueError,'HTTPS'):self.invites.require_mail()
    def test_invitation_requires_outgoing_email(self):
        self.f.db.exists.return_value=False
        with self.assertRaisesRegex(ValueError,'outgoing Email Account'):self.invites.require_mail()
    def test_invitation_defaults_to_configured_https_site(self):
        self.assertEqual(self.invites.invitation_origin(),'https://example.invalid')
    def test_unverified_phone_cannot_enable_notifications(self):
        self.f.db.exists.return_value=False
        with self.assertRaisesRegex(ValueError,'Verify'):
            self.contact.save_details({'date_of_birth':'2000-01-01','whatsapp_phone':'+94770000000','whatsapp_opt_in':True,'notification_language':'en'})
        self.f.get_doc.assert_not_called()
    def test_stolen_or_expired_invitation_does_not_create_membership(self):
        for email,expires in [('other@example.invalid',datetime(2026,10,1)),('teacher@example.invalid',datetime(2026,9,27))]:
            self.f.get_doc.return_value=types.SimpleNamespace(invite_email=email,status='Pending',expires_at=expires)
            with self.assertRaises((ValueError,PermissionError)):self.invites.respond('invite','Accepted')
        self.profiles.relate.assert_not_called()
    def test_guardian_contact_saves_without_verified_phone(self):
        self.f.db.exists.return_value=False
        self.f.db.get_value.return_value=None
        data={'date_of_birth':'2015-01-01','guardian_name':'Parent','guardian_relationship':'Mother','guardian_phone':'+12025550123','guardian_permission':True,'whatsapp_phone':'+12025550123','whatsapp_opt_in':True,'notification_language':'en'}
        self.assertTrue(self.contact.save_details(data)['saved'])
        self.f.get_doc.return_value.save.assert_called_once_with(ignore_permissions=True)
        self.f.db.exists.assert_not_called()
    def test_dispatch_accepts_guardian_consent_but_not_mismatch_or_adult(self):
        notifications=importlib.import_module('institute_lms.notifications')
        self.f.db.exists.return_value=False
        self.f.db.get_value.return_value='private-contact'
        member=types.SimpleNamespace(active=1,whatsapp_opt_in=1,phone='+12025550123',role='Student',user='student@example.invalid')
        data={'date_of_birth':'2015-01-01','guardian_name':'Parent','guardian_relationship':'Mother','guardian_phone':member.phone,'guardian_permission':True,'notification_language':'en'}
        self.f.get_doc.return_value.as_dict.side_effect=lambda:dict(data)
        self.assertTrue(notifications.whatsapp_allowed(member))
        data['guardian_permission']=False
        self.assertFalse(notifications.whatsapp_allowed(member))
        data['guardian_permission']=True;data['guardian_phone']='+12025550124'
        self.assertFalse(notifications.whatsapp_allowed(member))
        data['date_of_birth']='2000-01-01'
        self.assertFalse(notifications.whatsapp_allowed(member))
    def test_invitation_acceptance_connects_once_and_queues_response(self):
        doc=types.SimpleNamespace(invite_email='teacher@example.invalid',status='Pending',expires_at=datetime(2026,10,1),profile='P',flags=types.SimpleNamespace(),save=MagicMock())
        self.f.get_doc.return_value=doc
        self.invites.connect_teacher=MagicMock()
        self.invites.respond('invite','Accepted')
        self.invites.respond('invite','Accepted')
        self.invites.connect_teacher.assert_called_once_with(doc,'teacher@example.invalid')
        self.notices.queue_response.assert_called_once()
        self.assertEqual(doc.status,'Accepted')

    def test_reject_never_connects_and_cannot_be_changed_to_accept(self):
        doc=types.SimpleNamespace(invite_email='teacher@example.invalid',status='Pending',expires_at=datetime(2026,10,1),profile='P',flags=types.SimpleNamespace(),save=MagicMock())
        self.f.get_doc.return_value=doc;self.invites.connect_teacher=MagicMock()
        self.invites.respond('invite','Declined')
        self.invites.respond('invite','Declined')
        with self.assertRaisesRegex(ValueError,'no longer pending'):self.invites.respond('invite','Accepted')
        self.invites.connect_teacher.assert_not_called()
        self.notices.queue_response.assert_called_once()

    def test_unverified_teacher_cannot_accept(self):
        self.profiles.mine=lambda:types.SimpleNamespace(kind='Teacher',status='Pending')
        with self.assertRaises(PermissionError):self.invites.respond('invite','Accepted')
        self.notices.queue_response.assert_not_called()

    def test_changed_institute_or_revoked_inviter_cannot_connect(self):
        invitation=types.SimpleNamespace(profile='P',institute='I',invited_by='admin')
        self.f.get_doc.return_value=types.SimpleNamespace(kind='Institute',status='Verified',workspace='OTHER')
        with self.assertRaisesRegex(ValueError,'no longer available'):self.invites.connect_teacher(invitation,'teacher')
