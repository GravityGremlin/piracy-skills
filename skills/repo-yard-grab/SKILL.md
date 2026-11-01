---
name: repo-yard-grab
description: "Use when grabbing music (albums, discographies, tracks, playlists) via the downloader fleet on your host — resolve, dispatch, and watch downloads through the beets organizer into the Navidrome library, and hardlink them to /your-media-path/exports. Also covers fleet queue status, stuck-job cleanup, playlist import workflow, Tidal entitlement/quality, and hunting fresh scene releases."
version: 1.4.0
author: Gravis Wellz
license: MIT
tags: [music, downloader-fleet, download, beets]
metadata:
  hermes:
    tags: [music, downloader-fleet, download, beets]
---

# Repo Yard Grab

Grab albums/discographies/tracks through the downloader fleet's headless lanes on
your host (IPVPLACEHOLDER). Downloads auto-stage into the organizer's beets import
and land in the Navidrome library — no manual beets, ever.

## A slskd abort at `expected size 0` is a shape bug, not a peer

When a transfer dies with `the remote size of N does not match expected size 0`,
the peer is fine — the dispatch carried no size, so the abort reproduces against
every username in the results. Do not walk the result list peer by peer, and do
not sleep-and-poll the job: it sits in `running` and never moves a byte. Change
the dispatch SHAPE once (direct slskd enqueue with the real size, or
`kind=album` from a seed file) and re-dispatch. Bound every watch to two
progress checks minutes apart. Recipe and full triage: `references/slskd-dispatch.md`.

## Bulk runs and same-name artists

Many artists in one request, or an ambiguous one-word name: see
`references/bulk-discography-runs.md` for the resolve → fingerprint-probe →
dispatch → curate → verify sequence.

## One gated item never parks the rest of the batch

Every batch run eventually hits a row you cannot clear yourself — a delete under
`/your-media-path`, anything behind a standing approval gate. State that one blocked row
in a single line and finish everything ungated in the same turn: the re-dispatch,
the verification, the commits, the downstream consumers. Announcing "I'm waiting
on you" for a batch whose only blocked item is one delete reads as idling and is
the wrong shape; keep the batch moving and leave one explicit question behind.

## A FAILED job is not proof the audio is missing

`post-import verification failed: staged audio did not land (no size or DB-census
match)` usually means the album DID land. Beets re-tags the artist credit
(featured artists: target `Dope D.O.D` lands as `Dope D.O.D., Onyx`) or
normalises the title, so the verifier's identity match misses it and the job
burns all four retries to FAILED. Grep the library by album title before
re-enqueuing — re-running the same job only re-burns retries.

## Discography pitfalls — confirm before you trust a run

1. Artist search caps at ~10 popularity-ranked hits — an established band can be invisible to it. Fall back to album-level dispatch by URL instead of forcing candidate #1 (`references/bulk-discography-runs.md`).
2. `cancel` is group-scoped: cancel all rejects and verify each cancel landed before dispatching any recovery job into the same group, or the new job dies with the rejects (`references/bulk-discography-runs.md`).
3. Splits land under partner dirs and comps can slip title-keyword curation — check both before reporting a gap or declaring a run complete (`references/discography-grabs.md`).
4. Lane `error: "Not connected to Tidal"` jobs never download — after every run, scan the lane's `jobs.db` for errored/failed jobs in recently completed groups (the library holds nothing to match). Re-dispatch the whole group once `rygrab.py --status` reports `auth=ok` (`references/discography-dispatch.md`).
5. A `completed` job with `dir=null` means audio is still sitting in the lane's download dir (`/app/downloads/<Artist> - <Album>*` inside `tidal-headless`) and was never handed to the organizer. Landing is file-based: `ls "/storage/library/music-library/<Artist>"` plus per-dir `.opus` counts, stable across two polls. If a completed album is absent from the library, glob `/app/downloads` for the artist name and re-import or re-dispatch the orphan (`references/discography-dispatch.md`).
6. Merged Tidal pages — if an artist dir holds titles that do not match the band's known catalogue (e.g. Rush albums under Strife), trim to the right tracks or resolve by URL instead of the artist page (`references/discography-dispatch.md`).
7. Probe groups bypass curation — every dispatched group (probe or not) must pass the full curation pass (drop non-studio, drop owned, collapse edition duplicates) before the run is complete (`references/bulk-discography-runs.md`).
8. Collab/family albums organize under combined artist dirs — Trio lands under "Dolly Parton, Linda Ronstadt & Emmylou Harris", not under any solo artist. Check combined dirs before declaring a solo gap missing (`references/bulk-discography-runs.md`).
9. Compare kept groups against planned artists and report misses explicitly — a silent short batch looks like success in the log (`references/bulk-discography-runs.md`).

Same class: `staging empty: no audio files found` when the album was already
imported as loose singletons at the artist root, so `import_staging` holds only
`cover.jpg`. Check the artist directory before treating it as data loss.

## The MB gate matches the RELEASE title, not the release-group title

`no_musicbrainz_match` on an slskd grab means the `title` you sent the lane
did not match the MusicBrainz RELEASE title. The gate resolves a RELEASE, and
a release-group title can differ from the release title (release-group
"Twilight of the Idols: In Conspiracy With Satan" vs release "Live Bergen
1996").

Symptom that looks like data loss but is NOT: the FAILED manifest names
`target_album` as YOUR title, while the library dir holds a DIFFERENT,
MB-corrected title — beets renamed it after the MB release lookup. Verified
2026-10-22: sent "Bergen 1996", got `no_musicbrainz_match`, yet
`/storage/library/music-library/Gorgoroth/Live Bergen 1996/` held both opus
files with `album=Live Bergen 1996`, `releasetype=ep;live`, `date=2008-01-08`
and the right `musicbrainz_albumartistid`.

Read the manifest BEFORE re-grabbing:
    docker exec organizer sh -c "grep -l -i <artist> /app/data/queue/FAILED/*.json"
    docker exec organizer sh -c "cat /app/data/queue/FAILED/<id>.json"
then compare `target_album` with the library dir name. If the LIBRARY has the
release under an MB-corrected name, the grab succeeded and only the manifest
is stale. Only re-grab when the library has NOTHING for that release.

To avoid the mismatch, send the MB RELEASE title (query
`/ws/2/release/<id>?fmt=json&inc=recordings+media` and use `title`), not the
release-group title.

## Peer "Verification required" is peer-side — re-grab from another peer

slskd rejects the transfer with `TransferRejectedException: Verification
required` when the remote user demands a password-protected share. All files
of that album fail together; the lane auto-retries twice before FAILED.

Fix: cancel the group's jobs (`POST /download/jobs/<id>/cancel` per job id
from `/download/jobs/data`), then re-dispatch the SAME album with
`kind=album` and a seed file from a DIFFERENT peer. Verified 2026-10-22:
Incipit Satan from peer `thisisphyne` was rejected 8/8; the same album from
`TarryLoaf` landed all 8 FLAC files.

## A lane discography dispatch is not the artist's discography

Provider catalogs are thin. Gorgoroth on Tidal resolves to 7 albums; the
artist has 10 official studio records. Always cross-check the lane's set
against MusicBrainz release-groups for the artist
(`/ws/2/release-group?artist=<mbid>&fmt=json`), then fetch the missing
official releases from slskd as lossless FLAC. MusicBrainz is the authority
for "which releases exist"; the lane is only a source of bytes.

MB API notes: the `release` endpoint needs `inc=recordings+media` to expose
tracklists; a release id alone 404s. Use `release-group` for the release list
and `release-group/<id>?inc=releases` for editions. Rate-limit ~1 req/sec,
503 on bursts.

## Count queue depth with find, never ls

`ls /app/data/queue/READY/*.json | wc -l` inside nested quoting
(`ssh host 'docker exec organizer sh -c "..."'`) silently returns 0 — a queue of
300 looks idle and you go chasing ghosts. Use:

```
docker exec organizer sh -c "for s in READY PROCESSING DONE FAILED; do printf '%s=' $s; \
  find /app/data/queue/$s -maxdepth 1 -name '*.json' -printf '.' | wc -c; done"
```

A scheduler that goes silent with jobs parked in READY is usually a long
maintenance/convert pass, not a dead thread: check `docker stats` and for
`beet`/`ffmpeg` children before restarting anything. The organizer needs ~2 GB
for a 20-album beets batch (cap 4G/4CPU); at the old 1G it OOMs.

Retire dead queue entries by **moving** them: `mkdir -p FAILED.retired-$(date -u
+%Y%m%d-%H%M%S) && mv FAILED/*.json <that dir>/` — never `rm`, and only after
checking each `source_path` against what was since re-imported.

## "Any pending or failed items?" — enumerate before re-dispatching

Never answer from the last job you looked at. Three stores hold state and all
three must be read:

```
# lane jobs — SQLite, jobs stored as a JSON blob in the `data` column
# (there is NO status/artist/title column; querying them errors)
docker exec tidal-headless python -c "
import sqlite3,json,collections
c=sqlite3.connect('/app/data/jobs.db')
rows=[json.loads(r[0]) for r in c.execute('select data from jobs')]
print(len(rows), collections.Counter(r.get('status') for r in rows))
for r in rows:
    if r.get('status') not in ('completed','cancelled'):
        print(r['id'], r['status'], r.get('artist'), '-', r.get('title'), '|', (r.get('error') or '')[:80])"

# organizer queue — one JSON per job; aggregate by date and by error text
# (467 individual files is unreadable one at a time)
docker exec organizer python3 -c "
import json,glob,collections
c=collections.Counter(); e=collections.Counter()
for f in glob.glob('/app/data/queue/FAILED/*.json'):
    d=json.load(open(f)); c[(d.get('updated_at') or '')[:10]]+=1; e[(d.get('error') or '')[:60]]+=1
print(sorted(c.items())[-10:]); print(e.most_common(6))"

# queue depth right now
ls /your-stacks-path/fleet/... ; docker exec organizer sh -c 'ls /app/data/queue/READY | wc -l'
```

Rule of thumb when reading the numbers: a large burst of FAILED entries all
carrying ONE source path prefix means a staging-root/mount drift, not N broken
albums — fix the root, then re-enqueue (see `references/organizer-staging-roots.md`).
Old lossy-gate errors (`requested LOSSLESS but Tidal delivered ...`) are
delivery-quality records, not transport failures; do not "fix" them by
loosening the gate.

## Lane API quick contract (headless, bearer-guarded)

- Blueprints are PREFIXED: enqueue is `POST /download/enqueue`, not `/enqueue`.
  A bare `/enqueue` returns `{"error":"Not found"}` and looks like a missing
  route rather than a wrong path.
- Enqueue takes `url`, not an album/track id — build
  `https://tidal.com/browse/album/<id>` from the search result. Minimum body:
  `{"url":..., "type":"album|track|playlist", "title":..., "artist":...}`.
- `proxy_index: -1` (or any out-of-range value) means auto-rotate; `0` pins
  direct egress. Omitting it defaults to `0`.
- There is no `GET /jobs/<id>`; read status from `GET /download/jobs/data`
  (and `GET /download/jobs/summary` for per-artist rollups).
- Auth is the fleet `HEADLESS_TOKEN`; grab it from the tool's gitignored `.env`
  or the container env, never from a repo file.
