# SISU local security dependency retest

Date: 17 November 2026. Branch: Dev. **Testing and runtime changes were local only. The user subsequently authorized delivery of the fixes to Dev; no hosted-site deployment is included.**

## Result

Resolved the six previously reported Python dependency findings through a tested, dependency-only Frappe/LMS backport. The candidate environment passed compatibility tests before the active local environment was updated. Normal dependency resolution and `uv pip check` both pass; no dependency conflicts were ignored. Local web, workers and scheduler were restarted.

The Python package audit returned **zero known vulnerabilities among 221 scanned pinned registry packages**, down from 79 advisory entries across six packages. npm audit also returned **zero known vulnerabilities**. Five editable packages (Frappe, LMS, SISU, payments and the local harness) and two direct-source packages (Gunicorn and PyPika) were excluded from the registry requirements audit. Zero findings is not a full source-code or infrastructure security certification.

Exact versions, source commits, reapplication and rollback are in [the dependency backport handover](../deployment/security-dependencies-20261117/README.md).

## Retest evidence

| Area | Result |
|---|---|
| Full Python unit suite in upgraded candidate | 1,164 passed |
| Frontend suite | 215 passed |
| Database-backed institute/payment/service checks after active upgrade | 42 passed; all writes rolled back |
| Student second-month access and renewal | 9 passed; all writes rolled back |
| Running-server HTTP login/logout/role/CSRF checks | 15 passed |
| Real library compatibility | File-lock contention, Git index, Pillow image operations, lxml parsing, LMS Markdown and PDF read/write passed |
| Student, unified Teacher and Institute signup | Actual Redis challenge issuance, wrong-code rejection, email-before-phone ordering, resend cooldown, code verification, weak-password rejection, password persistence and consumed-challenge rejection passed; no privileged roles granted |
| Existing-role login | Teacher, Student, Institute Admin and platform Administrator authenticated and resolved their server roles; logout cleared authentication; wrong password rejected |
| Role isolation | Non-platform roles denied platform administration; institute teachers limited to assigned teaching, not institute tuition approval |
| Payment integrity | Amount mismatch denied, duplicate settlement idempotent, no access from unpaid/expired tuition; simulated verified approval unlocks access |
| Subscription settlement | Teacher and Institute simulated settlement activated their plans, generated SISU- plus 10 random digits, queued customer/admin SMS once and attached a correctly named PDF email once |
| Real receipt | Existing paid local invoice rendered as PDF and its number was readable in parsed PDF text |
| Request limits | Real Redis: 12 concurrent requests yielded exactly 3 allowed/9 throttled; WSGI test yielded 200/200/429 and valid Retry-After |
| Default protections | Developer mode, ignore_csrf and allow_tests remain off; CAPTCHA remains enabled; guest privileged endpoints denied; nosniff present |
| Actual browser CAPTCHA/gateway | User solved Google challenge; server accepted it; CyberSource contact step 1 of 3 opened |
| Checkout close/reopen | Same contact form reopened immediately in the same tab, with checkout still Draft and plan still Trial |

Student login initially resolves to the campus chooser until the existing Horizon membership is selected, then resolves to Student. Institute Admin is a campus role and is separate from delegated platform Admin.

## Scope and limits

- Signup delivery was captured in process; account creation/password checks used the real local database and Redis, then rolled back. No new real OTP emails or SMS were sent in this retest.
- Payment settlement and notification tests were simulated in rollback-only transactions. No real card details were entered, no payment was submitted, and no external payment or delivery success is inferred from those simulations.
- The actual browser check covered Google verification through CyberSource contact-form loading and reopening. It did not submit card details or retest banking/3DS settlement.
- Google OAuth signup callback, real delegated-Admin SMS MFA delivery, password-reset email delivery and invitation-link delivery were not repeated end to end. Their existing automated security suites passed. Full Administrator password-only policy remains the user's existing choice; delegated Admin still requires SMS MFA.
- Framework updates, production topology, edge protection, all API mutation-method declarations, source-fork advisories and previously shared-secret rotation still need release review. The existing security review's non-dependency follow-ups remain open.

## Local evidence

