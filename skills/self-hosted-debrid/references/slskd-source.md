# slskd as a source (search + grab) — verified API shapes

Measured against slskd 0.26. Auth is optional (LAN instances can run
keyless; if a key is set it goes in the `X-API-Key` header).

## Search

- `POST /api/v0/searches`  `{"searchText", "id": <uuid4>}` — for an
  INTERACTIVE UI add the limits: `{"responseLimit": 150,
  "searchTimeout": 15000}`. Why: without limits slskd hides ALL
  responses while `InProgress` and runs its full server timeout (~45 s)
  before exposing anything; with them a popular query completes in
  ~2 s (`Completed, ResponseLimitReached`) and rare ones at the
  timeout. Trade-off: the limit TRUNCATES result sets — fine for a
  top-N results UI, never for census-style probing (counting users,
  hunting rare copies) which needs the full window.
- Poll `GET /api/v0/searches/{id}` → `state`; terminal = starts with
  `Completed` / `Cancelled` / `Faulted`. Sleep a short flush grace
  (~0.5 s) before reading results — the search's own `responseCount`
  can exceed what the API has exposed yet.
- Results: `GET /api/v0/searches/{id}/responses`. Use the SUB-ROUTE —
  the metadata route's `responses` array is empty once completed.
  Each response: `{username, hasFreeUploadSlot, uploadSpeed (B/s),
  queueLength, files: [{filename (remote, backslashes), size,
  extension, isLocked, bitDepth, sampleRate, length}]}`.
- Cleanup: `DELETE /api/v0/searches/{id}` ONLY on a terminal search.
  Deleting one still in flight throws `DbUpdateConcurrencyException`
  and poisons subsequent searches (they return 0 responses, which
  reads exactly like "not on Soulseek") — the fleet measured this; if
  your poll deadline expires first, leave the search to expire itself.
- Shared instance: fleet probes use the same slskd — one search per
  user action, no tight search loops; heavy concurrent searching
  degrades everyone's results.
- Your own client never appears in its own results — a "do we already
  have it" check must be local (filesystem/index), not a search.

## Aggregation

- Group files per `(username, directory)`; keep the REMOTE filename
  verbatim — it is what the enqueue needs (separators are backslashes).
- Rank: lossless (FLAC) first, peers with free slots first, then fuller
  sets, then higher speed. Flag LOCKED / NO SLOT items.

## Grab (enqueue)

- Pinned batch route: `POST /api/v0/transfers/downloads/batches/` with
  `{"username", "files": [{"filename", "size"}], "options":
  {"destination": "<slug>"}}` → `{"batch": {"transfers": [...]},
  "failures": [...]}`. Destination is relative to slskd's downloads
  dir; files land FLAT at `<downloads>/<destination>/<basename>`.
- Route-absent fallback: an EMPTY-bodied 404/405 means the batch route
  doesn't exist on this build — fall back to `POST
  /api/v0/transfers/downloads/{url-quoted-username}` with the bare
  `[{filename, size}]` list (no destination pinning). A non-empty 404
  is a real failure and should raise.
- v0.26 transfer objects never include `localFilename` — derive the
  local path from the pin, not from the remote tail.

## Progress

- `GET /api/v0/transfers/downloads` → `[{username, directories:
  [{directory, files: [...]}]}]`; flatten, then match enqueued items
  by `(username, remote filename)`. Done = state contains `Succeeded`;
  dead = `Errored`/`Rejected`/`Cancelled`; `percentComplete` is 0–100.
- The remote filename is the JOIN KEY everywhere — do not normalize
  separators differently between enqueue, matching, and status reads.
