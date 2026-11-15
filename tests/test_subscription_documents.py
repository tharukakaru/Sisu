import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch


class SubscriptionDocuments(TestCase):
    def setUp(self):
        self.bill=SimpleNamespace(name='internal-checkout',status='Paid',receipt_number='SISU-0123456789',
            receipt_email_status='Pending',billing_email='teacher@example.test',billed_to='Test <Teacher>',
            currency='LKR',amount_minor=500,plan='Individual',period_start='2026-11-15',period_end='2026-12-15')
        self.f=SimpleNamespace(get_doc=MagicMock(return_value=self.bill),sendmail=MagicMock())
        spec=importlib.util.spec_from_file_location('institute_lms.subscription_documents_test',
            Path(__file__).parents[1]/'institute_lms/subscription_documents.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.module)
        self.save=MagicMock()

    def test_pdf_attachment_and_replay_only_queues_once(self):
        with patch.object(self.module,'render',return_value=b'%PDF-test'),patch.dict(sys.modules,
                {'institute_lms.account_billing':SimpleNamespace(save=self.save)}):
            self.module.deliver(self.bill.name);self.module.deliver(self.bill.name)
        self.f.sendmail.assert_called_once()
        message=self.f.sendmail.call_args.kwargs
        self.assertEqual(message['recipients'],['teacher@example.test'])
        self.assertTrue(message['now'])
        self.assertEqual(message['attachments'],[{'fname':'SISU-0123456789.pdf','fcontent':b'%PDF-test'}])
        self.assertIn('Test &lt;Teacher&gt;',message['message'])
        self.assertNotIn('internal-checkout',message['subject'])
        self.assertEqual(self.bill.receipt_email_status,'Queued')
        self.f.get_doc.assert_called_with('IL Account Invoice',self.bill.name,for_update=True)

    def test_unpaid_and_failed_never_render_or_email(self):
        with patch.object(self.module,'render') as render:
            for status in ('Draft','Unpaid','Void','Failed'):
                self.bill.status=status;self.module.deliver(self.bill.name)
            render.assert_not_called();self.f.sendmail.assert_not_called()

    def test_email_error_keeps_paid_invoice_pending_for_retry(self):
        self.f.sendmail.side_effect=RuntimeError('mail unavailable')
        with patch.object(self.module,'render',return_value=b'%PDF-test'):
            with self.assertRaises(RuntimeError):self.module.deliver(self.bill.name)
        self.assertEqual(self.bill.status,'Paid')
        self.assertEqual(self.bill.receipt_email_status,'Pending')
