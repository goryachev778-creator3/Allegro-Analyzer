# Neon connection repair — not live-verified

Based on PR #4 automation staging plus main's fail-closed protection. No production
data, schema, product photos, order or calculation formulas were changed.

## Reproducible code defects

- `storage.state_connection` expanded URL settings and also passed
  `connect_timeout=10`. A URL containing `connect_timeout` raised Python TypeError
  before attempting a network connection. A shared settings builder now preserves
  the URL timeout and supplies a default only when absent.
- Main's health check injected a startup `options` parameter to force read-only
  mode. Transaction poolers may reject unsupported startup parameters. Health now
  connects with the same settings as storage and starts a read-only transaction
  using `SET TRANSACTION READ ONLY` before SELECT. It does not weaken read-only
  protection or inject session state. Explicit user-supplied URL options remain
  untouched; if rejected by the endpoint, diagnostics report a safe category.
- Connecting to existing production storage no longer issues CREATE TABLE. This
  avoids schema-creation privilege failures after successful authentication.

SSL remains required or stronger; channel binding and verified TLS settings from
Neon Connect are preserved. No direct-host substitution, SSL disabling, password
guessing, data import, SQLite fallback or automatic retry of a write was added.
DNS, authentication, timeout, pooler, TLS and configuration errors are categorized
without returning raw exceptions, credentials, URLs or hostnames. Existing safe
SQLSTATE categories remain. URL text is excluded from error classification so a
URL containing `connect_timeout` cannot misclassify an SSL failure as a timeout.

## Production diagnosis still required

This execution environment has no ALLEGRO_DATABASE_URL binding or project Secrets;
the read-only live check returns MISSING_SECRET here. This is not evidence that
Streamlit's own secret is missing. The exact production cause cannot be established
from CONNECTION_FAILED alone; these code defects must not be reported as its
confirmed root cause without a successful live check or the safe detailed status.

In Streamlit Cloud, use **Manage app → Settings → Secrets** and verify the top-level
`ALLEGRO_DATABASE_URL` against **Neon → existing project → Connect**, selecting the
existing database **neondb**, intended branch and existing role, with connection
pooling enabled. Copy the generated PostgreSQL URI privately, retaining its SSL
and channel-binding parameters. Do not paste it in chat, an issue or a PR. An
environment variable of the same name takes precedence over Streamlit Secrets;
ensure any such binding is current too. Do not create a new database or role.

After the owner reviews and deploys the repair, use **Диагностика Neon → Проверить
подключение Neon**. Required acceptance: status OK, expected 108 positions, successful
load of the existing analysis, no repeat import. If not OK:

- AUTH_FAILED / ROLE_INVALID: verify the existing role's current connection details.
- DNS_FAILED: verify the generated endpoint hostname, without manually inventing it.
- NETWORK_UNAVAILABLE: check existing Neon compute status, project restrictions and
  Streamlit Cloud outbound access to the generated endpoint on TCP 5432.
- POOLER_STARTUP_PARAMETER: remove unsupported custom URL `options`; use the
  generated pooled PostgreSQL URI. The app no longer adds this parameter itself.
- TLS_FAILURE: use generated TLS/channel binding settings and current trusted CA
  configuration; do not disable SSL or certificate verification.
- TABLE_MISSING / ANALYSIS_MISSING: verify the selected existing database/branch;
  stop rather than recreate tables or reimport products.

Apify SilentFlow execution remains gated on successful Neon verification, as
requested. PR #4's normalizer and review-only proposal safeguards are retained;
no paid actor run or automatic price overwrite was initiated.

## Verification limits

New tests exercise URL timeout handling, TLS rejection/preservation, pooled-safe
read-only queries returning 108 positions, error redaction and the actual Streamlit
fail-closed screen. No live Neon load test was run.

The complete upstream main suite already has 31 failures (75 passes) due to tests
initializing empty local storage without the newly required concurrency snapshot,
or expecting write-enabled UI without Neon. The same 31 failures occur after the
repair; they were reproduced separately in an untouched archive of origin/main.
They are not hidden or skipped, and this change does not bypass production guards
to turn those tests green. Targeted connection and existing automation tests pass.