- Proxy/credential lists follow the same rule: the repo yaml carries only the
  credential-free default, the authenticated list goes in the gitignored
  `tools/<tool>/.env` as `PROXY_LIST` (a JSON array — `config_base` parses it).
  Prove one live request through each proxy BEFORE committing rotation code;
  an unauthenticated entry fails as `407` and masquerades as a token problem.

> **This is the user-facing entry point** for grabbing music through the
> the downloader fleet. For deep audit, hardening, deploy topology, and E2E test
> runs, see the `music-downloader-fleet-pipeline` skill. For playlist import
> workflow, failure modes, and diagnostics, see
> `references/playlist-import-workflow.md`. When a lane's grabs transfer but
> never import (organizer enqueue 422 "source_path escapes staging/queue root"),
> see `references/organizer-staging-roots.md` (also covers
> `post-import verification failed: staged audio did not land` / silent beets
> skips, and bulk re-import of an orphan staging tree).
> For Tidal `abuse_detected` (an IP flag, not an account problem), your proxy
> inventory/auth, lane rotation and the 407 → "Not connected to Tidal"
> symptom, see `references/tidal-egress-and-proxy.md`.

## Throughput model: track-granular fills pace at ~2-2.5 items/min

Measured live: a single-track job runs its own full beets import (the "singleton"
path), which paces the whole fleet at ~26 s/item (~2.3/min) — the Tidal fetch
itself is ~3 s. Each lane job also holds its worker up to ORGANIZER_VERDICT_TIMEOUT
(180 s) waiting for the organizer verdict, so worker occupancy ≈ 183 s and the lane
ceiling is workers × 60/183 (7 workers → 2.3/min). Consequences: adding lane
workers does NOT raise the net rate (the levers are organizer-side: per-item import
cost and verdict latency); tracks fetched as ALBUM batches run much faster per track
(one beet run per group of albums vs one per track); rough ETA for a track-level
backlog = jobs ÷ 2.3 minutes.

Measure before promising speed: pair `claimed`→`done` lines by job_id in the
organizer audit log (container `organizer`, `/app/data/audit.jsonl`) for per-item
time; use the lane's `/download/jobs/summary` for per-group aggregates (the
`/jobs/data` list is only the newest 500 rows — a rotating window). Knobs that exist
but do NOT move the net rate alone: ORGANIZER_POLL_INTERVAL,
ORGANIZER_CONVERT_WORKERS, ORGANIZER_VERDICT_TIMEOUT. The identified real levers
(autotag off on the singleton config; cheap DB-census landing proof before the
whole-library size crawl) are planned in the knowledge repo
plans/fleet-throughput-2026-10-13.md.

Before planning an organizer change, confirm which copy is live:
`docker inspect organizer` shows the beets configs bind-mounted read-only from the
deploy checkout (`/your-stacks-path/fleet/organizer/…`) — a config edit applies on the
next import; a code edit needs the deploy restart.

**Sizing:** the organizer is the fleet's only library writer and batches ~20
albums per beets run, holding the batch in memory. Keep it at 4 GB / 4 CPUs
(`docker update --memory 4g --memory-swap 4g --cpus 4 organizer` applies live
without dropping the in-flight batch; persist in `compose.prod.yaml`
`deploy.resources.limits`). At 1 GB a bulk re-import OOM-kills and the queue
stalls at `PROCESSING` with no log output.

## Discography dispatch: the skip-if-known filter is BROKEN on year-suffixed dirs

Measured 2026-10-13: dispatching 9 artist discographies queued **105 albums**
when only 38 were genuinely missing — 67 were re-downloads of albums already
held. Two distinct defects in `tools/tidal/app/download/routes.py`:

1. **`_normalize_title` (discography.py:27) only lowercases.** The library
   names dirs with a year suffix — `A Moon Shaped Pool (2016)`, `Pablo Honey
   (1993)`, `Boxer (2007)` — so the organizer's `albums` list returns
   `"a moon shaped pool (2016)"` while Tidal returns `"A Moon Shaped Pool"`.
   The `_norm(album.title) in owned` check at routes.py:204 therefore MISSES
   and the album is re-queued. Fix: strip trailing `(YYYY)` / `- YYYY` before
   comparing.
2. **No edition-variant dedup across the owned check.** Tidal serves many
   editions of one album (`To Lose My Life...`, `(Bonus Track Version)`,
   `(10th Anniversary Edition)`, `(Bonus remix version)`), and each becomes its
   own job. Collapse to a canonical key (strip parentheticals, punctuation,
   and `deluxe|remaster|expanded|edition|version|bonus`) and keep ONE.

**Always audit a discography dispatch before letting it run.** Procedure that
worked: read the queued jobs' `group_id`, list their titles, and compare
against `os.scandir(library/<artist>)` with a year/edition-stripping
normalizer. Cancel the excess via `POST /download/jobs/<id>/cancel` (needs the
per-service bearer from `path-to-credentials` key `TOOL_HEADLESS_TOKENS`,
JSON — the plain `HEADLESS_TOKEN` in your credential store is NOT the lane token).
Also drop non-studio items by title regex (live, remix, b-sides, compilation,
original score, full concert) — Tidal's album feed includes them.

**Partial-held albums are a deliberate exception.** A held dir with <8 tracks
(e.g. `CHVRCHES/The Bones of What You Believe` = 2 tracks) SHOULD be
re-downloaded — it is a fragment, not a complete copy. Only skip when the held
copy is substantial (~8+ tracks). Do not blanket-cancel every name match.

## Do NOT hand-roll a discography: dispatch, audit, cancel

A user asking for "the discography of X" is a `rygrab.py --artist "X" --platforms tidal`
job (or `POST /download/discography {"artist_id": …}`), never a custom script that
enumerates Tidal albums and POSTs `/download/enqueue` per album. The lane's own
resolver already applies the fleet edition policy (explicit preference → most
tracks → most recent) and builds one shared group_id per dispatch.

Build the album list yourself only to AUDIT and to classify what the endpoint
cannot express — never as the dispatch mechanism. The known-bad behaviour that
makes people reach for a custom loop (year-suffixed dirs, duplicate editions,
singles the endpoint skips) is handled by dispatch-then-cancel: read the queued
jobs, cancel the excess with `POST /download/jobs/<id>/cancel`, and use
`include_singles=1` on `/download/discography` when the ask is literally "full".

Pitfall that cost a rewrite: `POST /download/discography` resolves an artist by
search, and short/common names collide (e.g. "Peaches" also matches a Swedish
kids band and Peaches & Herb). Confirm the resolved artist id against the one
you resolved independently before trusting the dispatch.

**An artist-wide dispatch without `include_singles=1` silently drops every
single.** The lane resolves `ALBUMS` and `EPSANDSINGLES` as separate Tidal
filters and skips the singles filter unless asked. A "the discography of X"
dispatch that omitted the flag came back complete and 8-albums-big while two
Official singles ("More", 1992; "Lucretia My Reflection") were still absent
from the library. Cross-check the lane's own result against the *union* of
both Tidal filters — the album filter alone (20 entries) hides the singles
filter (26 entries) — and dispatch the gap by album id
(`service=tidal&kind=album&url=https://tidal.com/browse/album/<id>`).
Do not conclude "nothing else is missing" from one filter.

**Tidal's `artists/{id}/albums` returns ALBUMS ONLY unless you pass
`filter=`.** No `filter` param = albums only; the singles and EPs need
`filter=EPSANDSINGLES`, and the items that come back carry `type` of
`SINGLE` or `EP` — not the filter's name. Measured on 21 artists: no
filter returned 616 releases, both filters returned 1,836 (616 ALBUM +
1,108 SINGLE + 112 EP). The same applies to the lane's own
`/download/discography` resolver — it calls `get_albums()` with no filter,
so it can never fetch a single or an EP; those need a per-album
`POST /download` with `kind=album` and a `tidal.com/browse/album/<id>`
URL (or a `slskd://` seed for Soulseek).

**A per-artist held-check, never a global one.** A global "is this title
already in the library?" index makes a release look held because some
OTHER artist has an album with the same name (G-Eazy "The Vault" vs an
unrelated "Vault"). Index album dirs per artist and compare within the
artist.

**Title matching that will not import the wrong release.** Normalise by
folding accents and case, strip parentheticals, and drop edition words
(deluxe, remastered, expanded…) — but never drop them ALL: "Mark Ronson -
Version" normalises to the empty string that way, and an empty key
matches every title. Match on prefix, not set containment: containment
made the one-word title "Live" match "Got Live If You Want It!" and pull
in a live album. Read live markers from the title WITH its parentheticals
— "(Live)" is invisible once the brackets are stripped, and a live
edition will otherwise win the pick because it has more tracks. Finally,
a MusicBrainz release-group's track count is not a gate: the group
aggregates several releases, so a 4-track EP on Soulseek can sit in an
8-track group.

**Library artist-dir case splits are usually provenance-driven.** Tidal spells
an artist "The Sisters Of Mercy" and MusicBrainz spells the same artist "The
Sisters of Mercy", so imports land in two different directories depending on
which source matched — and beets then carries two artist rows. Check the
artist-name spelling on the source that produced each import before treating
a case split as a mistake. When merging, the collisions are often *different
masters of one recording* (same track names, different bytes/mix labels) and
need a per-album keeper decision, not a de-dup sweep.

**A merge is not permanent and it is not finished until imports are
normalised.** The library path is composed from the `albumartist` TAG
(`paths.default: $albumartist/$album/...`), and the provider lane imports ASIS
with no musicbrainz plugin — so merging dirs and rewriting tags fixes the
library today, and the very next provider grab re-creates the second dir.
After any merge, install the import-time normaliser: `the beets import pipeline` →
`references/beets-import-plugin.md` (beets import stage; the obvious event
hooks do not fire for ASIS imports). Two merge-script traps: write beets rows
with **library-relative** paths (absolute paths silently break every row you
touch), and pick the canonical spelling per ARTIST, not per directory — the
MB-matched and Tidal-matched albums of one artist can be split across both
dirs, so neither dir is uniformly "the keeper".

## Monitoring a lane queue: `/jobs/data` is capped at 500 rotating rows

`GET /download/jobs/data?limit=N` returns at most 500 rows regardless of `limit`;
the window rotates as new jobs arrive. With a deep queue the jobs you care about
fall outside the window and a poller reads **"drained"** while hundreds are
still queued.

- Use `GET /download/jobs/summary` for per-group aggregates
  (`queued`/`running`/`completed`/`error` per `group_id`) — it is not row-capped
  and is the correct endpoint for "is my batch done yet".
- To find a specific job's queue position, read the lane's persisted
  `queue_order.json` inside the container (`/app/downloads/data/queue_order.json`
  on Tidal) — index 0 is the front.
- **Queue order is enqueue order (LIFO), not priority.** `_worker_loop` does
  `pop(0)`; a job's `priority` field is advisory only. Discography batches
  (priority 2) wait behind any later-enqueued priority-1 track jobs.
  `priority/up` swaps one slot per call, so it cannot shortcut a deep backlog —
  measure the backlog depth before promising a reprioritize.
- Jobs enqueued **direct** to a lane's `/download/enqueue` (bulk redownload
  scripts, bypassing the aggregator) never appear in the aggregator's dispatch
  ledger at `/app/data/dispatch/ledger.jsonl`. An empty ledger with a full lane
  queue is expected for direct-lane traffic, not a bug.

## Export to /your-media-path/exports (hardlink mirror)

