# Unified teacher onboarding

This flow is opt-in per campus. Enable `il_unified_teacher_signup = 1` with public signup and shared campus enabled. The control plane is excluded. Enable `il_institute_teacher_coverage = 1` to apply an accepted institute's eligible subscription to that institute workspace. These flags were enabled only on the local campus during development.

## Teacher journey

One Teacher signup collects the profile and verifies email. Mobile verification must also succeed before access. New signup profiles do not need to be entered a second time. Existing incomplete profiles still require completion.

After identity verification, a POST creates or reuses a personal Teacher workspace. The existing account billing record supplies the 14-day trial; returning, joining an institute, or receiving profile approval does not restart it. Profile review remains Pending until SISU reviews it; this change does not issue a verified badge.

The sidebar and workspace switcher open **Join institute**. Teachers can search verified institutes, view their public profiles, and register with one. Pending requests remain locked and can be withdrawn through a confirmation popup; a success popup confirms cancellation. The request remains Pending and creates an in-app notice for the institute's active admins. Acceptance is still performed by that institute's admin. Only then can the teacher open that institute workspace. Institute work retains existing assignment and membership permissions. An eligible institute subscription covers only the selected institute workspace; the personal workspace uses the teacher's own trial or paid plan.

Existing stored `Individual Teacher` account types and legacy teaching paths are retained for compatibility. With the flag disabled, the previous entry flow is retained. No existing profiles or institute requests are automatically approved.

## Local validation

- Both legacy teacher paths enter the shared dashboard after completed verification, while profiles remain Pending.
- Reopening a personal workspace preserves account trial dates.
- A rolled-back database fixture checked institute requests, admin notifications, rejection of self-approval, acceptance by the institute admin, institute-only subscription coverage, and unchanged personal trial dates.
- Frontend tests cover unified signup routing, completed/incomplete identity entry, and expired-trial recovery. Backend tests cover provisioning ownership, disabled flags, revoked membership, code collisions, and signup verification boundaries.
- No card charge, real SMS signup, or deployment is part of this change.
