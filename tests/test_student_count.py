import unittest
from datetime import datetime
from institute_lms.student_count_rules import month_bounds,qualified_students,price_for,rate_minor

class StudentCountRules(unittest.TestCase):
 def test_distinct_sessions_across_classes_count_once(self):
  rows=[dict(student='one',session=s,status='Present') for s in ['a','a','b','c']]
  rows += [dict(student='two',session='a',status='Present'),dict(student='two',session='b',status='Absent')]
  self.assertEqual(qualified_students(rows),{'one':['a','b','c']})
 def test_student_identity_not_membership_and_separate_provider(self):
  self.assertEqual(len(qualified_students([dict(student='email',member=m,session=s,status='Present') for m,s in [('m1','s1'),('m2','s2')]])),1)
  self.assertEqual(qualified_students([dict(student='email',session='s1',status='Present')]),{})
 def test_calendar_boundaries(self):
  self.assertEqual(month_bounds('2026-12'),(datetime(2026,12,1),datetime(2027,1,1)))
  self.assertEqual(month_bounds('2028-02')[1],datetime(2028,3,1))
  for value in ['2026-13','2026-1','bad','2026-11-01']:
   with self.assertRaises(ValueError):month_bounds(value)
 def test_precise_rate(self):
  self.assertEqual(rate_minor('5'),500);self.assertEqual(rate_minor('5.25'),525);self.assertEqual(rate_minor('0'),0)
  for value in ['5.001','-1','NaN','Infinity','100000.01','abc']:
   with self.assertRaises(ValueError):rate_minor(value)
 def test_effective_rate_keeps_completed_month(self):
  policy={'rates':[dict(month='2026-11',unit_minor=500,enabled=True),dict(month='2026-12',unit_minor=700,enabled=True)]}
  self.assertEqual(price_for(policy,'2026-11')['unit_minor'],500)
  self.assertEqual(price_for(policy,'2026-12')['unit_minor'],700)
  self.assertIsNone(price_for(policy,'2026-10'))
if __name__=='__main__':unittest.main()
