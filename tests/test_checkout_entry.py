import importlib.util
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest import TestCase
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs


class CheckoutEntry(TestCase):
    def test_guest_signin_keeps_only_the_invoice_in_a_local_return_path(self):
        class Redirect(Exception):
            pass
        frappe = ModuleType('frappe')
        frappe.form_dict = {'checkout_invoice': 'draft & value', 'redirect-to': 'https://untrusted.test'}
        frappe.session = SimpleNamespace(user='Guest')
        frappe.local = SimpleNamespace(flags=SimpleNamespace())
        frappe.Redirect = Redirect
        entry = ModuleType('institute_lms.portal_entry')
        entry.redirect_owner_guest = lambda: None
        spec = importlib.util.spec_from_file_location('checkout_entry_test',
            Path(__file__).parents[1] / 'institute_lms/www/campus.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'frappe': frappe, 'institute_lms.portal_entry': entry}):
            spec.loader.exec_module(module)
            with self.assertRaises(Redirect): module.get_context(SimpleNamespace())
        login = urlsplit(frappe.local.flags.redirect_location)
        self.assertEqual(login.path, '/login')
        target = urlsplit(parse_qs(login.query)['redirect-to'][0])
        self.assertEqual(target.netloc, '')
        self.assertEqual(target.path, '/campus')
        self.assertEqual(target.fragment, 'subscription')
        self.assertEqual(parse_qs(target.query), {'checkout_invoice': ['draft & value']})
