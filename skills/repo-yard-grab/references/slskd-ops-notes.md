# slskd lane ops: enqueue, adopt, and what the organizer will (not) import

## Search display funnel (raw slskd -> lane -> aggregator)

A thin result list is usually the funnel, not the network. Audit before
blaming the UI: run the same query at each layer (raw slskd search API -> lane
`/search/json` -> aggregator `/search/json`) and compare row counts and
distinct (peer, dir) copies. One audit on a very popular album: 248 raw
responses (~282 candidate directories with 10+ files) -> lane 17 rows /
7 copies -> aggregator 6 rows / 2 copies. Three mechanisms ate the rest:

- The aggregator's cross-provider dedup keyed slskd rows on (title, artist).
  P2P rows are COPIES — the same track from two peers (or two dirs) is two
  acquisition choices — so the key must include (username, dir). Otherwise a
  seven-copy album lists as one, minus the rows that dedup kept.
- The generic per-tool cap (`MAX_RESULTS_PER_TOOL=10`) truncates rows BEFORE
  the UI can group them into copies; slskd needs its own budget (the lane's
  natural 30-row cap).
- Per-peer display rows are capped (`MAX_FILES_PER_USER=3`), so per-directory
  completeness must come from the peer's FULL match list: the lane client
  attaches `dir_stats` {dir: {files, lossless}} computed pre-trim and
  `dir_files`/`dir_lossless` prefer it. Computed from the trimmed rows, a
  25-file copy reports "3 files" and the incomplete-copy warning never fires.

Raw search API notes:
- `POST /api/v0/searches` body {"searchText", "id"} — the id MUST be a UUID;
  a label 400s with a .NET Guid conversion error.
- A popular query goes terminal in seconds as "Completed,
  ResponseLimitReached"; treat any state containing "Completed" as terminal.
- The lane sorts responses by file count before trimming, so the kept peers
  are the best-populated ones — only their counts were wrong, not the choice.

Audit recipes:
- Check the merged library FIRST: if the album is already present, a grab test
  only exercises the already_in_library skip — search-side funnel numbers are
  the meaningful output.
- Verify what a grab would actually pull with
  `client.search(query, only_user=<peer>)` filtered to the copy's directory: a
  "3 files" display row can belong to a directory holding the full edition.

## Enqueue paths

- Lane route (the UI path): `POST /download/enqueue {url, type}` with
  `url = slskd://<username>/<remote\path\file.flac>` and `type = album|track`;
  returns 202 `{job_id, job_ids, kind, status}`. Build the URL from a search
  row's `url` field — the standard shape works (`type=album` grabs the peer's
  whole directory). A hand-made URL shape that 500s with `malformed slskd url`
  is the exception, not the norm.

Album enqueue sanity checks (silent partial grabs happen here):
- Prefer complete copies at search time: rows carry per-copy completeness
  (`dir_files`/`dir_lossless`) and peer availability (`free_slot`,
  `queue_length`, `upload_speed`) — a copy with fewer lossless files than the
  album expects is refused by the MusicBrainz gate; skip it (the fleet web UI marks it
  `incomplete (x/y)`) instead of enqueueing and waiting for the quarantine.
- `len(job_ids)` must match the album's track count. A 1-3 job response for a
  full-length album means the sibling expansion was truncated. The lane's
  search caps files per peer for the DISPLAY only (`MAX_FILES_PER_USER`); the
  expansion must re-list the peer via `client.search(..., only_user=<peer>)`,
  which returns that peer's complete listing. Never route the expansion
  through the display cap — that bug sent partial 3-track sets down the
  pipeline until the organizer's MusicBrainz gate refused every one.
- Non-audio siblings (`.log`, `.cue`, `.lrc`) must not become jobs: they error
  on size mismatch, and ANY errored job wedges the group — a group finalizes
  only when every job has files and none errored, so one junk file silently
  silently blocks the whole album until the error clears. The lane's bounded
  auto-retry (attempts tracked as `retry_count`, retried on reconcile ticks, then
  terminal `failed`) drains transient transfer errors by itself; deterministic
  ones (junk siblings, a set the MB gate will refuse) still need cancel + fix +
  re-enqueue.
