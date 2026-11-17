import ast,unittest,sys
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
from datetime import datetime,timedelta
ROOT=Path(__file__).resolve().parents[1]
def functions(file,names,env):
 tree=ast.parse((ROOT/'institute_lms'/file).read_text(encoding='utf-8-sig'))
 selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 for n in selected:n.decorator_list=[]
 exec(compile(ast.Module(body=selected,type_ignores=[]),file,'exec'),env)
 return env
class ReminderWindow(unittest.TestCase):
 def test_window(self):
  f=functions('session_reminders.py',['due'],{'get_datetime':lambda v:v,'timedelta':timedelta})['due'];now=datetime(2026,11,16,20)
  for seconds,expected in [(-1,False),(0,False),(1,True),(240,True),(300,True),(301,False)]:
   with self.subTest(seconds=seconds):self.assertEqual(f(now+timedelta(seconds=seconds),now),expected)
class ReminderEligibility(unittest.TestCase):
 def setUp(self):
  self.room=N(name='c',institute='i',active=1);self.meeting=N(institute='i',classroom='c',status='Scheduled');self.member=N(name='s',user='u',role='Student',active=1,institute='i')
  self.db=N(exists=Mock(return_value=True),get_value=Mock(return_value=True));self.access=Mock(return_value={'allowed':True})
  self.env=functions('session_reminders.py',['eligible'],{'frappe':N(db=self.db),'__name__':'institute_lms.session_reminders'})
  self.modules=patch.dict(sys.modules,{'institute_lms.api':N(access=self.access)});self.modules.start()
 def tearDown(self):self.modules.stop()
 def check(self):return self.env['eligible'](self.meeting,self.room,self.member)
 def test_enrolled_allowed(self):self.assertTrue(self.check())
 def test_unpaid_denied(self):self.access.return_value={'allowed':False};self.assertFalse(self.check())
 def test_cancelled_denied(self):self.meeting.status='Cancelled';self.assertFalse(self.check())
 def test_foreign_denied(self):self.member.institute='foreign';self.assertFalse(self.check())
 def test_removed_denied(self):self.db.exists.return_value=False;self.assertFalse(self.check())
 def test_disabled_denied(self):self.member.active=0;self.assertFalse(self.check())
 def test_synthetic_recipient_skipped(self):
  for email in ('learner.qa@example.invalid','learner@example.test'):
   with self.subTest(email=email):
    self.member.user=email;self.assertFalse(self.check())
if __name__=='__main__':unittest.main()
