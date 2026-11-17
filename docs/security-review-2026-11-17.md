# SISU local security review — 17 November 2026

## Scope and result

Reviewed the local application, payment session creation, authentication hooks, API budgets, selected permission/upload/signup/webhook tests, installed package advisories, and checked-in proxy/worker configuration. No production deployment, live load test, payment, email or SMS was performed. Changes are prepared for the Dev branch; private keys and local site configuration remain outside Git.

This is a scoped code and local-runtime review, not a penetration-test certification or a guarantee that every vulnerability has been found. Production firewall rules, actual load-balancer topology, backups, host patch levels and all third-party integrations were not inspected. Do not describe the site as fully secure or production-ready from this result alone.

## Changes made locally

1. Added atomic Redis request budgets shared across workers. Login attempts are limited by both IP and normalized account, before password authentication. API requests are limited by IP and user, with narrower checkout/report budgets. Exceeded budgets return HTTP 429 and Retry-After. Redis protection failures deny requests with HTTP 503. Cache-clearing must preserve these counters.
2. Added reCAPTCHA v2 checkbox integration before opening/retrieving a card checkout session. The server verifies Google's response, expected hostname, success and freshness. Missing/invalid tokens, incomplete enabled configuration and verification outages deny checkout. No secret key goes to the browser. Payment confirmation still depends on trusted provider evidence, never the checkbox or browser success event.
3. Upgraded Vite 6.4.3 to 6.4.6 and rebuilt the portal. Full npm audit now reports zero known vulnerabilities, including development dependencies.
4. Added no-sniff and referrer-policy defaults on application responses.

### Request budgets

| Scope | Budget |
|---|---:|
| Password login per IP | 20 / 5 minutes |
| Password login per account | 10 / 5 minutes |
| All API traffic per IP | 1,200 / minute |
| Signed-in API traffic per user | 600 / minute |
| Guest API traffic per IP | 120 / minute |
| Checkout start per user | 12 / minute |
| Payment status/reconcile per user | 60 / minute |
| People reports per user | 60 / minute |

Existing OTP/session-creation restrictions remain in place. These are initial limits, not a measured production capacity. Monitor legitimate institute/NAT traffic and tune deliberately. They do not replace edge protection against distributed floods; requests reach the application before being rejected.

## Findings still open

### High priority: framework-pinned dependencies

The installed Python environment audit reported 79 advisory entries (77 distinct IDs) across six packages. An advisory match does not prove the affected path is reachable through SISU, and some entries concern local attacker access. Nonetheless, these require an upgrade plan before production sign-off.

| Installed package | Installed version | Scanner-reported remediation target |
|---|---|---|
| filelock | 3.29.7 | 4.2.1 |
| GitPython | 3.1.62 | 3.2.1 |
| lxml | 6.0.4 | 6.1.0 |
| Markdown | 3.5.2 | 3.8.1 |
| Pillow | 12.3.0 | 13.0.0 |
| pypdf | 6.19.0 | 6.21.4 |

Frappe/LMS pin the older ranges, including pypdf==6.19.0. A temporary pypdf 6.21.4 trial passed receipt/document tests but produced a dependency conflict; it was restored to 6.19.0. The repository requirement was also restored. Upgrade Frappe/LMS compatibly in an isolated environment, then retest uploaded images/PDFs, receipts, lessons and background jobs. Do not force-install incompatible packages into production. Package targets above reflect this audit's advisory data, not a promise that no newer advisories exist.

