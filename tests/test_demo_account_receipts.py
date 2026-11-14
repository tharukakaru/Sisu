import unittest
from types import SimpleNamespace
from test_upload_provisioning import function


class DemoReceiptDelivery(unittest.TestCase):
    def test_only_explicit_local_demo_accounts_suppress_external_delivery(self):
        conf={'host_name':'http://127.0.0.1:5400','il_local_student_signup_enabled':1}
        f=SimpleNamespace(conf=conf)
        local_demo=function('account_confirmations','local_demo',{'frappe':f})
        self.assertTrue(local_demo('learner@demo.sisu.test'))
        self.assertFalse(local_demo('learner@gmail.com'))
        conf['host_name']='https://www.sisuacademylk.com'
        self.assertFalse(local_demo('learner@demo.sisu.test'))
        conf['host_name']='http://127.0.0.1:5400'
        conf['il_local_student_signup_enabled']=0
        self.assertFalse(local_demo('learner@demo.sisu.test'))
        conf['il_local_student_signup_enabled']=1
        conf['il_control_plane']=1
        self.assertFalse(local_demo('learner@demo.sisu.test'))

    def test_demo_receipt_is_saved_in_app_without_enqueuing_delivery(self):
        saved=[]
        f=SimpleNamespace(local=SimpleNamespace(site='sisuacademylk.com'),db=SimpleNamespace(exists=lambda *a:False),
            get_doc=lambda data:SimpleNamespace(insert=lambda **kw:saved.append(data)),
            enqueue=lambda *a,**kw:self.fail('Demo receipt must not enqueue external delivery'))
        queue=function('account_confirmations','queue',{'frappe':f,'hashlib':__import__('hashlib'),'escape':__import__('html').escape,'local_demo':lambda user:True})
        queue('learner@demo.sisu.test','demo-key','Enrollment key','Demo key kept in app')
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]['for_user'],'learner@demo.sisu.test')

    def test_previously_queued_local_demo_receipt_does_not_deliver(self):
        f=SimpleNamespace(local=SimpleNamespace(site='sisuacademylk.com'),
            get_doc=lambda *a:SimpleNamespace(for_user='learner@demo.sisu.test'))
        deliver=function('account_confirmations','deliver',{'frappe':f,'local_demo':lambda user:True})
        # There is deliberately no database or delivery API: neither may be reached.
        self.assertIsNone(deliver('demo-notice'))
