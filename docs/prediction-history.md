# Prediction history

`GET /predictions/history` keeps its `count`, `limit`, and newest-first
`predictions` response. By default, history remains an in-process ring buffer
of 200 records. Set `RULGUARD_HISTORY_DB` to a writable local SQLite file to
retain records across restarts; its parent directory must already exist.
`RULGUARD_HISTORY_LIMIT` optionally sets a positive retained row count (default
200). Invalid configuration or an inaccessible database fails initialization;
the service does not silently fall back to volatile storage.

SQLite uses WAL, parameterized queries, a connection per operation and a
30-second lock timeout. Insertion and pruning are one transaction. Multiple
workers can share a local database, provided they use the same retention limit.
The limit bounds retained rows, not total disk bytes. Pruned rows are not a
secure-erasure guarantee. Operators must protect and manage the database and
its WAL/SHM sidecars as application data. Use a local filesystem that supports
SQLite locking, not a network filesystem.

Records cover validated requests reaching `/predict/rul` and `/predict/hi`,
including rejected domains and inference failures. Each has a UUID `id`, UTC
`timestamp`, `kind`, `status` (`succeeded` or `failed`), safe request counts,
`input_fingerprint` (SHA-256 of canonical serialized request data), model and
feature-schema versions, compatibility state, warnings, and result summary.
The fingerprint identifies submitted features and dataset identifier, not an
original raw dataset. Model versions hash the loaded artifact bytes; feature
schema versions hash the ordered model feature names, not feature values or
an asserted upstream extraction version. Versions are null when unavailable.
HI's model version combines the reference HI and stage-threshold artifact
hashes, and is null unless both are available.

Existing RUL-hour/missing-count and latest-HI/stage summaries remain available;
history does not retain full HI trajectories. Failed records have a null result
and a stable error code, never exception text. Compatibility is `UNSUPPORTED`
for rejected datasets, `INVALID_INPUT` for endpoint input rejection,
`NOT_EVALUATED` when the gate could not complete, and `FULLY_SUPPORTED` only
following successful execution of the existing FEMTO endpoint checks. This
records those checks and does not independently validate dataset provenance.

Only the allowlisted dataset label `femto` (otherwise `other`), counts, hashes,
and prediction summaries are retained. No feature values, arbitrary channel
names, raw uploads, filenames, or request/error text are stored. The store
interface accepts trusted internal summaries; callers must preserve this
contract. Missing RUL features produce a median-fill warning; HI records warn
that stage is severity, not a fault diagnosis. Request-schema validation errors
before endpoint execution and `/dataset/inspect` are not prediction records.
A history write/read failure returns retryable `503 HISTORY_UNAVAILABLE`;
a result is not returned as successful if its history could not be saved.

History retains the existing service-wide access behavior: there is no user
ownership or authentication. Do not expose it as private per-user storage.
Vercel/serverless local storage is ephemeral and not shared across instances.
SQLite there cannot provide durable history; an external store is required
and is outside this change's scope. This implementation also does not provide
job resumption, idempotent retries, or guaranteed recording after process death.
