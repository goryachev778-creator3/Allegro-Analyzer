# Neon traffic reduction — measured locally, not deployed

## Cause found in the current code

The application calls `save_analysis(edited)` on every Streamlit rerun: filtering, changing the margin threshold, clicking download, and ordinary UI interactions. On main at baseline e37265e each call opens a PostgreSQL connection, issues schema DDL, downloads the complete analysis JSON (including base64 original photographs), downloads prices, and writes the complete prices/analysis even when unchanged. With an uploaded Komertia quote retained, every rerun also calls a preview snapshot that downloads analysis again. Refreshing the import journal unnecessarily fetched analysis/photos too. Repeated connections add TLS/auth overhead, but the large repeated JSON transfers dominate.

This explains a concrete high-traffic path; no production Neon logs or billing telemetry were accessed, so this PR does not prove which fraction of the reported 4 GB was caused by it.

## Measurement

An offline instrumented database adapter counts the actual SQL statements, serialized parameters and results produced by the old/new code. No Neon connection is opened. The workload uses the actual supplied WebArchive locally; private rows/photos are not checked in. Scenario: 41 records, analysis JSON 11,828,533 bytes, 10 unchanged reruns and 2 individual sale-price edits. Initial session loading is excluded and identical starting data are used. State equality is asserted at the end.

| Metric | Before | After |
| --- | ---: | ---: |
| Explicit SQL statements | 72 | 6 |
| Connections | 12 | 2 |
| Writes | 24 | 4 |
| SQL/parameter UTF-8 bytes sent | 142,010,178 | 2,684 |
| Result UTF-8 bytes received | 142,004,878 | 64 |

The response payload reduction in this measured autosave workload is 99.999955%. The 64 bytes are two 32-character MD5 version tokens. TCP/TLS, PostgreSQL framing, transaction-control messages, compression and service/billing overhead are not included; these are application-payload counts, not a promise of identical Neon billing reductions. Result/egress bytes are the most relevant metric for a public-transfer warning; request bytes are reported separately, not counted as the same billed usage.

Preview projection was also executed on an isolated PostgreSQL engine: 11,667 bytes of identity/source/quantity/cost/archive metadata instead of 11,828,533 bytes of full analysis. Photographs are not returned. Full analysis/price reads are still required once for actual confirmation; post-write verification now returns a token/count instead of downloading photo JSON a second time. Initial loading of a fresh browser session still fetches originals once. Exporting already-loaded data does not require another database request.

## Implementation and safety

- Last confirmed records, version token and import profiles are cached in **each Streamlit session**, not a process-global shared dataset. Changing the database binding invalidates the cache; users/database bindings cannot see another binding's cached data. «Обновить данные из базы» explicitly reloads a fresh snapshot.
- A rerun without changes performs **zero autosave database calls**. This is not a liveness check or a promise of real-time cross-session updates; it means the session is displaying its last confirmed snapshot. Other sessions' updates become visible on refresh.
- Real edits compute per-position field deltas. A guarded `jsonb` UPDATE changes only these fields server-side; unchanged base64 photos are neither downloaded nor uploaded for an ordinary price/commission/expense edit. Only affected price-cache entries are merged.
- Version checking uses `md5(value::text)` **on the server** as an optimistic-concurrency token, not a security/authentication digest. SQL compares the expected token while taking a row lock. A concurrent import/photo change/edit rejects a stale write; no stale cache is accepted as evidence of freshness. An advisory lock serializes autosave and the new importer.
- Analysis and prices updates commit together. Failure does not advance the session snapshot/token. A discovered legacy error path that reran immediately after a rejected save was fixed, so the error and unsaved edits remain visible for backup.
- Structural changes (adding/removing/reordering rows) use a full JSON upload under the same compare-and-swap guard; there is still no full JSON download. There is no schema migration, photo deletion/compression or conversion to a different database.
- PostgreSQL may internally rewrite the single JSON/TOAST value. This is **wire-traffic optimization**, not a claim of per-product physical storage or elimination of server CPU/WAL.
- The new importer uploads only additions when appending analysis; its return-value comparison and compact read-after-write token/count protect transactional integrity. Old records remain server-side. Logs are still written atomically with successful import, separately on failure.
- File parsing and duplicate preview are session-cached. Duplicate metadata has a 30-second TTL; confirmation always rereads under a transaction lock. Journal refresh selects only its own key. Cached file/profile metadata is invalidated on explicit replacement/refresh.
- No schema `CREATE TABLE` runs on every external connection. Existing `public.allegro_state` is required, as it is for production. Idle browsing no longer opens connections. No background keepalive pool is introduced, so Neon can still suspend when idle.

