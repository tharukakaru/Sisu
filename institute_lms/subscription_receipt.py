"""Printable subscription documents generated on the server, with no remote assets."""
from io import BytesIO
from pathlib import Path
from html import escape
from datetime import datetime


def date_label(value, include_time=False):
    if not value:
        return '-'
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.strftime('%d %b %Y, %I:%M %p' if include_time else '%d %b %Y')


def render(bill):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    font = 'Helvetica'
    for path in (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'), Path('C:/Windows/Fonts/arial.ttf')):
        if path.exists():
            if 'SisuReceipt' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('SisuReceipt', str(path)))
            font = 'SisuReceipt'
            break
    purple = colors.HexColor('#572B91')
    style = ParagraphStyle('body', fontName=font, fontSize=10, leading=16, textColor=colors.HexColor('#30273E'))
    muted = ParagraphStyle('muted', parent=style, fontSize=9, textColor=colors.HexColor('#70657E'))
    title = ParagraphStyle('title', parent=style, fontSize=23, leading=30, textColor=purple)
    right = ParagraphStyle('right', parent=style, alignment=TA_RIGHT)
    p = lambda text, s=style: Paragraph(escape(str(text or '-')), s)
    money = f'{bill.currency} {int(bill.amount_minor)/100:,.2f}'
    paid = bill.status == 'Paid'
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=44, leftMargin=44, topMargin=42, bottomMargin=42,
                            title=('Payment receipt' if paid else 'Subscription invoice') + ' ' + bill.name, author='SISU Academy')
    width = A4[0] - 88
    heading = Table([[p('sisu.', title), p('Payment receipt' if paid else 'Subscription invoice', right)],
                     [p('SISU Academy', muted), p(bill.receipt_number if paid else bill.name, right)]], colWidths=[width*.45,width*.55])
    heading.setStyle(TableStyle([('LINEBELOW',(0,-1),(-1,-1),2,purple),('BOTTOMPADDING',(0,-1),(-1,-1),20),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story = [heading, Spacer(1,24), p('PAID' if paid else bill.status), Spacer(1,16), p('BILL TO', muted),
             p(bill.billed_to), p(bill.billing_email), Spacer(1,20)]
    details=[['Invoice',bill.name],['Issued',date_label(bill.creation)],
             ['Service period',date_label(bill.period_start)+' to '+date_label(bill.period_end)],
             ['Plan',bill.plan+' - monthly subscription']]
    if paid:
        details += [['Payment date',date_label(bill.paid_at,True)+' (Sri Lanka time)'],['Payment method',bill.payment_channel]]
    table=Table([[p(k,muted),p(v)] for k,v in details],colWidths=[128,width-128])
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    story += [table,Spacer(1,22)]
    lines=Table([[p('DESCRIPTION',muted),p('QUANTITY',muted),p('AMOUNT',muted)],
                 [p(bill.plan+' subscription'),p('1 month'),p(money)],
                 [p('Total paid' if paid else 'Total'),p(''),p(money)]],colWidths=[width*.53,width*.2,width*.27])
    lines.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F4EFFA')),
        ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#F4EFFA')),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12),
        ('LINEBELOW',(0,1),(-1,1),.5,colors.HexColor('#DED5E8'))]))
    story += [lines,Spacer(1,28),p('Thank you for choosing SISU.' if paid else 'This document is not proof of payment.'),
              Spacer(1,10),p('Class tuition is billed separately. No automatic renewal charges. This is a subscription billing document, not a tax invoice.',muted)]
    doc.build(story)
    return output.getvalue()
