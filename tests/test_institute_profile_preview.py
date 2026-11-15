"""Public institute previews cannot grant access or disclose private profile fields."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from test_upload_provisioning import function

class InstituteProfilePreview(unittest.TestCase):
    def test_preview_uses_viewed_institute_without_switching_membership(self):
        profile=SimpleNamespace(kind='Institute',workspace='institute-workspace')
        member=SimpleNamespace(role='Teacher')
        service=MagicMock(return_value={'profile':{'display_name':'Public institute'}})
        frappe=MagicMock();frappe._dict=lambda **kw:SimpleNamespace(**kw)
        guard=MagicMock()
        preview=function('catalog','institute_profile',{'frappe':frappe,'identity':lambda:(SimpleNamespace(name='personal'),member),'require_role':guard,'provider':lambda name:profile,'public_catalogue':service})
        preview('public-profile',2)
        guard.assert_called_once_with(member,'Teacher')
        args=service.call_args.args
        self.assertIs(args[0],profile);self.assertEqual(args[1].name,'institute-workspace')
        self.assertIsNone(args[2]);self.assertEqual(args[3],2)
        frappe.db.set_value.assert_not_called()

    def test_preview_rejects_teacher_profile(self):
        def throw(message,kind):raise kind(message)
        frappe=SimpleNamespace(throw=throw,PermissionError=PermissionError)
        service=MagicMock()
        preview=function('catalog','institute_profile',{'frappe':frappe,'identity':lambda:(None,None),'require_role':lambda *a:None,'provider':lambda n:SimpleNamespace(kind='Teacher',workspace='personal'),'public_catalogue':service})
        with self.assertRaises(PermissionError):preview('teacher')
        service.assert_not_called()

    def test_catalogue_excludes_unpublished_and_inactive_classes(self):
        filters=function('catalog','class_filters',{})
        self.assertEqual(filters(SimpleNamespace(kind='Institute',name='profile'),SimpleNamespace(name='target')),{'institute':'target','active':1,'published':1,'public_provider':'profile'})

    def test_profile_projection_excludes_private_fields(self):
        import ast
        from test_upload_provisioning import ROOT
        tree=ast.parse((ROOT/'catalog.py').read_text())
        fields=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FIELDS' for t in n.targets)))
        project=function('catalog','profile_row',{'FIELDS':fields})
        row=project({'display_name':'Public institute','bio':'About us','user':'private@example.com','phone':'+94123456789','bank_details':'private','status':'Verified'})
        self.assertEqual(row['bio'],'About us')
        for key in ('user','phone','bank_details','status'):self.assertNotIn(key,row)