- Reliable path (raw slskd API, base `http://IPVPLACEHOLDER:5030`, header `X-API-Key` from
  `docker exec slskd-headless printenv SLSKD_API_KEY`):
  1. `POST /api/v0/searches {searchText, id}` (id = uuid4)
  2. poll `GET /api/v0/searches/{id}` until state starts with `Completed`
  3. `GET /api/v0/searches/{id}/responses`
  4. `POST /api/v0/transfers/downloads/{username}` with `[{filename, size}, ...]`
  - Never DELETE an in-flight search (DbUpdateConcurrencyException).

## Route testing / hit-rate runs

Exercise the lane route end-to-end and measure what Soulseek actually
delivers (the default-FLAC-fallback workstream).

- Candidate matrix: search the RAW API for scoring data the lane's
  `/search/json` strips (free upload slot, queue length, speed). Group each
  peer's files by parent directory, keep dirs at or above the album's typical
  track count, prefer free slot > queue 0 > speed. Pick the flac count that
  appears most often across peers — that is the release's own shape; a lone
  26-file dir for an 11-track album is a deluxe/box set, and deluxes are the
  ones most likely to miss the MusicBrainz match.
- Cross-check the modal count against MusicBrainz before enqueueing (release
  search + track count via /ws/2). A set only imports when MB HAS that
  edition: RAT WARS ULTRA EDITION (16 tr, MB 2024-10-17) imported fine,
  while a 16-file dir corresponding to no MB release quarantines. When MB
  shows only the standard count, target a peer whose dir matches it — do
  not reach for the biggest set.
- Enqueue the pick through the LANE route (`POST /download/enqueue` with
  `{url, type: album}`) so the exercised path is the one the UI uses; the raw
  API + adopt path is for repairs, not for route testing.
- slskd rate-limits search bursts: firing many concurrent
  `POST /api/v0/searches` returns HTTP errors part-way through. Throttle to
  ~2 concurrent with backoff-retry on 429/5xx, or run sequentially; each
  search needs its full window (~45-75 s) before responses are complete.
- Monitor while it runs, in this order: lane DB job states per group ->
  slskd `GET /api/v0/transfers/downloads` filtered to your peers -> staging
  dirs under `/storage/fleet/slskd/<group>/` -> organizer `/queue/status`
  and `audit.jsonl` -> the library itself. A completed lane job is NOT the
  finish line; verified landing = opus files in
  `/your-media-path/library/music-library/<Artist>/<Album>/`.

## slskd API surface (0.26, measured)

- Search POST accepts peer filters: `filterResponses`,
  `maximumPeerQueueLength`, `minimumPeerUploadSpeed` (HTTP 200). Our lane
  does not send them yet — candidate hygiene pass (defaults 0 = off).
- Batch download API exists: `POST /api/v0/transfers/downloads/batches/`
  (empty body → 400 payload validation = route present; GET → 404, write
  path only). The Lidarr plugin pins per-batch destinations
  `lidarr/<download id>/<Artist> - <Album>/` — destination pinning,
  a failure blocklist, and a pre-grab duration-fit badge are the adopt
  list in `docs/slskd-interaction-models-20260920.md` (repo).
- Search response object fields: fileCount, files, hasFreeUploadSlot,
  lockedFileCount, lockedFiles, queueLength, token, uploadSpeed, username
  (queueLength is per peer — a displayable availability signal).
- File object fields: bitRate (lossy), code, extension, filename, isLocked,
  length (SECONDS), sampleRate, bitDepth, size. `isLocked` and `length` are
  unused by us so far — locked files just churn retries, and `length`
  enables the duration-fit warning (the Lidarr plugin uses 5 s tolerance /
  0.8 match fraction / 0.8 coverage against MusicBrainz durations).
- Funnel audit numbers and the four display defects fixed: see
  `docs/p2p-search-audit-20260920.md` (repo).

## Silent-import failure signatures (organizer side)

Read the organizer `audit.jsonl` skip reason before re-running anything:

- `duplicate_source_in_batch` — the same source dir was enqueued TWICE (a
  finalize that ran twice: webhook thread + watchdog). The batch keeps the
  first manifest and skips the rest, so a double-finalize ends as "nothing
  imported" even though every lane job shows completed. One group must
  produce exactly one organizer manifest — guard the finalize path with a
  lock plus an early-return when `organizer_job_id` is already set.
- `already_in_library` — the identity check matched; the gap-check missed a
  normalized-name variant. Re-check with normalization before grabbing again.
