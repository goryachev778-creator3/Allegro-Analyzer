# Separate image storage — proposal only, no migration

## Confirmed in code

`komertia_quote.py` embeds original WebArchive image bytes as `data:image/...;base64,...`
in `Фото Komertia`. The importer writes these records into the `analysis` value
in `public.allegro_state`. Base64 expands binary image bytes by roughly one third,
before JSON overhead. Existing installations may also contain external image URLs
or missing images from earlier import paths. No live Neon contents were inspected.

The traffic PR retains every existing image exactly as stored. Ordinary price edits
now send field deltas and receive a version token; unchanged Streamlit reruns make
no autosave queries. This removes the repeated transfer without moving images.
Fresh browser sessions still download the complete analysis, including its images.

## Recommended next step, subject to owner approval

Use a **private S3-compatible object store** for original images, with a provider
whose storage and outbound-transfer limits fit the workload. Neon should hold a
small object reference, SHA-256, content type, byte length and dimensions, rather
than image bytes. Do not rely on supplier hotlinks for durable storage. Do not put
storage credentials or permanent public links into PostgreSQL or exported workbooks.

- Key originals by verified SHA-256, for example `originals/<sha256>.jpg`.
  Upload once, use immutable objects, and never replace an existing object with
  different contents. Validate MIME/signature, dimensions and size as the parser
  already does. Reused images may reference the same verified object.
- Keep the bucket private. Credentials belong in Streamlit Secrets with least
  privilege. Generate short-lived read URLs at display time; do not persist signed
  URLs because they expire. Refresh them before expiry without rereading analysis.
  Scope any URL cache by storage binding and authorization. Strip URL signatures
  and credentials from logs. Browser CSP/CORS and Streamlit image rendering need
  validation with the selected provider before activation.
- Load thumbnails for the visible page/grid and originals on demand. Store
  thumbnails separately; never substitute a thumbnail for the retained original.
  Changing a table price must not download, decode or re-upload an image. Streamlit
  reruns should reuse session metadata; do not globally cache authenticated images.
- Retain support for existing inline images and original URLs during transition.
  Backups must remain self-contained: download originals when explicitly exporting
  the backup, or include a verified image bundle/manifest. An object key alone is
  not an offline photo backup. Never silently export broken/expired references.

## Safe staged migration, NOT implemented or authorized here

1. Take and verify a database backup and a separately retained original-image
   manifest. Dry-run all rows, including archived rows. Never infer a missing image
   from a similar product. An A1789 repair requires its exact source archive.
2. Upload immutable objects, then read them back and verify SHA-256, byte count
   and dimensions. Preserve existing database photo fields at this stage.
3. In small transactions, add references only if the row ID, existing photo hash
   and analysis concurrency token still match the reviewed snapshot. Preserve
   every other field and the array order. Record an audit manifest. Concurrent
   changes must cause rollback, never blind overwrite.
4. Validate every image, the 41 A1789 matches, backups, quantities, prices,
   calculations, archived records and a real Streamlit restart. Keep inline data
   and objects until the owner separately approves removal of the inline copies.
   Merely adding a reference while keeping Base64 in `analysis` will **not** reduce
   initial-session Neon traffic; a later reviewed read-path/schema change is needed.
5. Deleting inline copies or unreferenced objects requires separate explicit
   approval, verified recovery and a retention window. Do not garbage-collect
   objects after a failed database transaction: they can be audited and cleaned
   up only after checking references and backups.

No bucket, production connection, migration, image deletion or photo replacement
is part of this PR. The choice of provider, credentials, access policy, retention
and recurring cost remains to be approved before implementation.
