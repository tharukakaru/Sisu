import unittest
from email import message_from_bytes, policy
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import Mock

from institute_lms.message_templates import (
    action, add_email_design, details, format_sms, paragraph, render_email,
    sendmail, verification_body, verification_sms,
)


class MessageTemplates(unittest.TestCase):
    def test_escape_user_values_and_invalid_action(self):
        body = paragraph('<script>bad</script>') + details([('Name', '<img src=x>')])
        html = render_email('<img onerror=x>', body)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img src=x>', html)
        self.assertIn('&lt;img onerror=x&gt;', html)
        for url in ('javascript:alert(1)', '//evil.test', 'https://user:pass@host.test'):
            with self.assertRaises(ValueError): action('Open', url)
        self.assertIn('&amp;', action('Open', 'https://sisu.test/campus?a=1&b=2'))

    def test_otp_leading_zero_and_expiry_preserved(self):
        self.assertIn('019092', verification_body('019092'))
        text = format_sms(verification_sms('019092', purpose='Admin sign-in', minutes=5))
        self.assertIn('019092', text)
        self.assertIn('5 minutes', text)
        self.assertIn('Never share', text)
        self.assertLessEqual(len(text), 160)
        with self.assertRaises(ValueError): verification_body('<svg>')

    def test_related_logo_and_plain_text_survive_mime_roundtrip(self):
        mail = EmailMessage()
        mail['Subject'] = 'Verify your email'
        mail.set_content('Your code is 019092. Expires in 10 minutes.')
        add_email_design(mail, verification_body('019092'))
        parsed = message_from_bytes(mail.as_bytes(), policy=policy.default)
        self.assertIn('019092', parsed.get_body(('plain',)).get_content())
        self.assertIn('cid:sisu-logo', parsed.get_body(('html',)).get_content())
        images = [part for part in parsed.walk() if part.get_content_type() == 'image/png']
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]['Content-ID'], '<sisu-logo>')
        self.assertEqual(images[0].get_content_disposition(), 'inline')
        self.assertTrue(images[0].get_payload(decode=True).startswith(b'\x89PNG'))

    def test_framework_wrapper_preserves_pdf_queue_and_redaction(self):
        framework = SimpleNamespace(sendmail=Mock(return_value='queued'))
        attachment = {'fname':'SISU-0123456789.pdf','fcontent':b'%PDF-test'}
        result = sendmail(framework, subject='Paid invoice', message=paragraph('Paid'),
                         recipients=['owner@example.test'], attachments=[attachment], delayed=True,
                         now=True, redact_message_after_send=True, reference_name='invoice')
        self.assertEqual(result, 'queued')
        args = framework.sendmail.call_args.kwargs
        self.assertEqual(args['attachments'], [attachment])
        self.assertEqual(args['reference_name'], 'invoice')
        self.assertTrue(args['redact_message_after_send'])
        self.assertTrue(args['raw_html'])
        self.assertTrue(args['inline_images'][0]['filecontent'].startswith(b'\x89PNG'))

    def test_sms_keeps_security_data_and_local_language(self):
        body = 'SISU: SISU: Payment accepted. Key: 1234-ABC. https://local.test/?a=1&b=2'
        text = format_sms(body)
        self.assertEqual(text.count('SISU'), 1)
        self.assertEqual(format_sms(text), text)
        self.assertIn('1234-ABC. https://local.test/?a=1&b=2', text)
        self.assertIn('සිංහල', format_sms('සිංහල'))
        self.assertTrue(format_sms('You’re ready – join now.').isascii())


if __name__ == '__main__':
    unittest.main()