- `all_files_no_metadata` or a gated quarantine — the staged set was junk
  (`.log`/`.cue` only) or the MusicBrainz match failed, typically a partial
  track set or a peer rip that matches no release. Fix the grab; do not
  retry the same source.
- `no_musicbrainz_match` WITH TWINS IN THE STAGED DIR — `X.flac` sitting next
  to `X_<18-digit-ticks>.flac` means the re-grab landed over a stale slskd
  download copy (slskd uniquifies colliding names). Both get staged, the
  album carries duplicate tracks, and the MB match fails wholesale — 4 of 5
  test albums quarantined this way (2026-09-20). Lane >= d70758e collapses
  twins at stage time (newest mtime wins); on older lanes, clear the stale
  copies under /storage/slskd/ before re-grabbing.

## Staging & cleanup

- `/storage/fleet/slskd/<group>/` is transient lane staging; slskd keeps
  its own download copies under `/storage/slskd/`. Both are purge-safe once
  EVERY job of the group is terminal (completed/error/cancelled) — check the
  lane DB first; deleting under an active group breaks the staging.
- Re-verify contents at purge time: raw sources may already be gone (moved or
  cleaned by another session's finalize/adopt) — confirm current state, do
  not trust an earlier listing.
- A group with ANY errored job does not finalize while the error stands.
  Transient transfer errors are auto-retried (bounded) and exhausted jobs end
  terminal `failed`; for deterministic causes (junk siblings, an incomplete
  set) cancel the group, fix the cause, then re-enqueue.

## Adopt direct enqueues into the lane (otherwise the lane ignores them)

The lane only tracks transfers in its own store; raw slskd enqueues are invisible to it
(no stray-job creation in `reconcile()`). After the transfers succeed:

```python
import sys; sys.path.insert(0, "/your-stacks-path/fleet/tools/slskd-headless")
from app import store
DB = "/storage/fleet/slskd/data/lane.db"
job = store.create_job(DB, group_id, username, remote_filename, size)
store.update_job(DB, job["id"], slskd_transfer_id=..., state="downloading")
```

then POST one webhook per file to `http://IPVPLACEHOLDER:19496/webhook/slskd`
(`Authorization: Bearer <lane HEADLESS_TOKEN>`):
`{"type": "DownloadFileComplete", "transfer": {"username": u, "filename": remote},
 "remoteFilename": remote, "localFilename": local}`. The lane stages to
`/storage/fleet/slskd/<group>/` and enqueues the organizer. Lane job summary:
`GET /download/jobs/summary` (lane's own HEADLESS_TOKEN).

## Album-grab candidate selection (search → pick)

- Probe with the raw slskd API for the candidate matrix, then enqueue through
  the LANE route (the UI path). Searches take 40-80 s; `Completed, TimedOut`
  and `ResponseLimitReached` states are normal. Fire at most ~2 concurrent
  searches — a burst of parallel POSTs fails; retry HTTP 429/5xx with backoff.
- Score candidates: parent dir matches the album tokens, `hasFreeUploadSlot`,
  `queueLength == 0`, then the MOST COMMON FLAC count across the candidate pool
  (the release's own track count), then upload speed. Prefer the modal track
  count over the largest — deluxe/instrumental editions make the MB gate
  harder.
- You enqueue ONE file URL; the lane expands siblings by re-searching the
  parent dir name. Inspect the expansion path when a grab comes up partial;
  the caller side needs no change.

## Reissue / scene copies - identification, parse traps, ranking

- **Scene-rip naming.** Reissue drops arrive as scene dirs under roots like
  `@@music\...` or `0day_MP3\...`, e.g.
  `Apoptygma_Berzerk-Kathys_Song_(Come_Lie_Next_To_Me)_XXV-Limited_Edition-VINYL-FLAC-2026-FWYH`
  and `Apoptygma_Berzerk-Kathys_Song_XXV-(OVRDRV031)-16BIT-WEB-FLAC-2025-DASH`,
  with aux siblings (jpg/m3u/nfo/sfv) that must be EXCLUDED from job lists -
  one junk job wedges the whole group (see enqueue checks above).
- **Parse traps (measured on this case).** The `extension` field can be EMPTY
  for whole peers' result sets (5 of the 6 users-with-files in one search;
  only SKYLiGHT_D reported extensions) - derive extensions from the FILENAME.
  Filenames are Windows-style (`@@share\dir\file.ext`) and may end
  `@<clientTag>` (`mp3@synoeastream`): normalize backslashes, strip '@'
  markers from the EXTENSION only.
- **Responses contain only matched files**, and which peers answer depends on
  the query shape - union every resp dump from the full ladder (see
  slskd-search-probing.md) before ranking. Flushing each dump to disk is what
  makes the union possible.
- **Ranking**: `scripts/slskd_rank.py` aggregates every `resp_*.json`, groups
  by (user, directory), classifies edition (WEB-FLAC / VINYL-FLAC / MP3 /
  legacy), checks completeness vs `--expect N`, and ranks lossless + free
  slot + short queue + speed. It emits a `SAFE PICK` (non-vinyl lossless)
  and an `ARCHIVAL ALTERNATE` (vinyl rip) with ready `slskd://` sample URLs.
- **MB gate on reissues.** MusicBrainz often has the digital edition but NOT
  the vinyl-only one (measured: MB has the 2025-12-22 digital 4-track
  `68a4db85`; no 2026 vinyl entry). A vinyl-rip import can quarantine at the
  gate - prefer the digital edition for auto-import; keep the 24/96 vinyl rip
  as the manual/archival alternate.

## Album enqueue 500: sibling expansion blackholed (diagnose, then repair)

- Signature: `POST /download/enqueue {url, kind: "album"}` -> HTTP 500,
  `ValueError: no sibling files and no size for '<file>' on '<peer>': slskd
  aborts a 0-byte expectation, so nothing was enqueued`. Retrying the same
  URL fails identically; the lane log carries the same ValueError.
- Mechanism: `_album_file_list` expands the album by searching the album
  folder name (`album_dir_query`) restricted to the seed peer. That query has
  the same shape sensitivity as any slskd search: it can return 0 responders
  while the release is plainly shared. Scene-style names are the worst case -
  single-token underscore-joined folders (`Artist-Album-XXV-Limited_Edition-
  VINYL-FLAC-GRP`); a peer that answered `Apoptygma Berzerk XXV` ignored both
  its own full scene folder name and `Kathy's Song XXV`. With no siblings and
  no `size` opt the lane refuses rather than grab a 0-byte set.
- Diagnose before blaming the peer: `GET /api/v0/searches` on raw slskd - find
  the lane's expansion queries (the fired folder-name strings). `responseCount:
  0` on all of them = blackhole, not absence. Confirm with a reduced raw shape
  (`<Artist> <anniv token>`) in parallel.
- Repair, in order:
  1. Raw per-file enqueue: `POST /api/v0/transfers/downloads/{username}` with
     `[{filename, size}, ...]` built from the saved search responses (HTTP 201
     with queued transfers; watch via `GET /api/v0/transfers/downloads/
     {username}` - nested user/directories/files). Raw enqueues are invisible
     to the lane: finish with the adopt recipe in "Adopt direct enqueues into
     the lane" or the organizer never sees them (the adopt webhook payload
     must carry `transfer.state` containing `Succeeded`; the route silently
     ignores payloads that do not).
  2. Passing `size` in the lane enqueue body only buys the single-file
     fallback (one seed track) - fine for track grabs, not for an album you
     intend to import whole.
- The UI-search escalation (`fallback_query`) drops the first WHITESPACE token
  only - it cannot reduce single-token scene names; whichever layer retries,
  shape the reduced query yourself.
- **Fixed in the lane 2026-10-01 (deployed `690d5aa`): `_album_file_list` now
  walks `normalize.expansion_query_ladder`** - full folder name, then first
  two `-`/`_` tokens, then first token - stopping at the first search that
  yields audio siblings of the seed's parent dir (max 3 searches, only after
  an empty result, so a healthy full-name hit stays one search). The 500
  signature above now requires EVERY ladder candidate to come back empty
  (peer offline, or a blackhole deeper than the artist token). Measured
  2026-09-30 on the Tyske Ludder vinyl rip: full 63-char folder name and every
  `-DE-Limited…`-onward prefix returned 0 responders network-wide, while
  `Tyske_Ludder` answered with the folder - the ladder grabs all 10/10 files.
  Not length: a 58-char `Mortiis-…-FWYH` folder answered in the same session.

## Shared-side accounting: slskd's upload bytes are NOT wire bytes

Measured 2026-10-01. slskd's transfer DB claimed 6.7 TB of uploads in a week
while the host NIC (vnstat, enp4s0 — the only uplink) showed 0.88 TB TX TOTAL
for every service that week. Live capture of one claimed 3.5 GB "upload"
(ruonll pulling the same movie every ~11 min for weeks): slskd records
`Completed, Succeeded` with `BytesTransferred == Size` after a fixed ~59-60 s —
and the uploads API already shows full bytes ~5 s in — while no interface moved
more than ~2 MB/s during the window (no ≥50 MB/5 s bucket anywhere; wg0 +
docker bridges covered). Class signature: avg duration 58-62 s, full-size
bytes, one (user, file) pair repeated hundreds of times (ruonll 796x one file,
chuy03 222x, alicejjackson 411x = ~93% of the claimed week volume). Reads as a
client that hangs up at ~60 s + a slskd progress/state race (see upstream
slskd PR #1457 on stuck/raced transfer progress). Consequences:
- NEVER quote slskd's upload totals as data usage — use vnstat/`/sys/class/net/*/statistics/tx_bytes`.
- The repeat-loop users do keep hammering (queue slots, log noise); blocking
  is a policy call, the DB rows alone are not evidence of bandwidth spent.
- `slskd.yml` retention: `upload.succeeded: null` keeps these rows forever
  (transfers.db was 387 MB); set a cap if the file growth matters.
- Evidence dumps from the finding: `/var/tmp/slskd-xfer-watch/`,
  `/var/tmp/slskd-uploads.json`.

## Route verification loop (what to watch, in order)

1. Lane store: read `/storage/fleet/slskd/data/lane.db` via
   `app.store.list_jobs` (import path `/your-stacks-path/fleet/tools/slskd-headless`)
   — jobs grouped by `group_id`, states queued → downloading → completed/error.
2. slskd transfers: `GET /api/v0/transfers/downloads` — per-peer state counts.
3. Staging: `/storage/fleet/slskd/<group>/` gains the files plus
   `.organizer-peers.json` (peer-declared durations for the organizer's
   pre-import sanity gate).
4. Organizer: `docker exec organizer sh -c 'tail /app/data/audit.jsonl'`, grep
   the lane job's `organizer_job_id`; queue counts via
   `GET http://IPVPLACEHOLDER:19298/queue/status` with
   `Authorization: Bearer $(docker exec organizer printenv ORGANIZER_TOKEN)`.
5. Library: the album lands under `/your-media-path/library/music-library/<Artist>/`
   as opus within minutes of a successful gated import.

Outcome `reason=` values when auditing a grab:

| reason | meaning |
|---|---|
| `already_in_library` | identity already present — compare with normalized names, not exact paths |
| `already_in_library_gated` | tree-dedupe SKIP on the gated path — NOTHING is imported; it can fire for an album whose files were never actually filed, so treat it as a claim, not a result |
| `gated_import_landed` | the landing proof fired — the beets DB census (target-name guarded) or the byte-size fallback. HEURISTIC: verify the album on disk / in the beets DB. A false positive marks DONE, deletes the staging and skips the quarantine path, so the album is silently lost (Stick - Heavy Bag, 2026-10-17 — one coincidental size match; fallback now demands a FULL-set match, the fleet c053e19) |
| `duplicate_source_in_batch` | the same source dir appeared twice in one batch — a group finalized twice (webhook + watchdog race); one manifest imports, the rest skip |
| `quarantined` / `all_files_no_metadata` | staging carried no usable tags — e.g. only `.log`/`.cue` junk was enqueued |
| gated quarantine (no reason field) | slskd imports are MusicBrainz-gated: a weak/no match quarantines and FAILS deterministically (no retry) |

Cleanup: lane staging dirs are safe to purge only when every job of the group
is `completed`; slskd's own completed downloads live under
`/storage/slskd/complete`.

Dispatch-response traps (measured 2026-10-17):

- An album dispatch answered `{"error":"unavailable"}` from the aggregator
  while the lane had in fact enqueued every track — treat it as a proxy
  timeout, not a dead peer: check the lane's own
  `/download/jobs/data` queue before re-dispatching (a duplicate batch doubles
  the work).
- One album dispatch = one lane job per track: the response's `job_ids` array
  length is the track count.
- Saved search-response dumps go STALE: re-reading a dump hours later yields
  `no audio files listed for this folder (peer offline, or the search window
  closed)`. That is an expired search window, not a vanished share — fire a
  fresh search before concluding the album is gone.

## Dev/test runs (slskd path)

- The lane's tests are `tools/slskd-headless/tests` (suite `slskd`, 59 tests), run via
  the monorepo gate `bash scripts/test.sh` or standalone from the repo root:
  `python3 -m pytest tools/slskd-headless/tests -q` (~1 s).
- They are hermetic and must stay that way: the `env` fixture pins
  `SLSKD_DOWNLOADS_DIR`, `SLSKD_STAGING_DIR`, `LANE_DB_PATH` to pytest `tmp_path`;
  `HEADLESS_TOKEN`, `SLSKD_URL` (http://slskd.test:5030), `SLSKD_API_KEY`,
  `ORGANIZER_URL`, `ORGANIZER_TOKEN` default to test stubs; `FakeSlskd` /
  `FakeOrganizer` provide the in-memory API surface; the watchdog interval is parked
  at 3600 s. A test run therefore never touches `IPVPLACEHOLDER:5030`,
  `/storage/slskd/complete`, or the lane DB.
- Live ops (grabs, repair, adoption) are the opposite - real slskd API and real paths
  (see above). Never point the tests at those, and never point ad-hoc scripts at the
  tmp-dir fixtures.

## Deploys that touch the lane

`deploy/deploy.sh organizer` (or any tool) pulls the monorepo and recreates only its
registry target. The slskd lane is a bind-mount container and is NOT a deploy target:
after a pull that touches `tools/slskd-headless/`, restart it yourself
(`docker restart slskd-headless`) and re-check `GET http://IPVPLACEHOLDER:19496/health`
(200) - otherwise the process keeps running the pre-pull code. The organizer is
recreated by `deploy.sh organizer`; health gate is `GET http://IPVPLACEHOLDER:19298/ready`.

## Sources that can never import through the lane (do not re-dispatch)

Two shapes look like a successful grab but can never land — recognise them at
SEARCH time and report them as manual work instead of dispatching:

- **Whole-CD-single-file shares.** Some releases (measured: Anal Cunt
  *110 Song CD*, 110 tracks / ~21 min) circulate on Soulseek ONLY as one giant
  `<n> - <Album>.flac` (170 MB, `length` ~1285 s). The lane enqueues 1 job, the
  transfer completes, and the organizer quarantines it (`/storage/__Junked/
  music/<Artist>/<Album>/`) as a 1-track unknown — every peer has the same
  shape, so re-dispatching another peer repeats the quarantine. Only a
  local split (cue/silence) against the MB tracklist lands it; that is manual
  work, not a lane grab.
- **Early self-releases whose songs reappear on a later album.** Measured:
  Andy Shauf *Grandpa Songs* (2007 CD-R, 8 MP3 tracks, one peer) — the same
  songs also sit on *Darker Days* (2011), which the library already holds. The
  organizer's import-time dedupe drops them: the job ends `DONE` and NO folder
  appears for the early title. Re-dispatching is a no-op; the title can only
  exist via a forced/manual beets import with an album override.

- Classical/Soulseek rule: performer-ripped classical folders circulate as
ensemble/soloist/recital folders with inconsistent tags. The slskd lane is
an untrusted source, so the organizer imports it through the gated beets
config, which requires a MusicBrainz release match. These folders do not
resolve to release groups, so every import fails with
no_musicbrainz_match. No retry — re-dispatching another peer repeats the
quarantine. Recognize this at search time: the folder path lacks a composer
name or the artist field is a performer/ensemble, not the release artist.
Fill classical from a provider lane naming the recording (Glenn Gould -
Goldberg Variations), not the loose P2P path.

Before dispatching an obscure title, confirm the album is not already covered
by a differently-named release: compare its tracklist against the artist's
library folders (find /storage/library/music-library/<Artist> -iname
'*<track>*' ).

## What the organizer does with a re-grab

- Tracks/albums already in the library are skipped: job ends DONE, audit shows
  `reason: library`, staged dir cleaned. Use `/library/check` semantics as the hint -
  a re-download of existing library content will not import.
- Fresh downloads remain in `/storage/slskd/complete`; the lane copies/moves from there.
- A FAILED organizer job with `error` = the staged source path means the staging dir was
  gone by processing time (re-stage or enqueue a fresh source).
