"""Retryable, payment-only PDF emails; queue creation and marker commit together."""
from html import escape
import frappe
from .subscription_receipt import render, date_label

DT = 'IL Account Invoice'


def deliver(invoice):
    bill = frappe.get_doc(DT, invoice, for_update=True)
    if bill.status != 'Paid' or not bill.receipt_number or bill.receipt_email_status != 'Pending':
        return
    if not bill.billing_email:
        return
    pdf = render(bill)
    e = lambda value: escape(str(value or ''))
    message = f'''<div style="font-family:Arial,sans-serif;color:#30273e;max-width:600px">
    <h2 style="color:#572b91">Your SISU subscription payment is confirmed</h2>
    <p>Hello {e(bill.billed_to)},</p>
    <p>Thank you for your payment of <strong>{e(bill.currency)} {int(bill.amount_minor)/100:,.2f}</strong>
    for the <strong>{e(bill.plan)}</strong> plan.</p>
    <p>Your subscription covers {e(date_label(bill.period_start))} to {e(date_label(bill.period_end))}.</p>
    <p>Your paid invoice <strong>{e(bill.receipt_number)}</strong> is attached as a PDF.
    You can also download it from Subscription in your SISU account.</p>
    <p>No automatic renewal charge has been set up.</p><p>Thank you,<br>SISU Academy</p></div>'''
    queued = frappe.sendmail(recipients=[bill.billing_email],
                    subject=f'Your SISU paid invoice - {bill.receipt_number}',
                    # Frappe sends after the queue transaction commits. This worker
                    # must not wait for the site's periodic email flush to run.
                    message=message, delayed=True, now=True,
                    reference_doctype=DT, reference_name=bill.name,
                    attachments=[{'fname': bill.receipt_number + '.pdf', 'fcontent': pdf}])
    if not queued:
        raise RuntimeError('Invoice email could not be queued')
    bill.receipt_email_status = 'Queued'
    from .account_billing import save
    save(bill)


def dispatch():
    for name in frappe.get_all(DT, filters={'status': 'Paid', 'receipt_email_status': 'Pending'},
                               pluck='name', limit_page_length=20):
        frappe.enqueue('institute_lms.subscription_documents.deliver', invoice=name, queue='short')
