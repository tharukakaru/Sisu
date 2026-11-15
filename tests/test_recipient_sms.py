"""Recipient policy and enrollment notice regressions; no external SMS calls."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).resolve().parents[1]/'institute_lms'

def function(file,name,env):
    node=next(n for n in ast.parse((ROOT/file).read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name==name)
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),file,'exec'),env)
    return env[name]

class Notifications(TestCase):
    def test_background_policy_uses_recipient_not_admin_session(self):
        member=NS(institute='I',user='student');inst=NS(name='I')
        policy=MagicMock(return_value={'available':True,'features':{'integrations.sms':True}})
        f=NS(session=NS(user='Administrator'),get_doc=MagicMock(return_value=inst))
        fn=function('notification_service.py','recipient_channel_allowed',{'frappe':f,'__package__':'institute_lms'})
        with patch.dict('sys.modules',{'institute_lms.account_billing':NS(policy=policy)}):
            self.assertTrue(fn(member,'SMS'))
            policy.assert_called_once_with(inst,member)
            policy.return_value['available']=False
            self.assertFalse(fn(member,'SMS'))
            policy.return_value={'available':True,'features':{}}
            self.assertFalse(fn(member,'SMS'))
        self.assertEqual(f.session.user,'Administrator')

    def test_join_notifies_once_and_does_not_claim_payment(self):
        class Row(dict):
            __getattr__=dict.get
        member=Row(name='S',full_name='Demo Student')
        room=Row(name='C',active=True,published=True,public_provider='P',fee_mode='Paid',fee=1500,title='English')
        db=MagicMock();db.get_value.return_value=None
        create=MagicMock(return_value='E');notify=MagicMock()
        fn=function('catalog.py','join_class',{'__package__':'institute_lms','frappe':NS(db=db),
            'identity':lambda:(Row(name='I'),member),'require_role':lambda *a:None,'scoped':lambda *a:room,
            'provider':lambda *a:None,'today':lambda:'2026-11-15'})
        with patch.dict('sys.modules',{'institute_lms.api':NS(create_enrollment=create),'institute_lms.commercial':NS(notify_people=notify)}):
            self.assertFalse(fn('C')['existing'])
            self.assertEqual(notify.call_args.args[1],'enrollment.requested')
            self.assertIn('Payment is pending',notify.call_args.args[3])
            db.get_value.return_value=Row(name='E',active=True)
            self.assertTrue(fn('C')['existing'])
            create.assert_called_once();notify.assert_called_once()
