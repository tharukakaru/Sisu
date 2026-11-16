from types import SimpleNamespace as NS
from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch
from test_upload_provisioning import function


class InvitationSMS(TestCase):
    def setUp(self):
        self.row=NS(channel='SMS',status='Queued',event='event',recipient='admin',institute='I',attempts=0,
                    body='Teacher accepted',event_key='unique',save=MagicMock())
        self.member=NS(user='admin@test.invalid',active=1,role='Admin',institute='I')
        self.f=NS(cache=MagicMock(),db=MagicMock(),conf={'il_sms_adapter':'configured'},get_doc=MagicMock())
        self.f.get_doc.side_effect=lambda dt,*a,**kw:self.row if dt=='IL Notification' else self.member
        self.f.db.get_value.side_effect=lambda dt,*a,**kw:'teacher.invitation.responded' if dt=='IL Notification Event' else '+94704276212'
        self.sms=MagicMock(return_value={'provider_id':'accepted'})
        self.provider=patch.dict('sys.modules',{'institute_lms.providers':NS(sms=self.sms)})
        self.provider.start();self.addCleanup(self.provider.stop)
        self.deliver=function('invitation_notifications','deliver_sms',{'frappe':self.f,'EVENT':'teacher.invitation.responded','now_datetime':datetime.now})

    def test_success_is_not_sent_again(self):
        self.deliver('notice');self.deliver('notice')
        self.assertEqual(self.row.status,'Accepted')
        self.sms.assert_called_once_with('+94704276212','Teacher accepted','unique')

    def test_uncertain_send_stays_in_review_without_retry(self):
        self.sms.side_effect=TimeoutError('connection lost')
        self.deliver('notice');self.deliver('notice')
        self.assertEqual(self.row.status,'Review')
        self.sms.assert_called_once()

    def test_removed_or_foreign_admin_is_not_contacted(self):
        for attribute,value in [('active',0),('role','Teacher'),('institute','OTHER')]:
            with self.subTest(attribute=attribute):
                self.member=NS(user='admin',active=1,role='Admin',institute='I')
                setattr(self.member,attribute,value);self.row.status='Queued'
                self.deliver('notice')
                self.assertEqual(self.row.status,'Skipped')
        self.sms.assert_not_called()