For a grab-and-go copy that never touches the library and costs zero extra
space, hardlink an artist's albums into `/your-media-path/exports/<Artist>/<Album>/`.
`/your-media-path` is a symlink to `/storage` (same btrfs, dev 60), so hardlinks work;
deleting an export never affects the library.

- Bundled script: `scripts/export-artists.py` — idempotent and re-runnable:
  existing links are left alone, only new files are linked. Takes `--dry-run`
  and an optional artist subset. Re-run after any download batch lands.
- Verify with inode comparison (`os.stat(src).st_ino == os.stat(dst).st_ino`)
  — same inode confirms a true hardlink, not a copy.
- Bundled watcher: `scripts/wait-and-export.py` — bounded poller that waits for
  a discography set to drain (via `/jobs/summary`), then runs the export.

## Jumping a deep lane queue (cancel + re-enqueue, verified 2026-10-13)

The Tidal queue is **LIFO and enqueue-ordered, NOT priority-ordered**:
`runtime.py` `_worker_loop` does `_queued_order.pop(0)` and `enqueue()` does
`insert(0, ...)`. The `priority` field is advisory only — a priority-2
discography batch sits behind 500 priority-1 track jobs regardless.

**To move existing jobs to the front** (e.g. a bulk track re-download is
starving an album dispatch): cancel each job, then re-enqueue it — the fresh
enqueue lands at index 0. 48 API calls beats ~570 one-slot `priority/up`
calls. Recipe:

1. Find the queued jobs in the lane's sqlite: the fields live in the `data`
   JSON blob, not columns —
   `docker exec tidal-headless python3 -c "...select id,data from jobs..."`,
   parse each blob, filter `status=='queued' and group_id in <yours>`.
2. `POST /download/jobs/<id>/cancel` for each (cancelling only *sets an
   event*; the job leaves the queue when a worker reaches it — so you MUST
   re-enqueue, not just cancel).
3. `POST /download/enqueue` with `{url, type:album, title, artist}` —
   re-enqueue in REVERSE order so the first album ends up first.
4. Verify against `/app/downloads/data/queue_order.json` (index 0 = front).

**Caveat: a re-enqueued job loses its `group_id`**, so `/download/jobs/summary`
no longer shows it under the discography group. Track the re-enqueued job ids
yourself and match on title instead.

