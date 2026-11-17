# Dev integration audit — 17 November 2026

Audited remote Dev `465feeea9efa83b047d8d361fb4463a0675d304b` against remote main/local `262fb42129f2ea616acad2e8d2baae7d9c2f3267` after a fresh fetch. Dev is an ancestor of main. There are zero Dev commits missing from main. This is a source/configuration audit, not complete live workflow certification.

## Findings and correction

- Live `portal_policy.public` initially reported unified_teacher_signup=false. Dev documents local-only activation of il_unified_teacher_signup and il_institute_teacher_coverage. The user ran the guarded activation; a fresh independent public API read now returns unified_teacher_signup=true. Coverage activation is supported by the user's successful installer output, not an authenticated end-to-end subscription test.
- ProviderFirstLogin.completed had retained our older success-modal behavior for unified teachers. Restored Dev's immediate completed event for unified teachers; institute and legacy flows retain their fixes. Regression test exercises immediate continuation and returning-teacher workspace service routing.

## Remaining application source differences from Dev

- AccountVerification.vue and ExistingAccountDialog.vue: preserve the verified-student invisible-modal fix and close dialogs before unmount.
- VerifiedSignup.vue: hide obsolete creation title after successful signup.
- InstituteJoinPicker.vue: retain pending-request recovery and allow returning to login with no selection; unified teachers use TeacherInstitutes for the new journey.
- PortalRoot.vue and portal_session.py: additional pending-workspace recovery; unifiedTeacher prop and Dev signup routing remain present.
- ProviderFirstLogin.vue: unified completion restored; retained institute layout, verified-provider recovery, and legacy continuation.
- ProviderAccessGate.vue: unified recovery and institute layout retained; older path has explicit subscription overlay and sign-out recovery.
- onboarding_navigation.py and provider_onboarding.py: additional verified legacy/institute workspace recovery. Unified teachers use teacher_workspace.open_workspace, not this legacy service.
- teaching.py and teacher_approval_notice.py: additional queued institute acceptance notifications.
- campus.html and compiled portal assets: rebuilt from merged source, rather than selecting one branch's generated files.

No other frontend/src or institute_lms application source differs from Dev. Marketing intentionally retains the user-approved clean hero artwork. Deployment and test helpers differ intentionally.

## Validation

219 frontend tests and 1,188 backend tests passed. Frontend build succeeded. Live unified-teacher policy independently checked true. No live accounts were created, payments submitted, or membership approvals performed during this audit. Private runtime settings beyond the checked policy are not claimed to be fully audited. The static completion correction still requires the supplied deployment command and live flow verification.
