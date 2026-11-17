import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch

class PeopleTests(unittest.TestCase):
 def setUp(self):
  self.f=types.ModuleType('frappe');self.f.whitelist=lambda **kw:lambda fn:fn;self.f.PermissionError=PermissionError
  self.f.throw=lambda msg,kind=ValueError:(_ for _ in ()).throw(kind(msg))
  self.owner=MagicMock();self.manager=MagicMock();platform=types.ModuleType('institute_lms.platform');platform.owner=self.owner
  access=types.ModuleType('institute_lms.owner_access');access.require_manager=self.manager
  ops=types.ModuleType('institute_lms.owner_operations');ops.sources=lambda:['campus.test'];ops.connect=MagicMock()
  self.conn=ops.connect.return_value;self.c=self.conn.cursor.return_value.__enter__.return_value
  self.patch=patch.dict(sys.modules,{'frappe':self.f,'institute_lms.platform':platform,'institute_lms.owner_access':access,'institute_lms.owner_operations':ops});self.patch.start();self.addCleanup(self.patch.stop)
  spec=importlib.util.spec_from_file_location('institute_lms.owner_people_under_test',Path(__file__).parents[1]/'institute_lms/owner_people.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m);self.connect=ops.connect
 def test_guest_and_delegated_admin_denied_before_connection(self):
  for check in (self.owner,self.manager):
   check.side_effect=PermissionError
   for fn,args in ((self.m.overview,{}),(self.m.directory,{'site':'campus.test'}),(self.m.detail,{'site':'campus.test','user':'test'})):
    with self.assertRaises(PermissionError):fn(**args)
   check.side_effect=None
  self.connect.assert_not_called()
 def test_unconfigured_campus_rejected(self):
  for site in ('../private','other.test','campus.test/../../'):
   with self.assertRaises(PermissionError):self.m.directory(site)
  self.connect.assert_not_called()
 def test_input_validation(self):
  for kwargs in ({'kind':'secret'},{'state':'bad'},{'page':-1},{'page':'1.1'},{'page':10001},{'query':'a'*121}):
   with self.assertRaises(ValueError):self.m.directory('campus.test',**kwargs)
  with self.assertRaises(ValueError):self.m.detail('campus.test','a',section='User')
  self.connect.assert_not_called()
 def test_search_is_parameterized_and_wildcards_literal(self):
  self.c.fetchall.side_effect=[[{'total':1}],[]]
  self.m.directory('campus.test',query="x' OR 1=1 --_%!",kind='Teacher',state='Enabled')
  args=self.c.execute.call_args_list[1].args
  self.assertNotIn("x'",args[0]);self.assertIn("!_!%!!",args[1][-1]);self.assertEqual(args[1][:2],['Teacher',1])
 def test_read_only_pagination_closes_connection(self):
  self.c.fetchall.side_effect=[[{'total':26}],[{'user':str(i)} for i in range(26)]]
  result=self.m.directory('campus.test',page=1)
  self.assertEqual(len(result['rows']),25);self.assertTrue(result['has_next']);self.assertEqual(self.c.execute.call_args_list[0].args[0],'START TRANSACTION READ ONLY')
  self.assertEqual(self.c.execute.call_args.args[1][-2:],(26,25));self.conn.close.assert_called_once()
 def test_missing_identity_rejected_and_connection_closed(self):
  self.c.fetchall.return_value=[]
  with self.assertRaisesRegex(ValueError,'not found'):self.m.detail('campus.test','unknown')
  self.conn.close.assert_called_once()
 def test_failed_campus_not_returned_as_zero(self):
  self.connect.side_effect=RuntimeError('secret')
  r=self.m.overview()['campuses'][0];self.assertFalse(r['available']);self.assertNotIn('counts',r);self.assertNotIn('secret',r['message'])
 def test_person_columns_exclude_secrets(self):
  for secret in ('password','api_key','api_secret','otp','birth'):
   self.assertNotIn(secret,self.m.IDENTITY)
 def test_institute_subscription_does_not_include_student_plans(self):
  self.c.fetchall.side_effect=[[{'workspace':'academy','kind':'Institute'}],[]]
  self.m.detail('campus.test','owner',section='subscription')
  self.assertIn("AND role='Institute'",self.c.execute.call_args.args[0])
 def test_connection_links_include_incoming_requests(self):
  self.c.fetchall.side_effect=[[{'workspace':'academy','kind':'Institute','profile':'profile'}],[],[]]
  self.m.detail('campus.test','owner')
  self.assertIn('OR r.profile=%s',self.c.execute.call_args_list[2].args[0]);self.assertEqual(self.c.execute.call_args_list[2].args[1][:4], ('owner','owner','owner','profile'))

if __name__=='__main__':unittest.main()