## Verification and reproducibility

```bash
.venv/bin/python -m pytest -q
.venv/bin/python benchmarks/neon_traffic.py --baseline e37265e
# Optional local owner archive; never add it to Git:
.venv/bin/python benchmarks/neon_traffic.py --baseline e37265e --webarchive '/path/to/quote.webarchive'
```

The default benchmark uses 41 synthetic records with 128 KiB of synthetic photo data each: 5,391,460-byte JSON; the same workload gives 64,745,128 response bytes before versus 64 after. `docs/neon-traffic-measurement.json` contains only aggregate real-archive sizes/counters, no product data or secrets.

Tests cover no-op saves, small delta payloads, photos/archive preservation, stale-version rejection, rollback on price-write failures, optional-field removal, structural changes and retained price caches. Existing imports, calculations, photos and Streamlit tests continue to run. Additional local integration checks executed the delta and append SQL on an isolated PostgreSQL engine (PGlite), with both text and jsonb value columns, including the real archive and duplicate preview. These checks are not writes to production Neon.

## Expected effect and remaining costs

### Additional synthetic rerun measurement and monthly scenario

Reproduced with `.venv/bin/python benchmarks/neon_traffic.py --baseline e37265e
--output docs/neon-traffic-synthetic.json` (one command). Uses **only synthetic
test data**, an in-memory SQL adapter, and no network/database connection.
41 records, 5.391460 MB JSON, 10 unchanged reruns, 2 price edits:

| Metric | Before | After | Saved |
| --- | ---: | ---: | ---: |
| Explicit SQL statements | 72 | 6 | 66 (91.67%) |
| Connections | 12 | 2 | 10 |
| Writes | 24 | 4 | 20 |
| Response payload | 64.745128 MB | 0.000064 MB | 64.745064 MB |
| Request payload | 64.750440 MB | 0.002578 MB | 64.747862 MB |

MB/GB here are decimal; these are UTF-8 payloads, not observed billed wire bytes.
The benchmark includes a no-op autosave call for every rerun and verifies identical
final database state. It excludes startup reads, so the monthly projection adds
**one full analysis load per new browser session**, including Base64 images.

For the same 10 reruns + 2 edits per fresh session, over 30 days:

| Fresh sessions per day | Before, GB | After, GB |
| --- | ---: | ---: |
| 1 | 2.104098 | 0.161746 |
| 10 | 21.040976 | 1.617457 |

These are explicit scenarios, **not a prediction of the owner's measured activity**:
no session counts, elapsed quota period, current total database size or production
telemetry are available here. More/larger photos and frequent full refreshes raise
the after figure. Protocol/other-key overhead, imports, other apps and storage
provider traffic are excluded. Actual monthly usage cannot be inferred from the
4 GB warning alone. Already consumed quota is unaffected. At the 10-session/day
example, the modeled remaining workload uses about 1.62 GB per full month, plus
these excluded costs; monitor Neon before concluding it fits the free quota.

### Base64 confirmed; separate storage proposed, not migrated

The importer embeds original image bytes in `analysis`; this is confirmed in code,
not by inspecting production. The photo-preserving delta optimization works with
the current format. [Separate private object storage proposal](PHOTO_STORAGE_PROPOSAL.md)
describes verified immutable originals, short-lived read links, session reuse,
backup compatibility and staged concurrency-checked migration. **No migration or
production photo changes are executed by this PR.** Owner approval is required
before implementing that separate storage change.

For editing/filter-heavy sessions, expect the repeated large-JSON portion to drop by over 99%; the whole monthly reduction depends on workload. A fresh session still loads images; imports/new photographs/structural changes are larger operations. Frequent full browser refreshes, many users, or code outside this app can still consume the free quota. The already-used 4 GB will not be refunded. Staying below 5 GB is not guaranteed.

If an operator needs current production sizes, `diagnostics/neon_traffic_readonly.sql` returns only sizes/counts and does not download the photo JSON. It has not been run against Neon. Monitor actual public-transfer usage in the Neon console after reviewing and deploying the PR. No production database writes, schema changes, deployment or main merge were performed during this work.
