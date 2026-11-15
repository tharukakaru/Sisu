"""Transactional approval notices; delivery failures remain visible in worker logs."""
import frappe


def queue(relationship):
    for channel in ('email', 'sms'):
        frappe.enqueue('institute_lms.teacher_approval_notice.deliver',
            relationship=relationship, channel=channel, enqueue_after_commit=True, queue='short')


def deliver(relationship, channel):
    r = frappe.get_doc('IL Profile Relationship', relationship)
    if r.status != 'Active' or r.kind != 'Teacher membership':
        return
    title = frappe.db.get_value('IL Public Profile', r.profile, 'display_name')
    body = f'Your teaching request to {title} has been approved. Sign in to SISU to open your institute workspace.'
    if channel == 'email':
        from .invitations import send_notice
        if not send_notice(r.user, 'Your institute request is approved', body):
            frappe.throw('Outgoing email is not configured for the approval notice.')
    elif channel == 'sms':
        phone = frappe.db.get_value('IL Verified Phone', {'user': r.user}, 'phone')
        if not phone:
            frappe.throw('Verified phone missing for the approval notice.')
        from .providers import sms
        sms(phone, body, idempotency_key='teacher-approved:' + r.name + ':' + str(r.modified))
