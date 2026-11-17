"""Send notifications after an institute approves a teacher membership."""
import frappe


def queue(relationship):
    """Queue delivery only after the approval transaction commits."""
    for channel in ("email", "sms"):
        frappe.enqueue(
            "institute_lms.teacher_approval_notice.deliver",
            relationship=relationship,
            channel=channel,
            enqueue_after_commit=True,
            queue="short",
        )


def deliver(relationship, channel):
    """Verify approval status before delivering a notification."""
    r = frappe.get_doc("IL Profile Relationship", relationship)

    if r.status != "Active" or r.kind != "Teacher membership":
        return

    title = frappe.db.get_value(
        "IL Public Profile", r.profile, "display_name"
    ) or "your institute"

    body = (
        f"Your teaching request to {title} has been approved. "
        "Sign in to SISU to open your institute workspace."
    )

    if channel == "email":
        from .invitations import send_notice

        if not send_notice(
            r.user,
            "Your institute request is approved",
            body,
        ):
            frappe.logger().warning(
                "Teacher approval email unavailable for %s",
                relationship,
            )

    elif channel == "sms":
        phone = frappe.db.get_value(
            "IL Verified Phone", {"user": r.user}, "phone"
        )

        if not phone:
            frappe.logger().warning(
                "Teacher approval SMS skipped: no verified phone for %s",
                relationship,
            )
            return

        from .providers import sms

        sms(
            phone,
            body,
            idempotency_key="teacher-approved:" + r.name,
        )
    else:
        raise ValueError("Unsupported notification channel")
