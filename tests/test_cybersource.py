import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from institute_lms.cybersource_contract import (session_request, request_jwt, verify_session,
    verify_transaction, b64url, unb64, minor, HOST)

REFERENCE = 'sisu-' + 'a' * 32


def transaction():
    return {'id': '12345678901234567890', 'merchantId': 'sandbox_merchant',
        'clientReferenceInformation': {'code': REFERENCE},
        'orderInformation': {'amountDetails': {'totalAmount': '100.00', 'currency': 'LKR'}},
        'applicationInformation': {'applications': [
            {'name': 'ics_auth', 'reasonCode': 100}, {'name': 'ics_bill', 'reasonCode': 100}]}}


class Contract(unittest.TestCase):
    def setUp(self):
        self.binding = dict(merchant_id='sandbox_merchant', reference=REFERENCE, amount_minor=10000, currency='LKR')

    def test_customer_payment_no_token_storage_or_recurring(self):
        r = session_request(REFERENCE, 10000, 'LKR', 'https://sandbox.example.test',
                            ['PANENTRY', 'GOOGLEPAY', 'APPLEPAY', 'CLICKTOPAY'])
        self.assertEqual(r['completeMandate']['type'], 'CAPTURE')
        self.assertEqual(r['completeMandate']['consumerAuthentication'], '3DS')
        self.assertFalse(r['completeMandate']['tms']['tokenCreate'])
        self.assertFalse(r['captureMandate']['requestSaveCredentials'])
        self.assertEqual(r['data']['clientReferenceInformation']['code'], REFERENCE)
        # The provider styles its own isolated card fields from this session.
        self.assertEqual(r['appearance']['variables']['buttonBackground'], '#572B91')
        self.assertEqual(r['appearance']['variables']['inputFocusedBorderColor'], '#572B91')
        self.assertEqual(r['appearance']['theme'], 'LIGHT')

    def test_origins_and_methods_fail_closed(self):
        for url in ('http://localhost:8000', 'https://user@site.test', 'https://site.test/path'):
            with self.assertRaises(ValueError): session_request(REFERENCE, 10, 'LKR', url, ['PANENTRY'])
        with self.assertRaises(ValueError):session_request(REFERENCE, 10, 'LKR', 'https://site.test', ['UNKNOWN'])

    def test_no_rounding_or_nonfinite_amount(self):
        for value in ('1.001', '-1', 'NaN', 'Infinity', '0', None):
            with self.assertRaises(ValueError):minor(value)

    def test_verified_auth_and_capture(self):
        self.assertEqual(verify_transaction(transaction(), self.binding), 'succeeded')

    def test_authorization_alone_does_not_grant(self):
        t = transaction();t['applicationInformation']['applications'].pop()
        self.assertEqual(verify_transaction(t, self.binding), 'pending')

    def test_capture_failure_does_not_grant(self):
        t = transaction();t['applicationInformation']['applications'][1]['reasonCode'] = 102
        self.assertEqual(verify_transaction(t, self.binding), 'pending')

    def test_bindings_cannot_be_replayed(self):
        for key, value in [('merchant_id', 'other'), ('reference', 'other'), ('amount_minor', 999), ('currency', 'USD')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_transaction(transaction(), dict(self.binding, **{key: value}))

    def test_decline_and_reversal(self):
        t = transaction();t['applicationInformation']['applications'] = [{'name':'ics_auth','reasonCode':203}]
        self.assertEqual(verify_transaction(t, self.binding), 'failed')
        t = transaction();t['applicationInformation']['applications'].append({'name':'ics_auth_reversal','reasonCode':100})
        self.assertEqual(verify_transaction(t, self.binding), 'review')

    def test_signed_request_exact_body_host_path_expiry(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        body = b'{"amount":"1.00"}'
        token = request_jwt('POST', '/uc/v1/sessions', body, 'merchant', 'key', key, now=100)
        h,p,s=token.split('.')
        key.public_key().verify(unb64(s),(h+'.'+p).encode(),padding.PKCS1v15(),hashes.SHA256())
        claims=json.loads(unb64(p));self.assertEqual(claims['request-host'],HOST)
        self.assertEqual(claims['exp'],220);self.assertEqual(claims['request-resource-path'],'/uc/v1/sessions')
        import base64,hashlib
        self.assertEqual(claims['digest'],base64.b64encode(hashlib.sha256(body).digest()).decode())
        token=request_jwt('GET','/tss/v2/transactions/1234567890',b'','merchant','key',key,now=100)
        self.assertNotIn('digest',json.loads(unb64(token.split('.')[1])))

    def test_session_signature_and_expiry(self):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        n=key.public_key().public_numbers()
        jwk={'kty':'RSA','kid':'key','e':b64url(n.e.to_bytes(3,'big')),'n':b64url(n.n.to_bytes(256,'big'))}
        h=b64url(json.dumps({'alg':'RS256','kid':'key'}).encode())
        p=b64url(json.dumps({'iat':100,'exp':200}).encode())
        text=h+'.'+p;token=text+'.'+b64url(key.sign(text.encode(),padding.PKCS1v15(),hashes.SHA256()))
        self.assertEqual(verify_session(token,lambda _:jwk,now=150)['exp'],200)
        with self.assertRaises(ValueError):verify_session(token,lambda _:jwk,now=201)
        with self.assertRaises(InvalidSignature):verify_session(h+'.'+b64url(b'{"exp":9999}')+'.'+token.split('.')[2],lambda _:jwk,now=150)


class Row(dict):
    __getattr__=dict.get
    def get_password(self, field):return self[field]
    def __setattr__(self,k,v):self[k]=v


class Service(unittest.TestCase):
    def setUp(self):
        f=types.ModuleType('frappe');u=types.ModuleType('frappe.utils')
        f.whitelist=lambda **kw:lambda fn:fn
        f.throw=lambda msg,*a:(_ for _ in ()).throw(ValueError(msg))
        f.PermissionError=PermissionError;f.ValidationError=ValueError
        f.conf={};f.session=Row(user='student@test')
        f.db=MagicMock();f.db.get_value.return_value=None
        u.now_datetime=lambda:datetime(2026,10,30,10)
        u.get_datetime=lambda x:x;u.get_url=lambda:'https://sandbox.example.test'
        spec=importlib.util.spec_from_file_location('institute_lms._cybs_test',Path(__file__).parents[1]/'institute_lms/cybersource.py')
        self.m=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':f,'frappe.utils':u}):spec.loader.exec_module(self.m)
        self.f=f
        self.a=Row(name='attempt',reference=REFERENCE,kind='tuition',invoice='invoice',
            merchant_scope='tuition:provider',merchant_id='sandbox_merchant',amount_minor=10000,
            currency='LKR',status='pending',customer='student@test',active_key='tuition:invoice')
        f.get_doc=lambda *a,**kw:self.a
        self.m.save=lambda doc:doc
        self.m.accessible=lambda name:self.a
        self.m.settings=lambda scope, **kwargs:dict(merchant_id='sandbox_merchant', mode='sandbox')
        self.m.source=lambda *a,**kw:(Row(status='Unpaid'),Row(name='inst'),'scope',10000,'LKR')
        self.m.settle=MagicMock()

    def test_transport_only_treats_explicit_session_validation_as_rejected(self):
        from institute_lms.cybersource_transport import request, SessionRejected, ProviderUnavailable
        config=dict(mode='live',merchant_id='test',key_id='test',shared_secret='YWJj')
        with patch('institute_lms.cybersource_transport.requests.Session') as factory, \
                patch('institute_lms.cybersource_http_signature.headers', return_value={}):
            response=factory.return_value.__enter__.return_value.request.return_value
            response.status_code=400;response.content=b'{}'
            response.json.return_value={'code':'UNIFIEDPAYMENTS_VALIDATION_FIELDS'}
            with self.assertRaises(SessionRejected):
                request(config,'POST','/uc/v1/sessions',{},token=True)
            response.status_code=503
            with self.assertRaises(ProviderUnavailable) as caught:
                request(config,'POST','/uc/v1/sessions',{},token=True)
            self.assertNotIsInstance(caught.exception,SessionRejected)
            response.status_code=400
            with self.assertRaises(ProviderUnavailable) as caught:
                request(config,'POST','/tss/v2/searches',{})
            self.assertNotIsInstance(caught.exception,SessionRejected)

    def test_public_key_cache_is_bounded_by_time_environment_and_key_id(self):
        from institute_lms import cybersource_transport as transport
        transport._public_keys.clear()
        key={'kty':'RSA','n':'abc','e':'AQAB'}
        try:
            with patch.object(transport.requests,'Session') as factory, patch.object(transport.time,'monotonic',return_value=100) as clock:
                response=factory.return_value.__enter__.return_value.get.return_value
                response.status_code=200;response.content=b'{}';response.json.return_value=key
                first=transport.public_key('key1',host='api.cybersource.com')
                first['n']='changed'
                self.assertEqual(transport.public_key('key1',host='api.cybersource.com')['n'],'abc')
                self.assertEqual(factory.call_count,1)
                transport.public_key('key1',host='apitest.cybersource.com')
                transport.public_key('key2',host='api.cybersource.com')
                self.assertEqual(factory.call_count,3)
                transport.public_key('key1',host='api.cybersource.com',refresh=True)
                self.assertEqual(factory.call_count,4)
                clock.return_value=701
                transport.public_key('key1',host='api.cybersource.com')
                self.assertEqual(factory.call_count,5)
                response.json.return_value={'kty':'RSA','kid':'wrong','n':'abc','e':'AQAB'}
                with self.assertRaises(ValueError):transport.public_key('key3',host='api.cybersource.com')
                self.assertNotIn(('api.cybersource.com','key3'),transport._public_keys)
        finally:
            transport._public_keys.clear()

    def test_key_rotation_refreshes_signature_check_without_another_session(self):
        from institute_lms import cybersource_transport as transport
        config=dict(mode='live',merchant_id='test',key_id='test',shared_secret='YWJj')
        with patch.object(transport.requests,'Session') as factory, \
                patch('institute_lms.cybersource_http_signature.headers',return_value={}), \
                patch.object(transport,'public_key',return_value={}) as key, \
                patch.object(transport,'verify_session') as verify:
            response=factory.return_value.__enter__.return_value.request.return_value
            response.status_code=200;response.content=b'mock';response.text='mock-session'
            def check(token,fetch):
                fetch('rotating-key')
                if verify.call_count==1:raise InvalidSignature()
                return {'exp':123}
            verify.side_effect=check
            self.assertEqual(transport.request(config,'POST','/uc/v1/sessions',{},token=True),('mock-session',{'exp':123}))
            key.assert_called_with('rotating-key',host='api.cybersource.com',refresh=True)
            self.assertEqual(factory.return_value.__enter__.return_value.request.call_count,1)
            verify.side_effect=InvalidSignature()
            with self.assertRaises(transport.ProviderUnavailable):
                transport.request(config,'POST','/uc/v1/sessions',{},token=True)

    def test_browser_cannot_settle_or_clear_attempt(self):
        self.m.browser_event('attempt','completed')
        self.assertEqual(self.a.status,'pending');self.assertEqual(self.a.active_key,'tuition:invoice')
        self.m.settle.assert_not_called()
        self.m.browser_event('attempt','cancelled');self.assertEqual(self.a.status,'pending')

    def test_expired_empty_report_releases_retry_without_granting_access(self):
        self.a.session_expires=self.m.time.time()-301
        self.m.request=MagicMock(return_value={'totalCount':0})
        audit=types.ModuleType('institute_lms.saas');audit.audit=MagicMock()
        with patch.dict(sys.modules,{'institute_lms.saas':audit}):
            result=self.m.reconcile('attempt')
        self.assertTrue(result['retry_allowed'])
        self.assertEqual(result['status'],'cancelled')
        self.assertIsNone(self.a.active_key)
        self.m.settle.assert_not_called();audit.audit.assert_called_once()

    def test_close_hint_cannot_release_live_or_uncertain_context(self):
        self.m.request=MagicMock(return_value={'totalCount':0})
        for fields in [dict(session_expires=self.m.time.time()+60),
                       dict(session_expires=self.m.time.time()-299),
                       dict(session_expires=None),
                       dict(session_expires=self.m.time.time()-301,browser_event='completed'),
                       dict(session_expires=self.m.time.time()-301,browser_event='processing'),
                       dict(session_expires=self.m.time.time()-301,transaction_id='123'),
                       dict(session_expires=self.m.time.time()-7*86400)]:
            self.a.update(session_expires=None,browser_event='cancelled',transaction_id=None,last_checked=None)
            self.a.update(fields)
            result=self.m.reconcile('attempt')
            self.assertFalse(result['retry_allowed'])
            self.assertEqual(self.a.active_key,'tuition:invoice')
        self.m.settle.assert_not_called()

    def test_late_close_cannot_erase_submission_evidence(self):
        self.a.update(session_token='signed',session_expires=self.m.time.time()+900)
        grant=self.m.checkout_access(self.a,'sandbox')['submission_grant']
        self.m.browser_event('attempt','processing',grant)
        self.m.browser_event('attempt','cancelled')
        self.assertEqual(self.a.browser_event,'processing')
        self.m.browser_event('attempt','completed')
        self.m.browser_event('attempt','failed')
        self.assertEqual(self.a.browser_event,'completed')

    def test_empty_report_must_be_explicit_and_consistent(self):
        self.a.session_expires=self.m.time.time()-301
        for report in [{},{'totalCount':'0'},{'totalCount':False},{'totalCount':0,'_embedded':None},
                       {'totalCount':0,'_embedded':{'transactionSummaries':[{'id':'123'}]}},
                       {'totalCount':1}]:
            self.assertFalse(self.m.release_expired_empty(self.a,report))
            self.assertEqual(self.a.active_key,'tuition:invoice')

    def test_expired_checkout_provider_failure_does_not_allow_retry(self):
        self.a.session_expires=self.m.time.time()-301
        self.m.request=MagicMock(side_effect=self.m.ProviderUnavailable())
        self.assertFalse(self.m.reconcile('attempt')['retry_allowed'])
        self.assertEqual(self.a.active_key,'tuition:invoice')

    def test_server_report_settles_once(self):
        self.m.request=MagicMock(side_effect=[{'_embedded':{'transactionSummaries':[{'id':transaction()['id']}]}},transaction()])
        self.assertEqual(self.m.reconcile('attempt')['status'],'succeeded')
        self.assertEqual(self.m.reconcile('attempt')['status'],'succeeded')
        self.m.settle.assert_called_once();self.assertIsNone(self.a.active_key)

    def test_3ds_setup_challenge_and_one_capture_settle_once(self):
        paid=transaction()
        setup={'id':'11111111111111111111','merchantId':paid['merchantId'],
               'clientReferenceInformation':paid['clientReferenceInformation'],
               'applicationInformation':{'applications':[{'name':'ics_pa_setup','reasonCode':'100'}]}}
        challenge=dict(setup,id='22222222222222222222',applicationInformation={'reasonCode':475,'applications':[
            {'name':'ics_auth'},{'name':'ics_bill'},{'name':'ics_arc'},
            {'name':'ics_pa_enroll','reasonCode':'475'},{'name':'ics_decision_early'}]})
        report={'totalCount':3,'_embedded':{'transactionSummaries':[{'id':d['id']} for d in [paid,challenge,setup]]}}
        self.m.request=MagicMock(side_effect=[report,paid,challenge,setup])
        self.assertEqual(self.m.reconcile('attempt')['status'],'succeeded')
        self.assertEqual(self.a.transaction_id,paid['id'])
        self.assertEqual(self.m.reconcile('attempt')['status'],'succeeded')
        self.m.settle.assert_called_once()

    def test_multiple_real_payments_never_auto_allocate(self):
        first=transaction();second=dict(first,id='22222222222222222222')
        self.m.request=MagicMock(side_effect=[{'totalCount':2,'_embedded':{'transactionSummaries':[{'id':first['id']},{'id':second['id']}]}},first,second])
        self.assertEqual(self.m.reconcile('attempt')['status'],'pending');self.m.settle.assert_not_called()

    def test_truncated_report_never_auto_allocates(self):
        self.m.request=MagicMock(return_value={'totalCount':11,'_embedded':{'transactionSummaries':[{'id':transaction()['id']}]}})
        self.assertEqual(self.m.reconcile('attempt')['status'],'pending');self.m.settle.assert_not_called()
        self.assertEqual(self.m.request.call_count,1)

    def test_authentication_record_with_financial_result_is_not_ignored(self):
        row={'applicationInformation':{'reasonCode':475,'applications':[{'name':'ics_pa_enroll','reasonCode':'475'},{'name':'ics_auth','reasonCode':'100'}]}}
        self.assertFalse(self.m.authentication_only(row))

    def test_mismatch_never_settles(self):
        t=transaction();t['merchantId']='other'
        self.m.request=MagicMock(side_effect=[{'_embedded':{'transactionSummaries':[{'id':t['id']}]}},t])
        self.assertEqual(self.m.reconcile('attempt')['status'],'pending');self.m.settle.assert_not_called()

    def test_duplicate_transactions_require_review(self):
        self.m.request=MagicMock(return_value={'_embedded':{'transactionSummaries':[{'id':'1'},{'id':'2'}]}})
        self.assertEqual(self.m.reconcile('attempt')['status'],'pending');self.m.settle.assert_not_called()

    def test_poll_cooldown(self):
        self.a.last_checked=datetime(2026,10,30,9,59)
        self.m.request=MagicMock();self.m.reconcile('attempt');self.m.request.assert_not_called()

    def test_invoice_changed_keeps_verified_money_for_review(self):
        self.m.source=lambda *a,**kw:(Row(status='Paid'),None,'scope',10000,'LKR')
        self.m.request=MagicMock(side_effect=[{'_embedded':{'transactionSummaries':[{'id':transaction()['id']}]}},transaction()])
        self.assertEqual(self.m.reconcile('attempt')['status'],'review');self.m.settle.assert_not_called()

    def test_live_config_rejected(self):
        self.f.conf={'il_cybersource':{'enabled':True,'mode':'live'}}
        # Access the real implementation, not the test's settings stub.
        spec=importlib.util.spec_from_file_location('institute_lms._cybs_test2',Path(__file__).parents[1]/'institute_lms/cybersource.py')
        m=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':types.SimpleNamespace(now_datetime=datetime.now,get_datetime=lambda x:x,get_url=lambda:'https://site.test')}):spec.loader.exec_module(m)
        with self.assertRaises(ValueError):m.settings('platform')

    def test_local_card_configuration_checks_site_allowlist_and_browser_origin(self):
        self.f.conf = {'il_local_card_test': True,
                       'il_cybersource_test_users': ['teacher@test'],
                       'il_cybersource': {'enabled': True, 'mode': 'live',
                           'live_checkout_approved': True, 'origin': 'https://checkout.localhost:5440',
                           'merchants': {'platform': {'merchant_id': 'test', 'key_id': 'test',
                               'shared_secret': 'test', 'methods': ['PANENTRY']}}}}
        self.f.local = Row(request=Row(host_url='https://checkout.localhost:5440/'))
        spec = importlib.util.spec_from_file_location('institute_lms._cybs_local',
                    Path(__file__).parents[1] / 'institute_lms/cybersource.py')
        m = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils': types.SimpleNamespace(
                now_datetime=datetime.now, get_datetime=lambda x:x, get_url=lambda:'http://127.0.0.1:5400')}):
            spec.loader.exec_module(m)
        self.assertEqual(m.settings('platform')['origin'], 'https://checkout.localhost:5440')
        self.f.local.request = None
        self.assertEqual(m.settings('platform', for_reconciliation=True)['origin'], 'https://checkout.localhost:5440')
        with self.assertRaises(ValueError): m.settings('platform')
        self.f.local.request = Row(host_url='https://checkout.localhost:5440/')
        self.f.conf['il_cybersource_test_users'] = []
        with self.assertRaises(ValueError): m.settings('platform')
        self.f.conf['il_cybersource_test_users'] = ['teacher@test']
        m.get_url = lambda:'https://production.example'
        with self.assertRaises(ValueError): m.settings('platform')
        api = types.ModuleType('institute_lms.api')
        api.identity = lambda:(Row(name='inst'), Row(role='Teacher'))
        api.scoped = MagicMock()
        billing = types.ModuleType('institute_lms.account_billing')
        billing.account = lambda **kw:Row(name='sub', role='Teacher', institute='inst', enabled=1)
        invoice = Row(subscription='sub', status='Unpaid', period_end=datetime(2099,1,1),
                      amount_minor=500, currency='LKR')
        self.f.get_doc = lambda *a,**kw:invoice
        self.f.session.user = 'teacher@test'
        with patch.dict(sys.modules, {'institute_lms.api':api, 'institute_lms.account_billing':billing}):
            self.assertEqual(m.source('subscription', 'invoice')[3:], (500, 'LKR'))
            invoice.amount_minor = 501
            with self.assertRaises(ValueError): m.source('subscription', 'invoice')
            invoice.amount_minor = 500
            invoice.currency = 'USD'
            with self.assertRaises(ValueError): m.source('subscription', 'invoice')
            invoice.currency = 'LKR'
            self.f.session.user = 'someone-else@test'
            with self.assertRaises(ValueError): m.source('subscription', 'invoice')

    def test_other_student_and_foreign_tenant_are_denied(self):
        api=types.ModuleType('institute_lms.api')
        api.identity=lambda:(Row(name='inst'),Row(role='Student',name='member'))
        api.scoped=lambda *a:Row(student='another-member')
        # Restore the actual source function, which is stubbed in reconciliation tests.
        spec=importlib.util.spec_from_file_location('institute_lms._cybs_access',Path(__file__).parents[1]/'institute_lms/cybersource.py')
        m=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':types.SimpleNamespace(now_datetime=datetime.now,get_datetime=lambda x:x,get_url=lambda:'https://site.test'),'institute_lms.api':api}):
            spec.loader.exec_module(m)
            with self.assertRaises(ValueError):m.source('tuition','foreign')
            self.f.session.user='Guest'
            with self.assertRaises(ValueError):m.source('tuition','foreign')

    def test_network_uncertainty_keeps_invoice_unpaid(self):
        self.m.request=MagicMock(side_effect=self.m.ProviderUnavailable())
        self.assertEqual(self.m.reconcile('attempt')['status'],'pending')
        self.m.settle.assert_not_called()
        self.assertEqual(self.a.active_key,'tuition:invoice')

    def test_declined_report_releases_retry_without_access(self):
        t=transaction();t['applicationInformation']['applications']=[{'name':'ics_auth','reasonCode':203}]
        self.m.request=MagicMock(side_effect=[{'_embedded':{'transactionSummaries':[{'id':t['id']}]}},t])
        self.assertEqual(self.m.reconcile('attempt')['status'],'failed')
        self.assertIsNone(self.a.active_key);self.m.settle.assert_not_called()

    def test_business_validation_failure_retains_verified_transaction(self):
        self.m.request=MagicMock(side_effect=[{'_embedded':{'transactionSummaries':[{'id':transaction()['id']}]}},transaction()])
        self.m.settle.side_effect=ValueError('Invoice expired')
        self.assertEqual(self.m.reconcile('attempt')['status'],'review')
        self.f.db.rollback.assert_called_once_with(save_point='cybs_allocation')
        self.assertTrue(self.a.settlement_key)

    def test_transaction_lookup_identity_mismatch(self):
        t=transaction();t['id']='99999999999999999'
        self.m.request=MagicMock(side_effect=[{'_embedded':{'transactionSummaries':[{'id':transaction()['id']}]}},t])
        self.assertEqual(self.m.reconcile('attempt')['status'],'pending');self.m.settle.assert_not_called()

    def test_resume_reuses_context_rotates_and_consumes_submission_grant(self):
        reg=types.ModuleType('institute_lms.registration');reg.limit=MagicMock()
        self.a.update(session_token='same-signed-session',session_expires=self.m.time.time()+900)
        self.f.db.get_value.return_value='attempt';self.m.request=MagicMock()
        with patch.dict(sys.modules,{'institute_lms.registration':reg}):
            first=self.m.start('tuition','invoice')
            second=self.m.start('tuition','invoice')
        self.assertEqual(first['session'],second['session'])
        self.assertNotEqual(first['submission_grant'],second['submission_grant'])
        self.assertTrue(second['resume_allowed']);self.assertNotIn('retry_after',second)
        self.m.request.assert_not_called();reg.limit.assert_not_called()
        with self.assertRaises(ValueError):self.m.browser_event('attempt','processing',first['submission_grant'])
        self.assertIsNone(self.a.browser_event)
        self.m.browser_event('attempt','processing',second['submission_grant'])
        self.assertEqual(self.a.browser_event,'processing')
        with self.assertRaises(ValueError):self.m.browser_event('attempt','processing',second['submission_grant'])
        self.assertFalse(self.m.public(self.a)['resume_allowed'])
        self.m.settle.assert_not_called()

    def test_submitted_or_uncertain_attempt_cannot_resume(self):
        for fields in [dict(browser_event='processing'),dict(browser_event='completed'),
                       dict(transaction_id='123'),dict(settlement_key='paid'),dict(status='review'),dict(status='creating')]:
            self.a.update(status='pending',transaction_id=None,settlement_key=None,browser_event=None,
                          session_token='signed',session_expires=self.m.time.time()+900)
            self.a.update(fields)
            with self.assertRaises(ValueError):self.m.checkout_access(self.a,'sandbox')

    def test_guarded_unsubmitted_expired_session_releases_without_wait(self):
        self.a.update(session_token='expired',session_expires=self.m.time.time()-1,
                      evidence=json.dumps({'guarded_checkout':True,'environment':'sandbox'}))
        self.f.db.get_value.return_value='attempt';self.m.request=MagicMock()
        result=self.m.start('tuition','invoice')
        self.assertTrue(result['retry_allowed']);self.assertEqual(self.a.status,'cancelled')
        self.assertIsNone(self.a.active_key);self.m.request.assert_not_called()
        self.m.settle.assert_not_called()

    def test_duplicate_start_never_returns_a_second_context(self):
        reg=types.ModuleType('institute_lms.registration');reg.limit=MagicMock()
        self.f.db.get_value.return_value='attempt'
        self.m.request=MagicMock()
        with patch.dict(sys.modules,{'institute_lms.registration':reg}):
            r=self.m.start('tuition','invoice')
        self.assertNotIn('session',r);self.m.request.assert_not_called()
        reg.limit.assert_not_called()

    def test_start_snapshots_server_price_before_external_call(self):
        reg=types.ModuleType('institute_lms.registration');reg.limit=lambda *a:None
        events=[]
        self.f.db.commit=lambda:events.append('commit')
        self.f.get_doc=lambda doc,*a,**kw:Row(doc,name='new') if isinstance(doc,dict) else self.a
        self.m.source=lambda *a,**kw:(Row(status='Unpaid'),Row(name='inst'),'platform',10000,'LKR')
        self.m.settings=lambda scope:dict(merchant_id='sandbox_merchant',mode='sandbox',origin='https://sandbox.example.test',methods=['PANENTRY'])
        def provider(c,method,path,body,token=False):
            self.assertEqual(events,['commit'])
            self.assertEqual(body['data']['orderInformation']['amountDetails']['totalAmount'],'100.00')
            self.assertEqual(path,'/uc/v1/sessions')
            return 'signed-session',{'exp':9999999999}
        self.m.request=provider
        with patch.dict(sys.modules,{'institute_lms.registration':reg}):
            r=self.m.start('tuition','invoice')
        self.assertEqual(r['session'],'signed-session');self.m.settle.assert_not_called()

    def test_session_connection_failure_is_retryable_without_payment_review(self):
        reg=types.ModuleType('institute_lms.registration');reg.limit=MagicMock()
        self.f.get_doc=lambda doc,*a,**kw:Row(doc,name='new') if isinstance(doc,dict) else self.a
        self.m.settings=lambda scope:dict(merchant_id='sandbox_merchant',mode='sandbox',origin='https://sandbox.example.test',methods=['PANENTRY'])
        self.m.request=MagicMock(side_effect=self.m.ProviderUnavailable(reason_code='ReadTimeout'))
        with patch.dict(sys.modules,{'institute_lms.registration':reg}):
            result=self.m.start('tuition','invoice')
        self.assertEqual(result['status'],'failed');self.assertTrue(result['session_unavailable'])
        self.assertNotIn('session',result);self.m.settle.assert_not_called()
        reg.limit.assert_called_once()

    def test_legacy_review_without_delivered_session_can_recover(self):
        self.a.update(status='review',session_token=None,session_expires=0,browser_event=None)
        self.f.db.get_value.return_value='attempt';self.m.request=MagicMock()
        result=self.m.start('tuition','invoice')
        self.assertTrue(result['retry_allowed']);self.assertEqual(self.a.status,'cancelled')
        self.m.request.assert_not_called();self.m.settle.assert_not_called()

    def test_legacy_recovery_never_releases_delivered_or_inflight_attempts(self):
        for fields in [dict(status='creating'),dict(session_token='signed'),dict(session_expires=1),
                       dict(browser_event='processing'),dict(transaction_id='123'),dict(settlement_key='settled')]:
            self.a.update(status='review',session_token=None,session_expires=0,browser_event=None,
                          transaction_id=None,settlement_key=None)
            self.a.update(fields)
            self.assertFalse(self.m.undelivered_session(self.a))

    def test_definitive_session_validation_failure_does_not_lock_invoice(self):
        reg=types.ModuleType('institute_lms.registration');reg.limit=lambda *a:None
        self.f.get_doc=lambda doc,*a,**kw:Row(doc,name='new') if isinstance(doc,dict) else self.a
        self.m.settings=lambda scope:dict(merchant_id='sandbox_merchant',mode='sandbox',origin='https://sandbox.example.test',methods=['PANENTRY'])
        self.m.request=MagicMock(side_effect=self.m.SessionRejected())
        with patch.dict(sys.modules,{'institute_lms.registration':reg}):
            result=self.m.start('tuition','invoice')
        self.assertEqual(result['status'],'failed')
        self.assertNotIn('session',result)
        self.m.settle.assert_not_called()

    def test_pending_subscription_attempt_blocks_replacement_invoice_checkout(self):
        reg=types.ModuleType('institute_lms.registration');reg.limit=lambda *a:None
        self.f.db.exists.return_value=True
        self.m.settings=lambda scope:dict(merchant_id='sandbox_merchant',mode='sandbox',origin='https://sandbox.example.test',methods=['PANENTRY'])
        self.m.request=MagicMock()
        with patch.dict(sys.modules,{'institute_lms.registration':reg}):
            with self.assertRaisesRegex(ValueError,'earlier subscription checkout'):
                self.m.start('subscription','replacement-invoice')
        self.m.request.assert_not_called()

    def test_disabled_provider_does_not_block_existing_bank_flow(self):
        self.f.conf={};self.m.assert_no_active('tuition','invoice')
        self.f.db.exists.assert_not_called()

    def test_active_attempt_blocks_alternative_settlement(self):
        self.f.conf={'il_cybersource':{'enabled':True}}
        self.f.db.exists.return_value=True
        with self.assertRaises(ValueError):self.m.assert_no_active('tuition','invoice')
