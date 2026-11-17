import unittest
from datetime import datetime,timedelta
from institute_lms.renewal_rules import window,period_start
class RenewalRules(unittest.TestCase):
 def setUp(self):
  self.end=datetime(2026,12,16,17,34)
  self.a=dict(role='Institute',enabled=1,paid_until=self.end,cancel_at_end=0)
 def test_exact_four_day_boundary(self):
  self.assertFalse(window(self.a,self.end-timedelta(days=4,seconds=1))['renewal_available'])
  self.assertTrue(window(self.a,self.end-timedelta(days=4))['renewal_available'])
 def test_early_purchase_preserves_remaining_days(self):
  self.assertEqual(period_start(self.a,self.end-timedelta(days=3)),self.end)
 def test_remaining_time_never_negative(self):
  self.assertEqual(window(self.a,self.end+timedelta(days=1))['remaining_seconds'],0)
 def test_cancelled_disabled_student_cannot_renew(self):
  for changes in ({'cancel_at_end':1},{'enabled':0},{'role':'Student'}):
   self.assertFalse(window({**self.a,**changes},self.end)['renewal_available'])
 def test_teacher_early_purchase_preserves_trial(self):
  self.assertEqual(period_start(dict(role='Teacher',trial_until=self.end),self.end-timedelta(days=10)),self.end)
 def test_institute_onboarding_has_no_free_trial(self):
  now=self.end-timedelta(days=10)
  self.assertEqual(period_start(dict(role='Institute',trial_until=self.end,onboarding_payment_required=1),now),now)
 def test_lapsed_account_not_charged_for_locked_months(self):
  now=self.end+timedelta(days=40)
  self.assertEqual(period_start(self.a,now),now)
if __name__=='__main__':unittest.main()
