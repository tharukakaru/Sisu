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
class LiveAttendance(unittest.TestCase):
 def setUp(self):
  self.room=N(name='class',teacher='teacher');self.live=N(name='live',session='session',status='Live',institute='i',provider_room='provider')
  self.member=N(name='student',role='Student');self.meeting=N(name='session',institute='i',classroom='class',status='Scheduled')
  self.provider=Mock(return_value=N(identity='student'));self.record=Mock(return_value={'status':'Present'})
  def deny(message,*a):raise ValueError(message)
  self.env=functions('live_classes.py',['confirm_connection'],{'checked':lambda _: (self.live,self.member,self.room),'frappe':N(throw=deny,PermissionError=ValueError,get_doc=lambda *a:self.meeting),'__name__':'institute_lms.live_classes'})
  self.modules=patch.dict(sys.modules,{'institute_lms.live_provider':N(operation=self.provider),'institute_lms.operations':N(record=self.record)})
  self.modules.start()
 def tearDown(self):self.modules.stop()
 def test_real_connected_student_records(self):
  self.assertTrue(self.env['confirm_connection']('live')['attendance_recorded']);self.record.assert_called_once()
 def test_grant_alone_cannot_record(self):
  self.provider.side_effect=ValueError('Participant absent')
  with self.assertRaises(ValueError):self.env['confirm_connection']('live')
  self.record.assert_not_called()
 def test_wrong_identity_denied(self):
  self.provider.return_value=N(identity='other')
  with self.assertRaises(ValueError):self.env['confirm_connection']('live')
  self.record.assert_not_called()
 def test_ended_room_denied(self):
  self.live.status='Ended'
  with self.assertRaises(ValueError):self.env['confirm_connection']('live')
  self.provider.assert_not_called()
 def test_teacher_not_student_attendance(self):
  self.member.role='Teacher';self.assertFalse(self.env['confirm_connection']('live')['attendance_recorded']);self.record.assert_not_called()
 def test_cancelled_session_denied(self):
  self.meeting.status='Cancelled'
  with self.assertRaises(ValueError):self.env['confirm_connection']('live')
  self.record.assert_not_called()
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
