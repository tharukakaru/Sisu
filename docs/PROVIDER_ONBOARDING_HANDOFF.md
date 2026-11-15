# Provider onboarding handoff — 15 November 2026

Completed verified profiles resume without the old profile editor. Independent teachers and institute admins continue to their owned workspace, with plan selection over a disabled workspace until billing permits access. Institute teachers choose up to five institutes; pending requests do not grant membership. Both paths provide sign-out to the initial sign-in page.

Workspace provisioning is an authenticated POST. It validates the approved email registration, completed profile, verified phone, account kind and teaching path. It creates only a new owned workspace, never adopts an arbitrary existing institute. Existing revoked memberships are not restored. New billing accounts require payment; public endorsement status and trial timestamps are preserved. Retrying does not create duplicate workspaces or reset a trial.

Institute approval queues separate transactional email and SMS jobs after commit. Actual delivery depends on configured providers and must be checked on the server. Browser tests do not establish delivery.

Card-required 14-day trial activation is NOT implemented by this release. Existing verified payment settlement remains the authority. Do not advertise this as a tested card trial.

Validation: 159 frontend tests; 6 provisioning/registration tests; 6 onboarding navigation tests; 39 campus tests; 4 membership scope tests; production frontend build. No live account creation, real payment or SMS was tested locally.

Deployment archive: ../release-candidate/sisu-provider-onboarding.tgz
Installer: scripts/deploy-provider-onboarding.py
The installer checks existing source hashes, accepts known preceding UI releases, backs up sources and assets privately, builds on the server, and preserves old assets for open tabs. Restart web and workers after installation.

After deployment, check email/password and Google accounts for each provider role: save profile, primary completion action, logout, second login, pending institute request, approved institute access and locked billing. Confirm approval email/SMS from worker/provider logs. Verify revoked membership remains denied.
