# Local dependency security backport — 17 November 2026

This is a dependency-only backport for the existing local Frappe/LMS revisions. It does not upgrade framework features or database schemas. It has **not been deployed**. A normal framework reset/update can replace these patches; recheck versions afterward.

| Package | Before | Tested version |
|---|---|---|
| filelock | 3.29.7 | 4.2.4 |
| GitPython | 3.1.62 | 3.2.1 |
| Pillow | 12.3.0 | 13.0.0 |
| pypdf | 6.19.0 | 6.21.4 |
| Markdown | 3.5.2 | 3.8.1 |
| lxml | 6.0.4 | 6.1.0 |

Frappe's current upstream dependency ranges support the first four upgrades. The existing LMS Markdown and lxml use was tested separately. Updating the whole upstream framework would introduce unrelated changes, so it was not done. This backport still needs staging validation before production.

## Reapply to the same local bench

From `E:\Projects\Sisu\local-docker`, with Docker running:

```powershell
docker compose exec -T -e SISU_LOCAL_SECURITY_UPGRADE=1 bench /home/frappe/workspace/frappe-bench/env/bin/python /home/frappe/src/institute_lms/deployment/security-dependencies-20261117/apply_local.py
docker compose exec -T bench bash /home/frappe/deploy/dev-serve.sh
```

The helper checks the named Docker bench, local host/database configuration and exact framework commits before applying changes. It is idempotent and refuses changed revisions or incompatible patch hunks. It uses normal dependency resolution and `uv pip check`; it does not suppress dependency conflicts. It is not part of startup or deployment automation.

Pinned bases:

- Frappe: `980bdb0aa497ef787679353e0dbc16fd7cefbb36`
- LMS: `389d8a2720bfbd4b2e0de3f0f3c15d4cf0485d1e`

Pre-existing LMS `frontend/yarn.lock` modifications were preserved. Only the two framework `pyproject.toml` files changed. SISU's own Pillow/pypdf minimums now require the patched versions.

## Validation

See [the retest report](../../docs/security-dependency-retest-2026-11-17.md). Keep future framework updates coordinated with these minimums: an unpatched old Frappe pin will correctly fail dependency resolution.

## Rollback

The first manual upgrade preserved its original framework manifests in `/home/frappe/workspace/sisu-frappe-pyproject-before-20261117.toml` and `sisu-lms-pyproject-before-20261117.toml`, and its freeze in `sisu-dependencies-before-20261117.txt`. The helper preserves a separate `security-dependency-backup-20261117` directory before its first application. An already-patched bench's helper backup is not the original baseline.

If regression requires rollback: stop local workers/web, restore the original framework manifests, restore SISU's previous Pillow/pypdf requirements together, and install the six **Before** versions using normal resolution with the three editable apps. Run `uv pip check`, then restart and retest. Do not simply restore the manifests while leaving conflicting installed metadata. No schema/data rollback is necessary for this dependency-only change. Rollback reintroduces the known advisory findings, so it is a temporary recovery measure, not release approval.

## Primary sources

- [Frappe dependencies](https://github.com/frappe/frappe/blob/develop/pyproject.toml)
- [LMS dependencies](https://github.com/frappe/lms/blob/develop/pyproject.toml)
- [pypdf security fixes](https://github.com/py-pdf/pypdf/releases/tag/6.21.4)
- [lxml 6.1.0](https://pypi.org/project/lxml/6.1.0/)
- [Markdown changelog](https://python-markdown.github.io/changelog/)
