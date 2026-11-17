import importlib.util,sys,types,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import MagicMock,patch
ROOT=Path(__file__).parents[1]/'institute_lms'
class Denied(Exception):pass
class Security(unittest.TestCase):
 def setUp(self):
  self.f=types.ModuleType('frappe');self.f.conf={};self.f.cache=MagicMock();self.f.cache.make_key=lambda k:k;self.f.cache.eval.return_value=[1,60]
  self.f.local=types.SimpleNamespace(response={},request_ip='127.0.0.1',request=types.SimpleNamespace(path='/api/method/institute_lms.cybersource.start',method='POST'))
  self.f.session=types.SimpleNamespace(user='teacher');self.f.form_dict={};self.f.TooManyRequestsError=Denied
  def throw(message,*args):raise Denied(message)
  self.f.throw=throw
  def load(name):
   spec=importlib.util.spec_from_file_location('_security_'+name,ROOT/(name+'.py'));m=importlib.util.module_from_spec(spec)
   with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(m)
   return m
  self.c=load('checkout_captcha');self.r=load('request_security')
  self.config={'enabled':True,'site_key':'public-key','secret_key':'private-key','hostnames':['checkout.localhost']}
  self.f.conf['il_checkout_recaptcha']=self.config
 def response(self,**kw):
  value={'success':True,'hostname':'checkout.localhost','challenge_ts':datetime.now(timezone.utc).isoformat()};value.update(kw)
  response=MagicMock();response.json.return_value=value;return response
 def test_public_settings_never_expose_secret(self):
  self.assertNotIn('private-key',str(self.c.public_settings()))
 def test_missing_configuration_and_missing_token_fail_closed(self):
  with self.assertRaises(Denied):self.c.verify(None)
  self.config.pop('secret_key')
  with self.assertRaises(Denied):self.c.verify('x'*40)
 def test_valid_verification_uses_fixed_https_and_timeout(self):
  with patch.object(self.c.requests,'post',return_value=self.response()) as post:
   self.c.verify('x'*40);self.assertEqual(post.call_args.args[0],'https://www.google.com/recaptcha/api/siteverify');self.assertFalse(post.call_args.kwargs['allow_redirects']);self.assertEqual(post.call_args.kwargs['timeout'],(3,6))
 def test_wrong_host_expired_replay_and_malformed_denied(self):
  for changes in [{'hostname':'evil.example'},{'success':False},{'success':'true'},{'challenge_ts':(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat()},{'challenge_ts':'invalid'},{'challenge_ts':datetime.now().isoformat()}]:
   with patch.object(self.c.requests,'post',return_value=self.response(**changes)):
    with self.assertRaises(Denied):self.c.verify('x'*40)
 def test_timeout_fails_closed(self):
  with patch.object(self.c.requests,'post',side_effect=self.c.requests.Timeout):
   with self.assertRaises(Denied):self.c.verify('x'*40)
 def test_disabled_site_unchanged(self):
  self.f.conf={}
  with patch.object(self.c.requests,'post') as post:self.c.verify(None);post.assert_not_called()
 def test_limits_atomic_and_identity_hashed(self):
  self.r.budget('login','private@example.test',10)
  self.assertNotIn('private@example.test',self.f.cache.eval.call_args.args[2]);self.assertIn("redis.call('INCR'",self.f.cache.eval.call_args.args[0])
 def test_over_budget_has_retry_header(self):
  self.f.cache.eval.return_value=[11,42]
  with self.assertRaises(Denied):self.r.budget('login','a',10)
  response=types.SimpleNamespace(headers={});self.r.response_headers(response);self.assertEqual(response.headers['Retry-After'],'42');self.assertEqual(self.f.local.response['retry_after_seconds'],42)
 def test_redis_failure_not_silent_bypass(self):
  self.f.cache.eval.side_effect=RuntimeError('offline')
  with self.assertRaises(Denied):self.r.budget('login','a',10)
  self.assertEqual(self.f.local.response['http_status_code'],503)
 def test_checkout_guard_and_legacy_cmd(self):
  for path in ['/api/method/institute_lms.cybersource.start','/api/v1/method/institute_lms.cybersource.start','/api/v2/method/institute_lms.cybersource.start','/']:
   self.f.local.request.path=path;self.f.form_dict={'cmd':'institute_lms.cybersource.start'}
   with patch.object(self.r,'budget') as b:self.r.guard();self.assertEqual(b.call_args.args,('checkout','teacher',12))
 def test_login_limits_account_and_ip(self):
  self.f.form_dict={'usr':' TEST@EXAMPLE.COM '}
  with patch.object(self.r,'budget') as b:self.r.before_login();self.assertEqual(b.call_args.args,('login-account','test@example.com',10,300));self.assertEqual(b.call_count,2)
 def test_static_pages_not_counted(self):
  self.f.local.request.path='/campus'
  with patch.object(self.r,'budget') as b:self.r.guard();b.assert_not_called()
if __name__=='__main__':unittest.main()