The pypdf maintainer lists security fixes in [6.21.4](https://github.com/py-pdf/pypdf/releases/tag/6.21.4). Vite's [security advisory](https://github.com/vitejs/vite/security/advisories/GHSA-9jrq-w75r-8gcw) explains a development-server issue; deployed static assets are a different exposure.

### CAPTCHA: local configuration update

The user subsequently supplied Google v2 keys. They are saved outside Git in a private local handover file and merged into the local campus site's site_config.json. CAPTCHA is now enabled locally with localhost and checkout.localhost as the server hostname allowlist. No production configuration was changed. Missing and invalid tokens were rejected using the real local configuration. After Docker network recovery, the user completed the real checkbox and server verification succeeded: CyberSource opened its Contact details step. No card details or payment were submitted. The chronological test and recovery evidence appears below.

### Administrative authentication

Full Administrators currently use password-only login by the user's explicit earlier choice; the Admin role uses SMS MFA. This leaves the highest-privilege accounts dependent on password security. Prefer stronger MFA for full Administrators before production. No role policy was changed in this audit. Previously shared credentials and API secrets should be rotated before release; this review did not rotate them or write them into this report.

### Load balancing and proxy boundaries

The checked-in staging configuration has one application upstream and five Gunicorn workers. This is worker concurrency, not multi-server failover. The current local server is a development server. Neither observation establishes the running production architecture.

The checked proxy configuration overwrites X-Forwarded-For, which matters because Frappe trusts it for client IP. Keep backend/Redis/database ports private; accept ingress only from trusted proxies. If a CDN is added, configure trusted source ranges before using its client-IP header. Never trust arbitrary incoming forwarding headers.

Before a multi-node rollout: use identical code/assets/configuration, shared database/Redis/session/queue storage, shared uploaded files or object storage, correct site routing, WebSocket routing, health checks, TLS, drainable workers and coordinated scheduler jobs. Validate duplicate-job protection and payment idempotency during failover. Apply edge connection/request limits, body limits and timeouts with representative classroom traffic. No infrastructure topology was changed in this task.

### Static scan triage

Bandit scanned the application and returned 1 high, 13 medium and 9 low findings. The high item is MD5 mandated by the legacy PayHere checksum protocol, not password hashing; replacing that algorithm blindly would break the protocol. Medium SQL-construction alerts were reviewed: observed table/column fragments come from fixed internal names, allowlists or fixed query clauses, and user values are parameterized. No SQL injection was confirmed in those reviewed paths. This does not prove all SQL or all 439 inventoried API methods are safe.

The API inventory found 109 methods without explicit HTTP-method declarations. They were not all converted blindly: some are read-only. A complete mutation/GET review remains follow-up work. Enforce POST and authorization for each mutating handler after examining its callers.

## Validation evidence

- 17 selected backend suites: 222 tests passed. Covers API/workspace/commercial permissions, payment integrity, CAPTCHA rejection before provider calls, owner access, MFA, signup boundaries, upload proof restrictions and webhook tests.
- 215 frontend tests passed, including CAPTCHA token completion/expiry/error/reset and narrow rendering selection. Production build succeeded; existing large-chunk warning remains.
- Fixed an outdated signup unit-test fixture to mock the separately tested teacher workspace service; no signup permission assertion was removed.
- Real Redis concurrent probe: 12 requests with a budget of 3 produced exactly 3 allowed and 9 limited.
- Real Frappe WSGI request probe with an isolated test budget produced 200, 200, 429 and Retry-After: 60. No real user's budget was reduced.
- Guest owner-report and payment-status requests were denied. Local site has developer mode, ignore_csrf and allow_tests off; no broad CORS configuration was found.
- Bounded local HTTP liveness check: 20 requests, concurrency 4, 20 successful; median 19.7 ms and p95 433.4 ms. This is a smoke test, not payment throughput or production capacity measurement.
- Local administrator browser smoke: desktop search and six detail sections passed, mobile horizontal overflow absent, guest access denied, no page errors.
- No real payment was submitted. No messages were sent. Google challenge verification awaits real keys and user interaction.

Raw local evidence (ignored by Git): local-docker/security-tests.json, security-frontend-tests.txt, security-load.json, security-bandit.json, security-pip-audit.json, security-npm-after.json and security-endpoints.json.

## Create and configure the Google keys

1. Open [Google reCAPTCHA registration](https://www.google.com/recaptcha/admin/create) in your own Google account.
2. Label: **SISU local checkout**. Select **reCAPTCHA v2**, then **I'm not a robot Checkbox** (not v3 or Invisible).
3. Add **localhost** and **checkout.localhost** as domains, without https://, ports or paths. Use the checkout.localhost hostname for the local test. Keep domain validation enabled.
4. Complete Google's required registration steps. Copy the **site key** and **secret key** into a private file outside Git, and give the assistant its local path. Do not paste the secret into frontend code or commit it.
5. Configure the campus site's private site_config.json, not the repository or a public JS file:

```json
{
  "il_checkout_recaptcha": {
    "enabled": true,
    "site_key": "YOUR_PUBLIC_SITE_KEY",
    "secret_key": "YOUR_PRIVATE_SECRET_KEY",
    "hostnames": ["checkout.localhost", "localhost"]
  }
}
```

This is a fragment to merge with existing configuration, not a replacement for the file. Configure every site that issues payment sessions, restart its workers and clear cache. Confirm missing/expired tokens cannot create a session, then solve a real challenge and open checkout without submitting a payment. Payment reconciliation must continue without requiring another challenge.

Use a separate production key for sisuacademylk.com and the actual production checkout hostname. Add only actual returned hostnames to the server allowlist. No production key/configuration was created here.

Google documents [localhost/domain validation](https://developers.google.com/recaptcha/docs/domain_validation) and [server verification, single-use tokens and expiry](https://developers.google.com/recaptcha/docs/verify). CAPTCHA is one anti-abuse control, not a substitute for authorization, rate limits, provider verification or DDoS protection.

### Actual local teacher checkout verification (17 November)

- Tested danupadanupa@gmail.com at the local HTTPS checkout. Its subscription is Trial and had no existing paid invoice to remove. Created only a draft LKR 5 checkout (k4hd7bm3np); no card/payment submitted.
- Real Google checkbox rendered. Continue to card payment was disabled before completion. The user completed the checkbox, which enabled continuation.
- End-to-end verification FAILED: local server returned `Verification could not be completed`. Independent container diagnostics confirmed TCP timeouts to Google, recaptcha.net and CyberSource. Windows reached Google's verification endpoint (HTTP 200). No success/activation is claimed.
- Fixed the widget retaining an interruption error after a later successful callback. Both focused widget tests passed and the frontend build succeeded (existing large-chunk warning remains).
- Docker restart encountered a stale zero-byte dockerInference runtime socket. Automated removal was rejected by approval review; a manual recovery step was requested. Docker/SISU service restoration and final server acceptance test remain pending. No production configuration or hosted site was changed.

### Recovery and successful verification retest (17 November)

- After the user's restart, Docker Engine 29.1.2 started successfully. Started the existing SISU compose services, web/worker/scheduler processes and local HTTPS proxy. HTTPS checkout returned HTTP 200 with normal certificate validation.
- Container connections to Google, recaptcha.net and CyberSource succeeded (TCP connect checks approximately 0.09–0.27 seconds). The earlier container networking timeout no longer reproduced.
- Signed into local checkout as danupadanupa@gmail.com. The real CAPTCHA checkbox rendered and continuation was disabled until the user completed it. Clicking Continue to card payment then passed server verification and loaded CyberSource's Checkout with card button.
- Opened the gateway's Contact details step (Step 1 of 3). Email and phone fields and the Continue button rendered successfully. No contact/card details were entered and no payment was submitted. This validates CAPTCHA-to-checkout loading, not a new completed card payment.
- All recovery and testing were local. No deployment, Git push or live-site configuration change was made.

### Dev handover checks (17 November)

- Full Python unit suite in the existing SISU container: 1,164 tests passed. The initial Windows Python attempt lacked application dependencies; the container run is the authoritative result.
- Frontend suite: 215 tests passed. Static verification: 802 Python sources and 159 JSON documents passed. Ruff undefined-name/export checks passed.
- Staged changes passed whitespace checks and an exact-value check excluding the actual CAPTCHA keys. Private configuration and handover files remain outside the repository.
- Authorized delivery is a push to Dev only. The repository's GitHub workflow runs checks and uploads build artifacts; it has no deployment step. Framework dependency findings above remain open.
