# Raw upload lifecycle

`POST /dataset/inspect`, `/predict/rul/femto-acquisition`, `/analyze/features`,
`/analyze/rul` and the two `/blob` routes retain no raw uploads after the
request. There is no retention option or background analysis job in this
synchronous service. A retry is a new upload with a new identifier. The `/blob`
routes download the client's Vercel Blob object into the same request-owned
temporary file and then attempt to delete the blob itself on every outcome
(best effort, recorded as `blob_cleanup` in the access record; a failed delete
never turns a result into an error).
Prediction summaries remain governed by [prediction history](prediction-history.md);
cleanup does not delete history or returned results.

Multipart parsing owns its spool files and closes them on request completion,
validation rejection, parsing failure, client disconnect, cancellation, and
streaming body-limit rejection. A declared oversized body is rejected before
parsing. Each route creates one additional server-named temporary analysis file.
The shared context manager closes and unlinks that exact file on success or any
exception, including cancellation, timeout, storage failure, and file-limit 413.
The RUL route releases raw data after feature extraction, before model inference.
A disconnect after the body has arrived may allow synchronous analysis to finish;
the file is still deleted when that analysis exits.

Deletion never accepts a client filename or storage path. It closes only the
request-owned temporary file; it does not enumerate directories, delete model
artifacts, or touch another request's upload. A fixed internal `.csv` suffix does
not control parsing or imply that arbitrary data is supported.

## Cleanup tracking

The existing access record links the HTTP request ID, status and error code to a
random `upload_id` and `cleanup_state` for the analysis file:

- `not_created`: file creation did not complete.
- `pending`: the request owns the file and analysis is running.
- `deleted`: close and unlink completed.
- `failed`: close or unlink raised an operating-system error; success is withheld.

These fields contain no raw data, filenames, or filesystem paths. They describe
the analysis file, not the framework multipart spool. Requests rejected before
route entry have no analysis upload ID. Cleanup state is operational log metadata,
not a durable job registry or a new response field.

## Abandoned requests and limits

An abandoned analysis is a per-request temporary file, not a queued job. Normal
exception unwinding handles all tested terminal paths, so no stale-file sweeper
is added. Process termination that prevents `finally` from running (for example
SIGKILL), a host crash, or an operating-system unlink failure cannot guarantee
application cleanup. Deployments must use disposable runtime temporary storage;
logs with `cleanup_state=failed` require operator investigation. This policy does
not authorize scanning or deleting shared artifact directories.

`tests/test_upload_lifecycle.py` checks real route success, malformed input,
validation and processing failures, file and request 413s, disconnects,
cancellation, timeouts, prediction failure and retry, and request isolation in a
monkeypatched temporary directory. Multipart files are forced onto disk and held
by the tests until explicit closure is verified.
