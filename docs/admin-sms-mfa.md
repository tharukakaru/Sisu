# Platform admin SMS MFA

`institute_lms.admin_mfa` extends Frappe's native password/OTP flow. The feature
requires `il_control_plane` and `il_admin_sms_mfa_enabled` in site configuration.
No site is enabled by installing the code alone.

The local Docker platform site was enabled on 2026-11-15. Its three existing admin
accounts use the authorized QA handset ending 6212. Student-campus MFA settings
were not changed. No live site was configured and no changes were pushed.

## Configuration

- System Settings: enable two-factor authentication, method SMS, restricted-IP
  bypass disabled. SMS Settings contains the Notify endpoint metadata; credentials
  remain in the protected Notify credentials file outside the repository.
- `SISU Admin SMS MFA` is a non-desk role with `two_factor_auth = 1`. It grants no
  administrative permissions. Owner access continues to be checked separately.
- Existing administrators must be enrolled with `admin_mfa.enroll(user, phone)`
  by a trusted operator. Local QA accounts share `User.phone`; mobile-number login
  is disabled. Frappe prefers `User.mobile_no` when present, otherwise `User.phone`.
- Accepted admin invitations automatically enroll the recipient and copy the
  verified phone. Missing phone/configuration fails closed.
- The Notify sender and credentials are supplied by the existing protected
  platform adapter. No code is returned to the browser or autofilled.

## Security behavior

Password authentication precedes SMS delivery. Codes expire after five minutes,
allow at most five guesses, and are consumed atomically. Temporary login
credentials are removed after success or challenge invalidation. SMS requests
have a one-minute cooldown, five requests per account per hour and fifteen per
IP per hour. Uncertain sends are not automatically retried.

All new admin login sessions require the SMS proof, including attempts through
OAuth, email links, or `login_as`; admins should use password sign-in. Existing
authenticated sessions and separately issued API credentials are not revoked by
enabling this feature. SMS MFA does not replace account/role authorization.

Frappe clears site caches between the password and OTP requests. The hook
`persistent_cache_keys` preserves the short-lived MFA proofs and rate limits.
Other sites retain the framework's standard SMS adapter behavior.

## Local validation

- 15 MFA tests passed: wrong/expired codes, fifth-attempt limit, replay, delivery
  failure, resend cooldown, alternate-login rejection, site isolation and invite
  enrollment.
- 12 admin invitation tests and 22 owner permission tests passed (49 total).
- Real Notify.lk delivery to the authorized handset was confirmed by the user.
  A real SMS code successfully opened the local platform admin dashboard in Chrome.
- The browser rejected an invalid OTP. An integration check confirmed that a
  successful password alone leaves the session unauthenticated.
- Source compilation and focused whitespace checks passed.

Local configuration rollback data is in `.git/local-admin-mfa-before.json` and
is intentionally excluded from Git. Production deployment/enrollment was not
performed.