**Read the lane with `/download/jobs/summary` for aggregates, and remember
`/download/jobs/data` returns only the newest 500 rows** — a rotating window
that will silently omit deep-queue jobs (this produced a false "queue
drained" report). For per-job detail beyond 500 rows, read `jobs.db`
directly or use `?limit=N` (which caps at 500 on the default endpoint).

**The lane bearer is `path-to-credentials` key `TOOL_HEADLESS_TOKENS`**
(a JSON object, per-service). The plain `HEADLESS_TOKEN` in your credential store
returns `{"error":"Unauthorized"}` against the lane.

**Discographies can arrive SHORT** (Tidal throttling silently drops tracks).
After any discography dispatch, verify per-album opus counts against the
lane job's `data.source_quality.lossless_tracks`. Canonical lane status and
discography verification references: `music-downloader-fleet-pipeline` skill.

**A "short" album is not automatically a hole to fill** — test whether it is a
box set/compilation first (map its tracks against the other album dirs of the
same artist). Keeper-selection and compilation triage:
`references/library-dedupe.md`.

**Tidal FLAC entitlement is per-client, not per-account.** Tidal serves
different quality caps depending on which OAuth client pair authenticates.
tidalapi's built-in pair gets AAC 320 for everything without a hi-res master.
The "flac" pair (streamrip PR #1017, public credential) gets FLAC 16/44.1
catalogue-wide. Re-authenticate with:
`docker exec -it tidal-headless python /app/app/tidal/device_login.py`
(approve at link.tidal.com within 5 min). The token file records which pair
issued it (`client` marker) and `_create_session()` re-applies it on every
load/refresh. If a token refreshes under the wrong pair, it silently reverts
to AAC 320.

**Tidal lossy policy** ships `accept` — EAC3-only tracks download as lossy
instead of failing the whole job. FLAC is still requested first; lossy is the
last resort, loudly logged and recorded on `data.source_quality`.

**`abuse_detected: User account is suspended due to abuse` is an IP flag, not an account suspension.** The account stays active; Tidal throttled the egress IP. Do NOT treat it as auth expiry or trigger a re-login. Fix: route the lane through a different proxy — your proxy host's Mullvad fleet (`prx1–your-domain.example`, ports 16681–16695, rotated 00:00/12:00 UTC), added to `tidal.yaml` `proxy_list` and selected via `proxy_index` on the job. ntfy repo-alerts should classify this as "IP-flagged, retry via proxy", not "auth failed".

**Auto-rotation (2026-10-19):** Tidal now round-robins across `proxy_list` automatically when a job carries a sentinel `proxy_index` (-1 / None / out-of-range), so no manual proxy selection is needed for `abuse_detected` recovery — just re-enqueue (or leave proxy_index unset) and the lane rotates egress. Explicit `proxy_index` values are still honoured.

**Import-failure alerts** go to the dedicated `repo-alerts` ntfy topic
(https://your-domain.example/repo-alerts), NOT `cluster-alerts`. Every alert must
state WHY the import failed — no generic 'import failed' messages. triage:
`references/library-dedupe.md`.

## Playlist imports

Playlists go through a different path than albums/tracks. The full workflow,
failure-mode table, and diagnostic commands are in
`references/playlist-import-workflow.md`. Key points:

- Playlist dispatch now works through the fleet web UI (kind=playlist accepted by /dispatch).
- Multi-album playlists split into per-album organizer jobs (no more compilation-album failures).
- The playlist mirror searches the whole library for tracks, not just the target dir.
- Empty staging after import is `staging_consumed`, NOT `all_quarantined` — the engine
  checks if the import landed before marking DONE.
- Lossy policy is `accept` — EAC3-only tracks don't kill the whole playlist.

**User preferences for imports:**
- Import failures must ALWAYS state the specific reason (no generic "import failed").
- Quarantine is NOT delete — files stay until reviewed; only cleanup after confirmed import.
- Don't re-download if already in library (duplicate detection must work).
- Use subagents for parallel batch work (e.g., re-downloading missing tracks).

Curation + maintenance — m3u8 create/rebuild, backfilling missing tracks from a
batch search, linking library tracks into a playlist folder, recommendation
research, and batch-building ranked playlists from researched track lists
(presence-check → dedupe → paced dispatch → hardlink → m3u8 → monitor loop):
`references/playlist-curation.md`.

## ntfy alert channels

| Channel | URL | Purpose |
|---|---|---|
| `repo-alerts` | `https://your-domain.example/repo-alerts` | Download-queue alerts |
| `fleet-imports` | `https://your-domain.example/fleet-imports` | Import failures |

Fleet alerts must NOT go to `cluster-alerts` (that's for cluster infrastructure).

## General

- CI: the Forgejo runner for the fleet runs on your host at `/your-stacks-path/act-runner`
  (label `docker`, image `fleet-ci:3.12`). Forgejo 16 has no rerun API —
  trigger a workflow by pushing/opening a PR, not by re-running.

- **Library-scale gap-fill is CATALOG-FIRST.** Build and verify the list, then
sign-off, before dispatching any downloads — the volume is large and a false gap
burns real bandwidth. Gap cataloging method, the compilation-fragment inflation
trap, and the incidental-artist filter: `references/library-dedupe.md`.

Artist-dir merges (article/case variants, same-act verification, collision
triage) and the planner script are in the same reference:
`references/library-dedupe.md`, `scripts/artist-merge-plan.py`. Manual beets
repair (splitting a release out of a compilation, forcing a skipped import,
re-fetching a corrupt track) is scoped in `references/manual-beets-import.md` —
normal grabs never need it.

**Active lanes: Tidal + slskd.** (Spotify decommissioned; Qobuz +
Deezer sidelined — donor accounts dead/free. Canonical lane status:
`music-downloader-fleet-pipeline` skill.) A peer's "FLAC" may be a lossy
re-wrap — check its ancestry with `scripts/spectral_cutoff.py` (same-run
128k/fake-chain calibration; context in `references/lossless-sourcing.md`).

**slskd transfer reliability — two failure classes, never conflate them:**

- `Transfer rejected: File not shared.` — PEER side: advertised but not
  shared. Retry other peers (the same dir is often hosted elsewhere, and a
  peer that rejected once can succeed later).
- A timeout or error unavailable from the aggregator slash download does NOT mean the lane failed — the lane can still enqueue while the aggregator hits its transport timeout (raised to 120s in compose/env). Verify landings by lane job rows download slash jobs slash data or by globbing the artist's album dirs, not by the aggregator's response.
- Transfer aborted: the remote size of N does not match expected size 0 — OUR side: the by-URL dispatch enqueued without the size while the peer WAS sharing. Do not switch lanes for this class — enqueue directly on slskd with the real size from the search result (recipe: references slash slskd-dispatch.md). Peer-controlled names are mangled, so the organizer's manifest was wrong and the MusicBrainz gate refused the import with no_musicbrainz_match. Fix: the caller's title/artist wins over the peer-path guess in the manifest — pass them through on every slskd dispatch; a regression pin covers it.
- When the gate rejects, the organizer quarantines the job dir and the lane mirrors it in its quarantine tree. Clearing the lane's blocklisted rows store.forget_blocked alone is not enough — also retire the gated job dirs from the organizer's mirrored quarantine tree, or re-hunts get re-quarantined before they import.
- Soulseek long tail is accepted as not-importable. A Soulseek-sourced album lands only if the PEER's own file tags match a MusicBrainz release; the gate is not relaxed and the caller cannot vouch for a release. Refuse unmatched long-tail releases rather than landing them under guessed names — obscure EPs and 1960s-70s singles stay out as a known, accepted gap.

When sources genuinely fail (all rejections), fall back to Tidal if the
track exists on Tidal. The Tidal lane uses OAuth and streams directly from
Tidal's CDN, so transfers are deterministic.

**slskd search is OPT-IN, not stripped.** The aggregator's `/search` and
`/search/json` (19297) fan out to the provider lanes only by default, so a plain
query returns ``provider: "tidal"`` rows and nothing else — which reads as
"the aggregator filters Soulseek out". Add `slskd=1` (or `lanes=slskd`; the
handler unions them) and the slskd rows arrive in the same result set:

```
curl -s "http://IPVPLACEHOLDER:19297/search/json?q=<artist>+<album>&slskd=1"
```

Run the `slskd=1` shape BEFORE telling anyone a release is not grabbable: a
Tidal-only result set is a lane-selection artifact, not evidence of absence.
Query the lane directly at `http://IPVPLACEHOLDER:19496/search/json?q=...` (lane's own
HEADLESS_TOKEN) only when you need raw peer/file rows the aggregator flattens.
The aggregator's `/download` endpoint accepts `service=slskd` and enqueues
correctly (returns job_id).

**Tidal fallback (when slskd transfers genuinely fail):** after 2-3 slskd
sources fail via the failure classes above (not the size-0 class), fall back
to Tidal if the track exists on Tidal. The Tidal lane uses OAuth and
streams directly from Tidal's CDN, so transfers are deterministic.

Procedure:
1. Get tidal HEADLESS_TOKEN: `docker exec tidal-headless printenv HEADLESS_TOKEN`
2. Search tidal: `curl -H "Authorization: Bearer <token>" "http://IPVPLACEHOLDER:19493/search/json?q=..."`
3. Download via aggregator: `POST /download` form data `service=tidal&kind=track&url=<tidal.com/track/ID>&title=...&artist=...`
4. Monitor: `GET /download/tidal/<job_id>` — status `completed` means the file landed in the organizer import queue and then the library.
5. Verify in Navidrome (Subsonic API on IPVPLACEHOLDER:4533) or organizer `/library/albums` endpoint.

Batches of single songs from a pasted list (wiki/quiz/meme text): flexible-matching
presence check, per-track /download dispatch, singleton landing shape, and end-to-end
verification — `references/single-track-batches.md`.

Tidal FLAC: delivered quality is set by the OAuth client pair the token was
issued under, not the account tier. The working route is the in-container
device login with the FLAC-capable pair (`python /app/app/tidal/device_login.py`
inside `tidal-headless`, approve at link.tidal.com); the PKCE page
(login.tidal.com) is bot-walled and cannot be routed around — see
`references/lossless-sourcing.md`.

## Playlist imports

A playlist download is dispatched as ONE `kind="playlist"` job on the lane; the
downloader expands it into per-track downloads under `<playlist>/<artist>/<album>/`,
and the controller splits it into one organizer job per album, each carrying the
playlist export metadata (the legacy tool-UI path made per-track jobs instead —
both shapes feed the same mirror). After an organizer import succeeds,
`_mirror_playlist` reflinks the library copies into `/playlists/<name>/NN - <library_name>`
(btrfs FICLONE — copy-on-write, zero extra space, works across the separate `/music`
and `/playlists` mount entries). The `/playlists` folder is NOT imported by beets —
it is a hardlink export folder that beets never organizes.

**Empty `/playlists` folder — diagnostic order:**
1. Did playlist jobs actually dispatch? Check lane `/download/jobs/data` for
   `playlist_name` in job data.
2. Did the jobs reach the organizer? Check organizer `/queue/status`.
3. Did `_mirror_playlist` run? Grep organizer logs for `playlist mirror`.
4. Did `_match_library_file` find the library copies? Staging basename vs
   library filename mismatch is the most common silent failure.
5. Quarantine verdict? Trust the AUDIT (`event=quarantined`), not the folder —
   `quarantine/<job_id>/` dirs are created for every job unconditionally, so an
   empty dir proves nothing. An `all_files_no_metadata` verdict on a playlist
   whose files actually imported fine is the empty-staging misclassification —
   now distinguished as `staging_consumed` (the engine proves the landing or
   requeues; never a silent DONE). Genuine quarantine moves files and logs a
   `quarantine:` line per file.

**Fleet web UI and playlists:** the fleet web UI sends all result rows to `/dispatch` with the row's own kind. The aggregator validator now accepts `kind=playlist` (fixed 2026-10) — previously it returned 400. Playlist dispatch through the fleet web UI works. Direct playlist imports also work via the aggregator API or the fleet UI.

Full workflow trace + failure-mode table: `references/playlist-import-workflow.md`.

> **Deep audit → see `music-downloader-fleet-pipeline`** (auditing/hardening
> the fleet's code, gates, and pipeline internals).

After any discography dispatch, run the verification pass (resolver-missed
releases, throttle-gap reconciliation, per-album audit recipe):
`references/discography-grabs.md`.

Artist discography grabs ("get the discog for X") are NOT guaranteed complete
by the lane dispatch alone: the lane's discography resolver and its
`/search/json` disagree in both directions, so diff the dispatched group
against search and enqueue the misses by URL — recipe:
`references/discography-dispatch.md`.

Queue health, stuck/zombie jobs and lane-side cleanup:
`references/fleet-queue-forensics.md`. Finding fresh scene releases and mapping
them to lanes: `references/release-discovery.md`.

## Pitfalls that cost real time

- A stale `HEADLESS_TOKEN` in the shell env SHADOWS the per-lane .env files and
  every lane call 401s (the env value can be older than the files). If a lane
  answers 401, retry with `env -u HEADLESS_TOKEN` before blaming the lane.
- `--platform <lane>` narrows correctly only after the 2026-09-20 fix; on older
  copies of the script the `--platforms` default silently overrode it.
- Jobs frozen `queued` after a batch enqueue (no start, log silent): the
  worker-pickup race class — recover via pause→resume (no restart) and check
  for `job.pickup_miss` audit rows; recipe:
  `references/fleet-queue-forensics.md`.
- Organizer code is bind-mounted (`/your-stacks-path/fleet/organizer` →
  `/app/organizer`) but gunicorn imports modules at process start with no
  `--reload`: a pull or edit is NOT live until the container restarts. Compare
  `docker inspect -f '{{.State.StartedAt}}' organizer` against the changed
  file's mtime before trusting an organizer fix; `organizer/__pycache__/*.pyc`
  mtimes are not a proxy for the loaded code. Verify `git log -1` in
  `/your-stacks-path/fleet` is what the running container actually loaded.
- Reproduce a suspected organizer bug before naming a cause: the "concurrent
  imports raced" explanation for the 2026-10-17 false landing proof was wrong —
  the bug reproduced deterministically on a single job.
- **Tidal does not carry every release.** Late-period/obscure albums (e.g.
  The Beach Boys "Still Cruisin'" 1989 and "Summer in Paradise" 1992) return
  zero album hits. Search `type=album` and confirm a real album id before
  promising a grab; if absent, flag it for manual sourcing instead of
  dispatching a compilation that happens to share a word.
- **Enqueue an album by its Tidal album URL, not a track id.**
  `https://tidal.com/album/<id>` with `type=album`; search results' `id` field
  is the album id only when `type=album` is requested.
- **Lane blueprints are prefixed.** Enqueue/status routes live under
  `/download/...` (e.g. `/download/enqueue`, `/download/jobs/data`), search
  under `/search/json`, tidal under `/tidal`. A bare `/enqueue` or
  `/jobs/data` returns `{"error":"Not found"}` — prefix the blueprint, not a
  404 from auth.
- **slskd's batch enqueue route answers 207 Multi-Status as a PARTIAL
  SUCCESS**, not an error: when some files of a batch enqueue and some fail
  ("already queued, in progress, or an error occurred"), the body still
  carries `batch.transfers`. slskd-headless's client MUST accept 207 and
  record the enqueued transfers; raising on it creates no job rows for
  transfers that are actually downloading and removes the pinned tree out
  from under them. Treat 207 as success, then fail only if `enqueued` is empty.
- `docker exec <lane>-headless printenv HEADLESS_TOKEN` returns a working
  bearer; the plain `HEADLESS_TOKEN` in `your credential store` returns
  `{"error":"Unauthorized"}` against the lane. If a lane 401s, retry with
  `env -u HEADLESS_TOKEN` before blaming the lane.
- Brand-new releases (same-week singles/collabs): slskd peers won't have them
  yet and API-lane creds may be dead — the artist's Bandcamp is the fast
  legit lossless path. Before even that, confirm it is RELEASED: an album with
  a future date is not a grab target (`## A "new album" that is not out yet`). Check BOTH artists of a collab; NYOP ("name your
  price") pages = FLAC download for free, paid pages still hand you FLAC.
  (Seen 2026-09-20: "Berry Your Candy" — Berried Alive x The (John) Candy,
  on Bandcamp 6 days after release while slskd had zero copies.)
- Anniversary/reissue hunts (`...XXV`, deluxe, remaster): the long full-phrase
  query can return 0 while a shorter token subset finds everything - fire the
  shape ladder (artist+anniv token, artist+title, full title) and UNION all
  saved response dumps before concluding (measured: a 4-token full-phrase
  shape returned 0 responders while `artist + anniv-token` found every copy;
  see
  references/slskd-search-probing.md and scripts/slskd_rank.py). Flush every
  response to disk - stdout truncation hides results you already have.
- An album enqueue that 500s with `no sibling files and no size` is the
  lane's sibling-SEARCH query blackholing, not a dead peer - diagnose via
  `GET /api/v0/searches` and repair with the raw-enqueue + adopt path in
  references/slskd-ops-notes.md ("Album enqueue 500").

## A "new album" that is not out yet is not a lane gap

Check the release DATE before probing lanes or reporting absence. Labels and
artist sites announce albums months ahead; lanes only carry released material,
so a request for a future release resolves to the artist's back catalogue and
to similarly-titled strangers — which looks exactly like a broken search.

Order for "get me the new <band> album": library check → release date →
decide. Do not dispatch, and never report "not available anywhere", until the
date is known. "Releases <date>; only the lead single is out" is the correct
answer.

- An aggregator/NLU search that answers with the artist's other albums or with
  other acts sharing a title word is a FUZZY MISS, not a find. Match per row
  on `artist` + album/title + `year`; never accept a row because it carries one
  matching token.
- When it is genuinely pre-release: offer the released single
  (`kind=track`) and park the album on the aggregator watchlist
  (`POST /api/watchlist`) instead of re-searching it every session. State the
  release date in the report so the user knows why nothing landed.

## Before grabbing: what is actually missing

- Gap-check with NORMALIZED names, not exact paths: strip case, punctuation
  and diacritics before comparing (`Run the Jewels` vs `Run The Jewels`,
  `Hyëna` vs `Hyena`). Exact-path checks report false absences, and you
  re-grab albums the library already holds — the organizer then skips the
  re-grab as `already_in_library`.
- Recipe: list `Path('/your-media-path/library/music-library')`, match the artist dir
  by normalized name, then album dirs by normalized substring; only normalized
  misses are grab targets.
- Fast pre-check: `rygrab --lib "<artist>"` (organizer `/library/albums`)
  prints held albums under the organizer's normalized name — run it before
  dispatching to see whether a dispatch will land anything at all.
- slskd album picks, the lane enqueue route, and the end-to-end verification
  loop live in `references/slskd-ops-notes.md`; `scripts/slskd_group_check.py`
  prints per-group job states, organizer hand-off, and staging counts right
  after an enqueue (read-only). `scripts/slskd_rank.py` ranks candidate copies
  across saved response dumps (reissue/scene-aware; SAFE PICK + ARCHIVAL
  ALTERNATE with slskd:// sample URLs); `scripts/slskd_probe.py` fires, polls,
  and flushes raw searches to disk.
- Shared state: the library, the lane DB, and the slskd staging dirs are
  touched by every session and by kanban workers. Before a grab or a repair
  sweep, check for another live session on the same files (`ps aux`, recent
  mtimes, and the Hermes state DB's recent messages) — two sessions on one
  staging tree confuse each other's bookkeeping (adoption, cleanup, purges).
  If one is mid-task, stand down or split the work explicitly rather than
  racing it.

## Fleet map (lane liveness flips between sessions — always probe before trust, see Auth)

| Lane | Provider | Port | Tool dir | Status |
|---|---|---|---|---|
| qobuz | Qobuz | 19492 | tools/qobuz | **sidelined 2026-09-21** (free donor account — previews only; registry-disabled, container stopped) |
| tidal | Tidal | 19493 | tools/tidal | the provider lane (priority 1; wants the client-id fresh-login for FLAC) |
| deezer | Deezer | 19494 | tools/deezer | **sidelined 2026-09-21** (donor ARL dead). Album art unaffected (organizer art.py is independent) |
| slskd | Soulseek | 19496 | tools/slskd-headless | live; opt-in gap-fill lane |

- **the fleet web UI is the search/grab front-end over this aggregator** (`:19299`,
  `your-domain.example`) — classic-skin search tabs, fleet queue, Soulseek
  album hunter. It is NOT a library player and adds no acquisition path of its
  own: whatever it can grab, the aggregator can grab.
- **Read the service's own README before describing what a fleet service does.**
  `/your-stacks-path/fleet/<service>/README.md` (and its `docs/`) is the authority;
  inferring a service's role from its first paint, its hostname, or memory
  produces a confident wrong answer the user has to correct. Same rule for the
  the knowledge repo docs — grep them for the service name before asserting anything.

- Organizer (beets single writer): `http://IPVPLACEHOLDER:19298`
- Aggregator health/auth: `GET http://IPVPLACEHOLDER:19297/status` (unauthenticated,
  shows per-lane `auth: ok|expired`) — check this FIRST; an `expired` lane will
  accept jobs that then fail auth.
- Final library:`/your-media-path/library/music-library`(organizer-mounted`/music`).

- **Artist resolution is fuzzy — confirm the resolved id/title before you
  trust a dispatch.** Punctuation variants are DIFFERENT artists on Tidal
  (`X (Y)` vs `X Y` resolved to two distinct catalogs). Dispatch the id you
  verified, not the first fuzzy hit. When a wrong artist slips through:
  cancel and delete its queued jobs individually (some lanes have no group
  actions), remove the imported album dirs from the library, and re-check the
  library for every spelling of the name afterwards.

## Before you trust a dispatch (resolution, quality claims, cleanup)

- **Verify the RESOLVED artist entity, not the query string.** Resolution is
  fuzzy and name variants collide — `The (John) Candy` and `The John Candy`
  are two different artists with different ids, and `rygrab --artist`
  dispatches whichever the lane resolved first. Read the `resolutions` block
  (id + title) and compare it to the requested name character for character
  BEFORE the jobs drain; a wrong entity still imports and lands in
  `music-library` under the wrong artist dir, where it then reads as the
  library's copy.
- **Undo a wrong-entity landing immediately:** cancel each queued job, delete
  the job records, `rm -rf` the imported artist dir from `music-library`, and
  clear the matching `import_staging` dirs. Do it before the next organizer
  pass so nothing else indexes the wrong artist.
- **Lane job actions are not uniform.** Tidal answers
  `{"error":"this lane does not support group job actions"}` for
  `/download/jobs/group/<id>/<action>`; use per-job
  `/download/jobs/<job_id>/cancel` then `/delete` whenever the group route
  refuses. `/download/jobs/summary` also drops finished groups within minutes,
  so read `/download/jobs/data` while the group is still fresh.
- **Never describe import or source quality with an adjective** (`avg`,
  `high`, `lossless`). Lane job records carry no quality field, so any such
  word is invention the user will challenge. Quote a measured codec and bit
  rate (see references/source-quality-forensics.md, probe with
  scripts/probe_tidal_stream_quality.sh; for a P2P file the spectral cutoff is
  the truth, not the extension — scripts/spectral_cutoff.py, notes in
  references/p2p-lossless-verification.md) or say nothing.
- **`music-library` is opus 160k by design** (beets `convert: format: opus`,
  `delete_originals: yes`) — a lossless source is transcoded and the original
  discarded, so "why isn't this FLAC" is usually policy, not a lane fault.
  Check the source entitlement before blaming the pipeline.

## Probing Soulseek before blaming the lane

When a search looks empty, or you are picking test cases for the lane, probe
slskd directly instead of guessing. Search-only API (no download queued):
`POST /api/v0/searches` then `GET /api/v0/searches/{id}/responses` at
`http://IPVPLACEHOLDER:5030` with header `X-API-Key`. Full recipe, endpoint list and
worked measurements: references/slskd-search-probing.md.

The four rules that matter in every probe:

- Never `DELETE` a search that is still in flight - slskd throws
  `DbUpdateConcurrencyException` and every search after it returns 0 responses,
  which looks identical to "not on Soulseek". Let slskd expire them.
- Space searches ~40s apart with a 60-90s window; dropped searches read as 0 users.
- A 0-user result is never evidence of absence - re-query with a differently
  shaped string before concluding (`Da Drought 3` found 255 users where
  `Lil Wayne Da Drought 3` found none).
- **Persist search responses before the window closes.** A search that reaches
  `Completed, TimedOut` can have its `responses` array emptied by the time you
  re-fetch it, even though `fileCount`/`responseCount` were non-zero. Poll
  `GET /api/v0/searches/{id}` every few seconds and dump the full JSON to disk
  the moment `fileCount > 0` (or `responseCount > 0`); never trust a later
  re-fetch to still carry the peer/file rows. The fileCount alone is not enough
  to queue a download.
- Counts include other releases by the same artist and fan-made compilations,
  so inspect sample paths before trusting a hit, and keep one
  never-distributed album as a negative control.

To check whether a release is off-streaming at all, use the no-auth Deezer
(`api.deezer.com/search/album`) and Apple (`itunes.apple.com/search`) search
APIs and score on artist+title match - raw hit counts misfire on near-misses.
Keep the raw sweep output as dated JSON under `docs/data/` and regenerate any
write-up from it with a script, so the numbers stay verifiable.

## Library repair

Restoring corrupt/unreadable library files is a track-level replacement (re-grabs of
library content do not import). Procedure: music-library-maintenance skill,
references/manual-beets-import.md . slskd adoption + duplicate-skip mechanics:
references/slskd-ops-notes.md

## Dispatch quirks

- Scoped fill sweeps (missing studio albums for taste artists): follow
  references/fill-sweep.md - discovery filters, lane-fallback ladder,
  landing verification, title-core normalization.

- Bootlegs / rarities / slskd grabs also follow references/fill-sweep.md
  (slskd lane + organizer MB-gate sections): four provider lanes first,
  slskd only when absent everywhere; slskd grabs enqueue the organizer
  with source_kind slskd through the MB gate. slskd is the 5th lane
  (port 19496); it is NOT part of the default four-tool fan-out —
  aggregator search fans to 4 lanes; slskd is opt-in via the **UI
  toggle (L pill in the masthead, ?slskd=1)** or direct lane curl.

- rygrab REFUSES dispatch while any default-priority lane auth is expired
  (`refusing dispatch provider auth expired`): pass healthy lanes explicitly,
  e.g. `--platforms qobuz` alongside `--url ... --platform qobuz` —
  `--platform` alone does not override the default lane set.
- **Verify the resolved artist before any discography dispatch.**
  `rygrab --artist` name-resolves fuzzily; near-name collisions
  (punctuation variants, e.g. "The John Candy" vs "The (John) Candy")
  silently land a DIFFERENT band's albums. If the printed resolution
  title is not an exact match of the request, stop: run
  `type=album&q=<name>` and confirm the album titles belong to the band
  intended, then dispatch the exact entity with a direct
  `POST /download/discography {"artist_id": "...", "artist_name": "..."}`.
  Filter `type=album` hits by the result's `artist` field, never the title:
  name searches return OTHER artists' releases that merely feature or
  mention the name (features, same-word artists, joke/meme albums).
- **`"No albums found (may all be singles)"` is not a resolution failure.**
  The lane discography resolver drops releases with `num_tracks <= 2`
  unless `include_singles` is set, so a catalog that is all singles/EPs —
  or an artist whose solo/mixtape material isn't on the platform under
  their name — resolves to zero albums from a perfectly real entity.
  Confirm against a raw `type=album&q=<name>` search, then grab wanted
  releases individually via `--url` instead of re-dispatching.
- **Ambiguous artist credit → verify the entity id before grabbing.** The
  album page `https://tidal.com/browse/album/<id>` embeds schema.org JSON
  with the exact `byArtist` id+name — compare it to the resolved artist
  id. Tidal splits one person across stylized/variant entities, so a
  same-name-but-different-id artist is a DIFFERENT catalog: flag it as a
  known gap, don't grab on faith.
- **Tidal v1 `/search` returns `{"albums": {"items": [...]}}`, not a flat
  `items` list.** Reading `data["items"]` returns nothing and iterating
  `data["albums"]` yields dict KEYS, so `.get()` raises
  `AttributeError: 'str' object has no attribute 'get'`. Both mistakes look
  exactly like "this release does not exist on Tidal" — which is how a
  whole album can be wrongly reported as unavailable. Correct path:
  `data["albums"]["items"]`, and per-type keys are `albums` / `artists` /
  `tracks` / `playlists` / `videos` / `topHit`.
  Also: `session.request` is a `Requests` OBJECT, not a callable —
  `session.request("GET", path, params=…)` raises "not callable" and
  `session.request.get(...)` does not exist. Use
  `session.request.request("GET", path, params=…)` (the tidalapi
  `basic_request` path that attaches sessionId/countryCode/auth).
- **Aggregator `/download` and `/dispatch` take FORM fields, not a JSON
  body.** A JSON POST returns 400 `dispatch supports kind=track|album|
  artist|playlist` because the handler reads `request.form`. Send
  `service`, `kind`, `url`, `title`, `artist` as
  `application/x-www-form-urlencoded`.
- **Check a "missing album" premise against three independent sources
  before dispatching for it.** For The Sisters of Mercy the requested
  targets (Claps, Temple of Psych, Mission of Light, a 9-track "When You
  Don't See Me", Codes and Languages) were mostly not real releases: MB
  lists "When You Don't See Me" as a 3-track Single, has no release-group
  for Claps / Temple of Psych / Mission of Light / Codes and Languages, and
  Tidal's own artist page lists 46 releases carrying none of them. MB's
  artist release-group browse also caps at 100 per response and can return
  a null `count`, so a naive read truncates the catalogue and reports later
  albums as non-existent — page until a short page comes back. Filter MB by
  RELEASE STATUS too: primary-type Album/EP with no secondary type still
  includes Bootleg-status releases (three of the eight candidates for that
  band were bootlegs), so check `status == "Official"` per release before
  treating an entry as canonical.
- Wrong-artist rollback (imports land within minutes, so act fast):
  per-job `POST /download/jobs/<id>/cancel` then `/delete` for every job
  in the group; remove the library artist dir under music-library; remove
  the lane's `/storage/fleet/<lane>/import_staging/` dirs. /your-media-path
  deletions normally need explicit confirmation — a same-session undo of
  your own mistaken dispatch is the exception; state it in the report.
- `/download/jobs/group/<id>/<action>` is NOT fleet-wide: tidal
  answers "lane does not support group job actions". Fall back to
  per-job cancel/delete wherever the route errors.
- Re-dispatching albums the library already holds creates a new job
  group whose jobs flip to completed instantly and leaves duplicate dirs
  in import_staging — beets dedupe protects the library, but clean the
  duplicate staging dirs so disk isn't doubled.
- Discography dispatches miss catalog on purpose and by accident: the
  resolver drops releases with num_tracks <= 2 (singles/EPs) and covers
  only the one artist entity dispatched, while providers park the same
  band under name-variant entities. After dispatch, cross-check
  `type=album&q=<name>` rows (filtered on the row's artist field)
  against the queued titles; for underground/punk acts also check
  Bandcamp — Bandcamp-only releases never arrive via these lanes, so
  report them as known gaps rather than claiming a complete discography.
- Partial-album re-grabs land as a NEW sibling dir (organizer never merges into the existing dir); finishing an edition is a library-side merge, see music-library-maintenance phase7. Lane `/search/album/<id>/tracks` returns 500; authoritative tracklists come from qobuz.com album pages.
- **Organizer identity gate is all-or-nothing on the FIRST staged track.** `_metadata_identity(source)` (engine.py) returns only the first audio file's identity, and the pre-import check skips the ENTIRE album job when that one track is already in the library. A hole-fill whose first track happens to be held therefore drops every missing track silently (job logs `already in library (identity) — marking DONE`). The per-track batch helper `_library_has_identities` exists and is currently unused; the correct predicate is *skip only when every staged track is already present*. Until fixed, verify a `DONE`/`already_in_library_gated` job actually landed by counting tracks in the artist dir, not by job status.
- **Artist-dir names can differ by a single unicode hyphen/apostrophe** (e.g. `G‐Eazy` U+2010 vs `G-Eazy` U+002D, `When It’s Dark Out` U+2019 vs `When It's Dark Out`). The gate's `_find_artist_dir` does not normalise these, so a held fragment under the unicode variant is missed and the re-grab creates a parallel artist dir. Treat two artist dirs that differ only by hyphen/apostrophe as the same act; consolidate via the phase-7 merge and verify both dirs before declaring the fill complete.
- Lane job ids purge from `/download/jobs/summary` within minutes: verify
  landings by globbing the artist's album dirs server-side (track counts
  before/after), not by job status.
- **Organizer beets dedupes imports against the library: tracks already held in
  ANY edition dir get routed there or skipped, so album grabs land partially
  across edition dirs — recheck every edition dir of the artist after a grab.
- **Beets album-level duplicate check kills whole album re-grabs.** `duplicate_keys.album = [albumartist, album]`, so a hole-fill whose album name matches an existing library album row is skipped wholesale under the live config's default `duplicate_action: ask` (quiet mode → "This album is already in the library! Skipping."). Per-item `duplicate_action` values do not help: `keep`/`merge` create `.1` duplicate files, `remove` deletes library-only tracks, `skip`/`ask` drop the album. Only `upgrade` fills the hole while preserving library-only tracks. The item-level check cannot substitute — it appends `NoneQuery('album_id', True)`, so it matches only singleton (album_id IS NULL) items and returns 0 hits for album members. Until the live config uses `upgrade`, verify a hole-fill landed by counting tracks in the album dir before/after.
- **Realistic bitrates decide `upgrade`'s supersede.** With `upgrade`, a staged track supersedes the library copy only when its bitrate is higher; realistic FLAC (~900k) beats curated opus 160k, so a re-grab replaces curated bytes for the overlapping track. Pre-filter the staged dir to missing tracks only, or accept the churn (consistent with the phase-7 merge policy, which also replaces fragment copies with the fuller edition's).
- Long typed path literals (album/track names with spaces/punctuation) get
  mangled in tool input: derive paths via server-side glob/listdir, never
  hand-type album names into shell or execute_code commands.
- Some sessions mangle text in BOTH tool inputs and outputs (=, # comment
  prefixes, leading indents, small words). All file edits then go through
  `terminal` python3 heredoc splices with ast.parse verification — full
  procedure in references/heredoc-editing.md. `git checkout -- <file>` +
  md5-vs-HEAD is the reset loop when a region arrives corrupted.


## Source quality: FLAC first, lossy as a very last resort

Standing user rule: the download SOURCE must be FLAC wherever possible; M4A/MP3
only when nothing lossless exists anywhere. Even though the organizer converts
to opus 160k, a lossy source is a double-lossy artifact — never accept one
silently. Every provider lane has a delivered-quality gate
(`<lane>.lossy_policy`, default `deny`); slskd is exempt by design (peers
supply whatever exists) and logs its format mix at group finalize.

- **Asking for lossless is not the same as getting it.** A lane's request is
  honest; the delivery is not always. Measured 2026-09-19: a SUBSCRIBED Tidal
  account (subscription ACTIVE, premiumAccess true) still received AAC for
  every LOSSLESS/HI_RES request on tested tracks — HIGH (mp4a.40.2) on
  mainstream releases, LOW (mp4a.40.5) on some indie catalogue. Cause is
  client-id entitlement and/or plan tier, NOT "no subscription" — never judge
  entitlement from one track, and never from tidalapi's `user.subscription`
  (it reads the PLURAL `/users/<id>/subscriptions`, which 404s; the singular
  `/users/<id>/subscription` returns the real document).
- **Every job records what it actually got** in `job.data.source_quality`
  (requested quality, policy, lossless/lossy track counts, delivered
  codecs/formats) — read it in `/download/jobs/data` before judging a lane, a
  grab, or a "broken" dispatch.
- **Under `deny`, a lossy delivery fails the job with a message naming the
  fix** — that error is the policy working, not a lane outage. Do not flip a
  lane to `accept` to "unblock" a grab unless the user asked for lossy.
- **Tidal now ships `lossy_policy: accept`** (user decision 2026-10): EAC3-only
  tracks download as lossy (loudly logged, recorded in source_quality) instead
  of killing the whole job. FLAC is still requested first — lossy is the last
  resort for tracks with no lossless master. This is essential for playlist
  imports where one bad track shouldn't fail the entire playlist.
- **Tidal entitlement is per OAuth client pair, NOT per account.** The same
  HiFi account gets FLAC with the "flac" client pair but AAC/EAC3 with the
  legacy pair. Re-authenticate via device login (see lossless-sourcing.md).
  If track 41223159 fails with EAC3/LOW, the session is on the wrong client pair.
- **Egress can cap quality too — rule it out before re-authing.** The same
  device-flow token (`is_pkce: false`, no PKCE login) delivered true 16-bit/
  44.1 FLAC when the lane egressed through a Mullvad proxy, while the cluster's
  own IP got AAC. Prove it with `file` on a downloaded track, then rotate egress
  (`references/tidal-egress-and-proxy.md`) before spending a re-login.
- Per-lane keys, delivered-format probe recipes, entitlement re-login, and
  lane job-management quirks: references/lossless-sourcing.md.

## Auth

- Lanes: `Authorization: Bearer $HEADLESS_TOKEN`. Token lives in
  `path-to-credentials` (shared by the three provider
  lanes; gitignored — never print or commit it).
- **slskd does NOT accept the fleet token.** Its lane runs with its own
  `HEADLESS_TOKEN`; read it from the live container:
  `docker exec slskd-headless printenv HEADLESS_TOKEN`. Using the fleet
  token yields a 401 whose body is `{"error":"Unauthorized"}` — no
  `results` key — so a client that does `.get("results", [])` sees 0 rows
  and the auth failure masquerades as "no peers". Check for an error key
  (or hit `/health`) before diagnosing an empty slskd search as peer
  variance.
- Organizer: `Authorization: Bearer $FLEET_ORGANIZER_TOKEN` from
  `path-to-credentials`.
- Lane `/status` returns 401 without the bearer — that means auth missing, not
  service down. `/health` is the unauthenticated liveness probe.
- **`/health` and the aggregator `/status` LIE about provider auth.** 2026-09-17:
  Qobuz reported `auth: ok` (label last refreshed 2026-08-08) and
  `authenticated: true` while `docker logs qobuz-headless` showed
  `Token refresh failed: 401 .../user/login` and every `/search/json` returned
  `{"error":"provider_error","results":[]}`. A lane storing only
  `QOBUZ_TOKEN` + `QOBUZ_USER_ID` (no email/password) cannot self-heal an expired
  token — it needs a human re-login. Always confirm with a real search probe
  (`?q=<known artist>&type=artist`) before trusting a lane with a dispatch.
- **slskd cannot do artist/discography dispatches.** Its `/search/json` returns
  track rows (`artist`, `album`, `username`, `filename`) with no artist entities,
  so there is no `artist_id` to POST; `fleet_dispatch` routes non-track/album
  kinds to the provider lane. `rygrab.py --platform` does not accept slskd at
  all. slskd is album/track-at-a-time only — do not plan bulk discographies on it.

## API contract (frozen — core/fleet_core/app/headless/routes.py)

```
GET  {lane}/search/json?q=<query>&type=<artist|album|track>   -> {"results":[{id,title,...}]}
POST {lane}/download/discography  {"artist_id": "...", "artist_name": "...", "override_existing": "0"}
POST {lane}/download/enqueue      {"url": "...", "kind": "track|album|playlist"}
GET  {lane}/download/jobs/summary -> per-group {queued, running, ...} counts
GET  {lane}/download/jobs/data    -> full job list (status, progress, files)
GET  {organizer}/queue/status     -> per-status counts (bearer = organizer token)
```

- There is no `/openapi.json` (404s) — enumerate the full route surface from
  repo source: `grep -n "@bp.route" your-project-path/tools/<lane>/app/*/routes.py`.
  Search hits carry `artist`, `track_count` and `url` fields (use `url`
  verbatim for `--url` enqueues).

## Lane priority policy (user-set 2026-09-06)

All lanes deliver lossless, so quality is roughly interchangeable — priority
is about load, not fidelity:

1. **tidal** (Tidal) — the only provider lane (2026-09-21: qobuz +
   Deezer sidelined; Tidal wants the client-id fresh-login lever for FLAC)
2. **slskd** (Soulseek) — opt-in gap-fill ONLY via explicit `--platform slskd`;
   P2P search is slow/noisy; never part of default fan-out; MB-gated on import.

**Very large discographies: spread, don't pile up.** `--dispatch spread`
searches the artist's albums on each candidate lane and round-robins per-album
enqueues across them (each lane serves its own provider URLs, deduped by
normalized title). One service holding a 100-album discography alone is the
thing to avoid.

## Procedure

Fast path — use the bundled CLI (stdlib-only, mirrors `scripts/driver_phase2.py`):

```bash
python3 scripts/rygrab.py --status
python3 scripts/rygrab.py \
    --artist "System of a Down" --wait                      # priority dispatch
python3 scripts/rygrab.py \
    --artist "<huge discog>" --dispatch spread              # spread across lanes
python3 scripts/rygrab.py \
    --url "https://tidal.com/album/..." --platform tidal --wait
python3 scripts/rygrab.py \
    --group <group_id>            # per-job status dump + lane/organizer state
python3 scripts/rygrab.py \
    --group <group_id> --retry    # requeue errored jobs in the group
python3 scripts/rygrab.py --poll
```

- `--artist` resolves the artist per lane via `/search/json` (exact normalized
  name match preferred), then dispatches per `--dispatch`:
  `priority` (default — first candidate lane that resolved, in
  Qobuz→Tidal→Deezer order), `least-loaded`, `all`, or `spread`.

- `--wait` polls `/download/jobs/summary` on the dispatched lane(s) until
  queued+running hits 0 (or `--timeout`, default 3600s), then shows the
  organizer queue so you can see the beets import drain.
- `--url` enqueues one album/track/playlist URL (kind inferred from the URL).
- `--poll` just prints current lane + organizer queue state.
- **`rygrab.py` aborts dispatch if ANY lane shows auth expired** (conservative
  fleet-wide gate). Workaround while one lane is down: resolve on the healthy
  lane via `/search/json`, then curl that lane's `/download/discography` or
  `/download/enqueue` directly (raw commands below).
- **`/download/enqueue` only accepts album/track/playlist URLs** — an artist
  page URL fails with `Not valid <provider> URL` (observed: Qobuz
  `open.qobuz.com/artist/<id>`). For "grab everything by artist" always use
  `/download/discography`; resolve the id with `type=artist` search first.
- **Tidal URLs for enqueue are `https://tidal.com/album/<id>`** (no
  `/browse/` segment; `tidal.com/browse/album/...` fails to parse).

Manual curl path (if the script is unavailable):

```bash
TOKEN=$(grep '^HEADLESS_TOKEN=' path-to-credentials | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://IPVPLACEHOLDER:19492/search/json?q=System%20of%20a%20Down&type=artist'
# send BOTH artist_id and artist_name — each orchestrator uses whichever it needs
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"artist_id":"<id>","artist_name":"System of a Down"}' \
  http://IPVPLACEHOLDER:19492/download/discography

## Shortlist dispatch by genre

Sourcing the rows: one research subagent per genre, dispatched in parallel, each
returning ~10–20 canonical artists plus a few deeper cuts, and 1–3 albums each
with years. Use chart/last.fm/Deezer APIs for the canon and weight the shortlist
toward the user's taste (dark, free, raw over smooth; one copy per canonical
studio album, lives and compilations out). Land the output as one shortlist JSON
(`{artist, album, genre}`) and let the run JSON be the single source of truth
for per-row status — never track drain state in prose.

Curate a shortlist (genre → artists → 1–3 canonical studio albums each) and
dispatch it through the fleet in one pass: resolve each album on the live lane,
skip anything the library already holds, dry-run to validate resolution, then
dispatch. This is the right shape for "more jazz / blues / latin / ambient"
asks — never hand-roll a per-album download loop; use the shortlist driver
instead (skill script `scripts/grab_shortlist.py`, stdlib-only).

Input shape (one JSON file per genre):
{
  "genre": "jazz",
  "artists": [
    {"name": "Miles Davis", "tier": "main", "albums": [{"title": "Kind of Blue", "year": 1959}]}
  ]
}

Steps:
1. Research first — 15 mainline + 5–6 acclaimed extras per genre, each with
   evidence (a Deezer/Tidal page URL) and exact studio album titles + years.
   Research is its own step; this skill dispatches what research produced.
2. Dry-run: `grab_shortlist.py <file>.json --dry-run` — verifies every album
   resolves on the lane without dispatching anything. Treat `not_found` as a
   real miss: flag it for manual sourcing; never dispatch a compilation that
   merely shares a word.
3. Skip-if-held: the driver indexes the beets library
   (`/your-stacks-path/beets/config/library.db`, `albums` table) by year/edition-
   stripped normalized artist+title and skips anything already held.
   Year-suffixed dirs (`Pablo Honey (1993)`) and edition variants
   (`Legacy Edition`, `Remastered`) must be stripped before comparing, or the
   check misses and the album is re-grabbed.
4. Dispatch remaining albums via `--url <tidal.com/album/<id>> --platform tidal`
   (tidal is the only live provider lane; slskd is opt-in, track-at-a-time,
   not for discographies or shortlists).
5. Throttle lane calls (~5 s) and record the run to
   `.tmp/grab-shortlist-run.json` with per-album status
   (held / not_found / dispatched / dispatch_failed) plus a tally. Report misses
   explicitly — a silent short batch looks like success.
6. Verify landings against the BEETS DB, not a dir listing alone: index
   `{normalized albumartist: {normalized album}}` from the `albums` table and
   match each shortlist row with case, punctuation, and parentheticals stripped
   (`Giant Steps (60th Anniversary …)` must match a `Giant Steps` request).
   Then compare the album's ITEM COUNT against the pressing's `track_count` —
   an album row carrying 1 track is a PARTIAL import, not a landing: either the
   lane gave you a 1-track "album" (a mislabeled single) or beets deduped the
   rest into another edition dir. Re-dispatch it by explicit URL at a pressing
   whose `track_count` is the full album, and re-check the artist's other
   edition dirs before declaring a hole. Job status proves nothing (lane rows
   purge in minutes; `completed`/`DONE` is not landing proof).

Pitfalls:
- **The edition penalty must name `live|bootleg|concert`.** Parenthetical
  stripping makes `Giant Steps (226 bpm – Live from The Tiberi Tapes)`
  normalize to `giant steps`, so a bootleg silently satisfies the shortlist row
  and the real studio album is never fetched. Before a run, grep the driver:
  `grep -n 'EDITION_RX' -A3 scripts/grab_shortlist.py` — the pattern must cover
  live/bootleg/concert as well as deluxe/remaster/anniversary/expanded.
- **Classic albums often have NO clean studio pressing on Tidal.** Read
  `track_count` per candidate: `1` means a mislabeled single, and the only real
  option may be a bloated anniversary/super-deluxe edition (35 tracks for a
  7-track album). Take the deluxe when it is the only studio source, and say so
  in the report — an edition compromise beats a missing classic.
- **Expect the occasional substitution and record it in the run JSON.** When the
  platform genuinely lacks the album (e.g. only a live cut exists), dispatch
  another canonical studio album by the same artist and rewrite that row's
  `album` (plus a `note`) so the completion test matches what will actually
  land. A stale expectation makes a finished run read as permanently pending.
- **Dispatch the ambiguous three by explicit URL, not by title.** After a dry
  run, hand-resolve any row whose pick looks wrong and enqueue
  `--url https://tidal.com/browse/album/<id> --platform tidal`; the resolver
  will otherwise repeat the same bad pick.
- Tidal enqueue URLs: rygrab accepts both `https://tidal.com/album/<id>` and
  `https://tidal.com/browse/album/<id>` (it normalizes before enqueue — the
  `/browse/` form dispatches fine). A raw `POST /download/enqueue` is the
  stricter path, so use the bare `/album/<id>` form when you curl the lane
  yourself.
- Aggregator `/search/json?q=<artist> <album>&type=album` returns `results[]`
  with `artist`, `title`, `track_count`, `url`; pick the clean release (no
  edition words, studio-sized track count) — the lane's edition policy applies
  at dispatch, but the resolver returns many editions per album.
- Tidal carries zero hits for some releases (late-period/obscure catalogue);
  `not_found` is a known gap, not a reason to dispatch a near-match.
- rygrab aborts if any lane shows auth expired — dispatch only healthy lanes;
  check `GET http://IPVPLACEHOLDER:19297/status` first, and probe with a real search
  before trusting `auth: ok` (a stale token can still read ok).
```

## Fleet ops — disable / re-enable a lane

Disable a lane (halt its backlog, stop its container):

1. Add `profiles: ["disabled"]` to the service block in
   `your-project-path/compose.yaml` (after the existing
   `container_name` line, before the run-as-user comment). This is a
   secondary guard for whole-file `docker compose up -d` runs.
2. **Remove the lane's line from `your-project-path/deploy/services.conf`.**
   This is the **real** deploy-side kill switch. The deploy engine runs
   `docker compose up -d <service-name>` — explicitly naming a service
   BYPASSES compose profiles, so a profiles-disabled lane comes right back
   on `deploy.sh all`. The registry is the authoritative enable/disable
   source; compose profiles only guard whole-stack up runs. Both must be
   in sync. (Observed 2026-09-15: `deploy.sh <lane>` silently
   recreated a profiles-disabled container.)
3. Stop and remove the live container:
   `docker stop <lane>-headless && docker rm <lane>-headless`
4. Commit + push both files (compose.yaml + services.conf) to the
   monorepo origin.
5. On your host prod: `cd /your-stacks-path/fleet && git pull origin main`
   (prod checkout is service-owned — plain your-user git commands fail EACCES
   if you try to work there directly; pull from the dev checkout then
   deploy via `deploy.sh all`).

Re-enable: remove the `profiles: ["disabled"]` line from compose.yaml,
restore the lane's line in services.conf, commit+push, deploy.

## Fleet maintenance — purge a lane's queue

When a lane's queue has grown unbounded (e.g. a discography flood) and you
want to start clean — the queue is SQLite-backed, so the purge is a file
delete, not an API call:

1. Stop and remove the lane container:
   `docker stop <lane>-headless && docker rm <lane>-headless`
2. Delete the lane's queue DB and order file (all under
   `/storage/fleet/<tool>/data/`):
   - Qobuz / Tidal / Deezer: `jobs.db`, `jobs.db-shm`,
     `jobs.db-wal`, `queue_order.json`
   - slskd: `lane.db`, `lane.db-shm`, `lane.db-wal`
3. Staging residue: `/storage/fleet/<tool>/import_staging/` may hold
   `upload_*` partial dirs from aborted jobs (inert, but numbering in the
   thousands after a flood). Clear with:
   `find /storage/fleet/<tool>/import_staging -maxdepth 1 -mindepth 1 -type d -name 'upload_*' -exec rm -rf {} +`
   Only after the lane is stopped.
4. Verify: organizer `GET /queue/status` should show READY=0, PROCESSING=0.
   DONE/FAILED counts are historical and harmless.

**Pitfall:** a lane "rebuilding" its backlog on restart is the SQLite DB
being read back into the worker. If the DB is present at container start,
the queue reappears. Purge BEFORE restart, or the backlog returns.

## Finishing a decommission — the operator pass

The repo-side excision and the lane-teardown list above stop at code and
data. What such a batch typically leaves to an operator (all five steps, in
order):

1. Container and images: the teardown list covers `docker stop`/`rm`; add
   `docker rmi` of every matching image (tagged and untagged), then confirm
   the port is free (`ss -tlnp | grep <port>`).
2. Disable the traefik route on your host — rename, do not delete:
   `ssh your-user@IPVPLACEHOLDER "sudo -n mv /your-stacks-path/traefik/config/dynamic/<lane>.yaml /your-stacks-path/traefik/config/dynamic/<lane>.yaml.disabled"`.
   traefik only loads `*.yaml`/`*.yml`, so the rename unloads the route and
   keeps a one-command rollback. Verify no active yaml still names the port.
3. Drop the lane's key from `TOOL_HEADLESS_TOKENS` in the prod `.env` —
   parse with Python `json.loads`, back the file up first, print no values.
4. Sweep the out-of-repo consumers no CI covers: the knowledge repo `scripts/*`,
   `~/.hermes/scripts/*` monitors' `LANES` tuples, root crontab scripts
   (`sudo -n grep -rl`), and the skills.
5. Pull prod after the push, then clear the checkout's untracked leftovers
   (`tools/<lane>/.env`, root-owned `__pycache__` — `sudo -n rm -rf`).

Verify by direct measurement, never by task reports: port refuses, no
container/image, the served JS/HTML of the UIs carries zero refs, surviving
lanes healthy. Data dirs (`/storage/fleet/<lane>`, `/your-app-data-path/<lane>`)
stay for an explicit user disposition decision — never delete data on your
own initiative.

**Before starting a planned batch here, check for a parallel session.**
This checkout is shared with card-driven/headless runs that commit and push
from the same tree. `git log --since=<plan date>` plus the roadmap §-ledger
(`docs/improvements-roadmap.md` tail) show what already landed; re-scope to
the remaining operator items instead of re-executing phases.

## Spotify artist page as verified discography reference (not a download source)

Spotify is decommissioned as a lane (Spotify removed 2026-09-21) — never dispatch from it. Its artist page IS the best **verification point** before dispatching through Tidal/slskd:

```bash
curl -s -L https://open.spotify.com/artist/<SPOTIFY_ARTIST_ID> -o spotify-artist.html
```

The page embeds `initialState` as base64 in `<script id="initialState" type="text/plain">`. Decode it and walk `entities.items[spotify:artist:<id>].discography`:
- `spotify:album:<id>` entries (under `albums.*.releases.items`) = verified discography: name + year + URI
- `discography.topTracks.items[*].track.*` = verified top tracks

Decode recipe:
```python
import re, base64, json
html = open("spotify-artist.html").read()
b64 = re.search(r"<script id=\"initialState\" type=\"text/plain\">([^<]+)</script>", html).group(1)
b64 += "=" * (-len(b64) % 4)
data = json.loads(base64.b64decode(b64))
for uri, item in data["entities"]["items"].items():
    if uri.startswith("spotify:album:"):
        print(item.get("name"), uri)
    if uri.startswith("spotify:track:"):
        print(item.get("name"), uri)
```

Then diff the verified album list against `os.scandir(music-library/<Artist>)` with year/edition-stripped normalized names to find genuine gaps, and dispatch only missing releases via `POST /download/discography`.

**This is reference only.** Spotify track/album URIs are not dispatchable through the fleet (no Spotify lane). The URI identifies the release; resolve it on Tidal/slskd by title+artist before dispatching. Never treat a Spotify search result as a download URL.

## Last resort: official artist YouTube channel via yt-dlp

When every fleet lane fails (slskd peers all report ``File not shared``, Tidal has no artist/album content, no other lane carries the release), fall back to the artist's official YouTube channel using yt-dlp (``/usr/bin/yt-dlp`` on your host). This is reference/verification material only — YouTube is not a dispatchable lane and yields single-track audio from MVs/live clips, not full albums.

Procedure:
1. Confirm artist identity matches the Spotify-verified discography (decode the artist page's ``initialState`` base64 block and read ``discography`` + ``topTracks``) before downloading anything.
2. Search the channel: ``yt-dlp "https://www.youtube.com/@<channel>" --flat-playlist --print "%(title)s|%(id)s|%(uploader)s"``
3. Download official MVs/live audio as opus:
   ``yt-dlp --extract-audio --audio-format opus --audio-quality 0 --output "%(title)s [%(id)s].%(ext)s" <youtube_url>``
   - Warning: YouTube extraction without a JS runtime may miss formats (EJS deprecation). Add ``--js-runtimes deno`` if needed.
   - Output is 48kHz stereo opus — the fleet's policy is opus 160k, but a verified YouTube source beats no source.
4. Write to ``/your-media-path/library/music-library/<Artist>/``.
5. Verify with ffprobe (codec opus, sample_rate 48000, channels 2) and file duration.
6. Register the artist in wanted-monitor (mode=auto) as a secondary retry in case slskd peers later share the release.

Never dispatch YouTube URLs through the fleet lanes — there is no YouTube lane, and ``POST /download`` will reject them. Treat YouTube as a verified last resort, not a lane.

---

## Discography dispatch — track-count failsafe (historical)

The Spotify lane (decommissioned 2026-09-21) enforced
`MAX_DISCOGRAPHY_TRACKS = 100` on `/download/discography`
(configurable via `downloads.max_discography_tracks` or the
`MAX_DISCOGRAPHY_TRACKS` env var). Before enqueueing any artist, it resolves
each album's track count; if the total >= cap, it refuses with HTTP 422.

This prevents a repeat of the 2026-09-07 Martin Stadtfeld flood, where a
single 10.9k-track album job (one T1 envelope) bypassed the 500-job queue
cap and spawned 65k downstream jobs via `fetch_album_tracks` fan-out. The
queue cap counts jobs, not tracks — the flood was one job.

That flood path died with the Spotify lane; the underlying lesson
(queue caps count jobs, not tracks) applies to any future fan-out.

## Fleet status check

```bash
curl -s -m 5 http://IPVPLACEHOLDER:19297/status | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'{k}: auth={v.get(\"auth\")} reachable={v.get(\"reachable\")}') for k,v in d.get('health',{}).items()]"
```
- Lanes can show auth `ok` even when a provider token is stale — the
  health endpoint tests the token's presence, and a stale token can still
  pass. Real auth failures surface only in lane logs.
- Tidal lane: auth expires without warning and the lane keeps accepting
  jobs (which then fail). Check lane logs for `[tidal] token refreshed`
  vs `[tidal] token expired` to distinguish a healable auth hiccup from
  a hard expiry that needs manual re-auth.
- If the aggregator reports a lane expired but the lane logs show a
  successful token refresh, trust the logs + a live search call over the
  cached status (Tidal has healed on redeploy with status flipping to
  ok without manual re-auth).
- **Large discographies exceed HTTP timeout after acceptance.**
 Confirm the job landed in `/download/jobs/summary` — blindly retrying the
 POST gives you duplicate job groups. Transient-only retry: 5xx/429/network, not 4xx.
 **2026-09-08: rygrab.py now enforces this** —`dispatch_discography`
 wraps the POST: on timeout it checks the lane's summary for a group of
 the same artist created <10 min old and returns guarded instead of
 repeating. (Real cost of ignoring: "Traditional, Martin Stadtfeld"
 21,921-track discog dispatched 3x in 5 min ≈ 65.7k jobs, 82% of the
 entire fleet backlog.)
- **Spotify discography flood (2026-09-07):** a single ~11k-track
 discography entered as ONE album-job (T1 envelope) bypassed the 500-job
 queue cap and spawned 65k downstream jobs via `fetch_album_tracks` fan-out.
 Fix: `MAX_DISCOGRAPHY_TRACKS = 100` on `/download/discography` (refuses
 with HTTP 422). The queue cap counts JOBS, not TRACKS — a single album
 job carrying thousands of tracks sails past it. A per-track cap is the
 correct unit.
- **Prod .git is service-owned** — `cd /your-app-data-path/webamp` and plain `git`
 commands fail EACCES for your-user. The deploy path is: commit+push from
 dev, then `sudo -u agent git -C /your-app-data-path/webamp pull --ff-only` (or use
 the FORGEJO_TOKEN inline-credential pull flow in webamp-stack-ops). Same
 applies to `/your-stacks-path/fleet`.
- **Queue purge pattern (2026-09-15):** when the user says "clear the queue" or "wipe the backlog," the queue is SQLite-backed — the purge is a file delete, not an API call. Procedure: stop the container, delete `jobs.db` (+ `-shm`, `-wal`) and `queue_order.json` from `/storage/fleet/<tool>/data/`, clear `upload_*` staging dirs, verify organizer `/queue/status` shows 0 READY/PROCESSING. A lane "rebuilding" its backlog on restart is the SQLite DB being read back into the worker. Purge BEFORE restart.
- **Lane disable gotcha (2026-09-15):** the deploy engine (`deploy.sh <service>`) explicitly names the service, which BYPASSES compose `profiles: ["disabled"].` The real kill switch is the lane's entry in `deploy/services.conf`. Remove it there AND add `profiles: ["disabled"]` to compose.yaml. Both must be in sync.
- **Cancelling duplicate groups:**`POST {lane}/download/jobs/group/<group_id>/<action>`
 (cancel/delete/retry...). `cancel` only signals ACTIVE jobs, skips
 terminal, returns {applied, skipped, remaining}. **Pass`?limit=N`** —
 whole-group runs (17k jobs) exceed the gunicorn worker timeout and
 kill the request; loop client-side until`remaining: 0`. Cancelled
 jobs are terminal →`POST /download/jobs/purge` deletes them.
- **Check `19297/status` for `auth:"expired"` before dispatching** — a lane can
 be reachable+healthy with an expired provider token; its jobs fail later.
- **Deezer (Deezer) history is stale (2026-08-16)** — verify auth state,
 don't assume. **Observed 2026-09-06:** deezer `/download/discography` can
 500 with `RuntimeError("No albums found")` (orchestrator.py:121) when
 `/search/json` resolves the artist fine — fall back to qobuz/tidal.
- **Aggregator `/status` (19297) can lag lanes by minutes after a deploy**;
  if it reports expired but lane logs show `token refreshed`, trust the
  logs + a live search call over the cached status (Tidal healed on
  redeploy, status flipped to ok without manual re-auth).
- **Tidal orchestrator has no group cancel/retry implementation**
  (route exists, `job_group_action` attribute missing) — stuck jobs drain
  only via worker error-retry; don't burn time trying group actions there.
- **Staged imports may sit in `/your-app-data-path/<tool>/import_staging` for days**
  with the lane queue at 0 (drain stalled). Check staging mtimes before
  assuming "all quiet"; confirmed-orphan staging for artists already canon
  → copy to quarantine and drop (user-approved) rather than re-import.
- **The organizer is the ONLY beets writer.** Never run `beet import`
  yourself, never enqueue a tool's download dir directly — tools stage to
  `/your-app-data-path/<tool>/import_staging` and POST the organizer `/enqueue`
  themselves. Organizer deletes staging copies after DONE.
- Organizer enqueue path translation: container `/app/import_staging/<X>` →
  host `/your-app-data-path/<tool>/import_staging/<X>` (organizer sees `/your-app-data-path`).
- Ports bind IPVPLACEHOLDER, not IPVPLACEHOLDER — curl the WG/LAN IP.
- Throttle multi-lane calls (~5s); the lanes are gentle shared services.
- Never commit tokens, `.env`, `data/`, or `downloads/` contents; monorepo
  root `git add -A` is safe by design only because gitignore covers them.

## Verification

**Queue status is not landing proof.** Organizer `DONE` rows arrive with
`reason=gated_import_landed` (a DB-census or byte-size claim) or
`reason=already_in_library_gated` (a SKIP — nothing was imported); both are
heuristics, not evidence the files exist. Measured 2026-10-17 (Stick - Heavy
Bag): a single staged track whose byte size coincidentally matched an unrelated
library file certified the album DONE, deleted its staging, and skipped the
quarantine path — the album never entered the library and the source copy was
gone (`reason`/`skip` lines in `/app/data/audit.jsonl`). A false landing proof
is silent data loss, not a queue hiccup.

Prove a landing by content before reporting success — the album dir and its
tracks under `/your-media-path/library/music-library/<Artist>/`, cross-checked against
the beets DB:

```bash
sqlite3 /your-stacks-path/beets/config/library.db \
  "select albumartist, album, count(*) from items where album like '%<Album>%' group by 1,2;"
```

Details and the re-fetch recipe: references/verifying-downloads.md.

1. `/download/jobs/summary` on the dispatched lane drains to 0 queued+running.
2. Organizer `GET /queue/status` → counts move READY→PROCESSING→DONE.
3. Files appear under `/your-media-path/library/music-library/<Artist>/...` as opus
4. If the track isn't in the library, search lane queues, organizer queue,
   and staging dirs — see references/verifying-downloads.md.
5. Beets may file tracks into a differently-named album dir than the URL
   album title (e.g. `Odyssey Of Respair`, or an undated dir beside a dated
   one) — verify the landed path before declaring success; when the grab
   was `type=track` the track lands in the album dir named by the file's own
   album tag, not the requested title.
6. Track-mode dispatches (one URL per track) explode into one stub dir per
   track (`Artist/Album/NN - Title.opus`) — after a large track-mode grab,
   expect thousands of 1-track album dirs; regroup by the files' own
   `album_artist`/`album` tags into real album dirs before any dedupe pass
   (see references/library-dedupe.md for the regrouper + stub-audit scripts).
   Skip any dir containing live `tmp*.opus` — that's organizer conversion
   in flight.