Ignored evidence under `local-docker/`: `security-candidate-audit.json`, `security-candidate-audit-requirements.txt`, `security-npm-retest.json`, `security-dependency-runtime-results.json`, `security-http-retest-results.json`, `scripts/full-qa-service-results.json`, `scripts/full-qa-student-renewal-results.json`, `security-checkout-captcha-retest.png` and `security-checkout-reopened.png`. Credentials and CAPTCHA secrets remain outside tracked files.

The temporary compatibility environment remains at `/home/frappe/workspace/frappe-bench/env-security-candidate-20261117` for further investigation. The active environment uses the same six tested security versions.

## Authentication browser follow-up (17 November)

Local browser checks after the dependency upgrade:

- A disposable delegated **Admin** received a real Notify.lk SMS at the user-approved test number. Password authentication alone did not open `/campus`. An incorrect OTP was rejected. The user-supplied SMS code opened the administration dashboard successfully; sign-out returned to login.
- The real database-backed access guard rejected that Admin's attempt to manage platform-owner access. The temporary account and its access grant were disabled and its sessions revoked after testing. The existing full Administrator was unchanged.
- All **17 Admin MFA unit tests** passed again, covering expiry, single use, attempt limits, cooldown, delivery failure, and password-only/OAuth bypass rejection. These negative tests are automated fixtures, distinct from the real delivery/login test above.
- A real Google sign-in for the original Google test account returned to local SISU and prefilled the Student signup form without a 417 or redirect mismatch. Email verification was requested, but the user said that inbox was unavailable; registration was not completed for that address.
- The Google consent screen identifies the OAuth application as **n8n**, not SISU. Correct its Google Cloud branding before release; no Google Cloud settings were changed during this test.
- The user authorized resetting the local `sadisnad@gmail.com` Student for a fresh Google signup. A database backup was taken first. The old User was renamed to a disabled archive identity, preserving linked class/payment records; its registration email association was archived too. Google authentication for that address was not completed. The user subsequently selected `atdhanupa@gmail.com` and explicitly chose to keep its institute account and test Google login only. The archived Student remains disabled; fresh end-to-end signup is **not a pass** and is outside this final chosen login-only check.
- Real Google signup with the existing `atdhanupa@gmail.com` identity displayed **Account already exists** and its Log in button returned to the local login page. A subsequent Google login opened **Horizon Learning Academy → Institute overview** with **Institute Admin** displayed. Existing institute data was retained. No duplicate Student account was created through the learner signup path. The duplicate-account popup incorrectly says “student campus” for this institute identity; routing itself succeeded.
- The four signup-boundary and thirteen signup-completion unit tests passed again. They cover Google identity/session matching, existing-account protection, email/phone proof and privilege isolation; they do not substitute for the unfinished real fresh-signup test.
- Minor MFA UX issue observed: after a wrong code, the framework temporarily replaced the verification button label with the error sentence and also displayed a message dialog. Correct-code submission still worked.

Evidence: ignored `local-docker/admin-mfa-challenge-20261117.png`, `local-docker/admin-mfa-success-20261117.png`, `local-docker/google-qa-signin-handoff-20261117.png`, `local-docker/google-existing-institute-20261117.png` and `local-docker/google-institute-login-success-20261117.png`. The local student rollback database is `sites/sisuacademylk.com/private/backups/20261117_090838-sisuacademylk_com-database.sql.gz` inside the bench container. Private reset metadata remains under `.git/`, outside tracked files. No hosted-site changes or payments were made.

### Local wording follow-up

Changed the shared existing-account popup from “your student campus” to “your SISU workspace” for all account types. The frontend production build passed. A real Google signup attempt with the existing local institute identity showed the new text, and its Log in action returned to `/login?redirect-to=/campus`. Screenshot: ignored `local-docker/account-exists-wording-fixed-20261117.png`.

The public live login page was read without signing in or making changes: it advertises OAuth project 719381599910, whereas local Google sign-in uses project 176942346762. The Google Cloud branding page for the local project reports insufficient permissions for the signed-in `atdhanupa@gmail.com` account. Renaming its Google-hosted “n8n” consent branding to SISU is therefore pending project-owner access. No Google Cloud settings were changed. Google controls this name through Google Auth Platform → Branding, not through the local frontend's text or Social Login Key display label.
