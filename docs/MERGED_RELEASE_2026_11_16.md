# Merged release deployment — 16 November 2026

Application commit: 5845053f67ee014ee93fe81f7ead832eb44ed97d.
Includes Dev 1e9ffd3 and pending changes since the confirmed production baseline f013d40. Deployment helpers are committed separately; the archive identifies the application commit.

Validation: 204 frontend tests, production frontend build, 1082 backend tests (including eight installer tests). Production execution and live account/payment workflows remain unverified until deployment.

From this repository in Windows Command Prompt:

```bat
git push https://github.com/tharukakaru/Sisu.git HEAD:main HEAD:tharuka
git push origin HEAD:mergetharukaa-prod
scp -o ServerAliveInterval=15 -o ServerAliveCountMax=6 "..\release-candidate\sisu-production-merged.tgz" ".\scripts\deploy-production-merged.py" root@13.140.131.250:/tmp/
ssh -o ServerAliveInterval=15 -o ServerAliveCountMax=6 root@13.140.131.250 "python3 /tmp/deploy-production-merged.py --apply"
```

Run each command only after the previous command succeeds. Do not force-push if a collaborator has changed a branch. The installer must run as root and manages maintenance and service restarts itself; do not append a separate restart.

The installer validates source fingerprints and all required assets, installs pyotp, checks pending historical patches and duplicate invoice receipt numbers, and puts all four configured sites into maintenance. It backs up databases, uploads, configuration and changed source files privately before writing application files and migrating staging, public campus, teen campus and platform sites. HTTPS ping, campus asset references, served asset hashes and unchanged public plan catalogue are checked before workers restart. No gateway settings or optional feature flags are enabled.

Backups and detailed logs are under /home/sisu/.sisu-secrets in the timestamped directory printed by the installer. They contain private data and must never be committed. If failure occurs after migration begins, maintenance remains enabled and services stop; inspect the private log and resolve the failure before reopening. Do not run an older installer over a partially migrated database. Before migration, the installer restores changed source files on failure.

After a successful deployment, verify login, signup and completion for all three provider roles, institute switching, classroom photos and Progress, and the changed teacher/institute panels. Verify billing and notifications separately before claiming payment or SMS delivery success.
