from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase
from pypdf import PdfReader
from institute_lms.subscription_receipt import render


class SubscriptionReceipt(TestCase):
    def test_receipt_is_pdf_with_exact_amount_and_readable_dates(self):
        bill=SimpleNamespace(name='invoice-123',status='Paid',currency='LKR',amount_minor=500,
            receipt_number='SISU-R-invoice-123',billed_to='Demo Teacher',billing_email='teacher@example.test',
            plan='Individual',creation='2026-11-15 19:05:30.314686',period_start='2026-11-15 19:05:30',
            period_end='2026-12-15 19:05:30',paid_at='2026-11-15 19:56:29.12345',payment_channel='CyberSource live')
        raw=render(bill);self.assertTrue(raw.startswith(b'%PDF-'))
        pdf=PdfReader(BytesIO(raw));self.assertEqual(len(pdf.pages),1)
        text=pdf.pages[0].extract_text()
        for value in ('LKR 5.00','SISU-R-invoice-123','15 Dec 2026','Sri Lanka','PAID'):
            self.assertIn(value,text)
        self.assertNotIn('314686',text);self.assertNotIn('Â',text)

    def test_unpaid_checkout_has_no_invoice_pdf(self):
        for status in ('Draft','Unpaid','Void','Failed'):
            with self.assertRaises(ValueError):
                render(SimpleNamespace(status=status,receipt_number=None))
