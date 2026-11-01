# Artist discography dispatch (Tidal)

The canonical action for "get the discog for <artist>" is a direct artist
dispatch on the lane (the fleet web UI's Discography button POSTs the same endpoint).
The lane filters and dedups, but the dispatch is NOT guaranteed complete —
run the cross-check below every time.

## Pre-flight

1. `rygrab.py --status` — Tidal must answer `auth=ok`; note queue depth.
2. `rygrab.py --lib "<artist>"` — lists the album dirs the organizer thinks
   the library holds. A dir can hold a single track (a fragment), so
   spot-check `ls "/storage/library/music-library/<Artist>"` and count files
   before assuming an album is present.

## Verify the organizer can actually import before dispatching

A dispatch that resolves fine still lands nothing if the organizer is wedged.
Check both, cheapest first:

- `ls /app/data/queue/DONE | wc -l` twice a few minutes apart (`docker exec
  organizer sh -c ...`). A frozen DONE count with a growing READY count means
  the engine thread is dead — `docker restart organizer` clears it.
- `sudo ls -ld /your-app-data-path/quarantine` must be owned by the organizer's uid (1000).
  If it is `root:root`, every import fails `PermissionError: mkdir
  /your-app-data-path/quarantine/<id>` in `_quarantine_unusable_files` and no album lands.
  Fix the root dir only: `sudo chown your-user:your-user /your-app-data-path/quarantine`.
- A long `beet import` (bulk re-import, another session's `/tmp/run_all.sh`) holds
  `flock(LOCK_EX)` on `library.db`; imports block and lane jobs error with
  `beets organize failed ... organizer enqueue failed: read timeout=5`. Those
  are transient — retry after the bulk job finishes.

## Auth failures stall silently

A lane job can reach `error: "Not connected to Tidal"` and never download, then
disappear from job data once its group purges. The verifier misses these
because nothing landed — there is no library dir to match against.

After every run, scan the lane's `jobs.db` for errored/failed jobs in recently
completed groups, not just the library:

    docker exec tidal-headless python -c "
    import sqlite3,json
    c=sqlite3.connect('/app/data/jobs.db')
    for (d,) in c.execute('select data from jobs'):
        j=json.loads(d)
        if j.get('error') or j.get('status') in ('error','failed'):
            print(j.get('group_id'), j.get('title'), j.get('status'), j.get('error'))
    "

Auth errors mean the whole group died at dispatch time and must be re-dispatched
once `rygrab.py --status` reports `auth=ok`. Never declare a group fully landed
while it has uncanceled errored jobs.

## Completed job is not proof of landing

A job can reach `completed` with `dir=null` while its audio still sits in the
lane's download dir (`/app/downloads/<Artist> - <Album>*` inside
`tidal-headless`) and was never handed to the organizer. Landing is
file-based: `ls "/storage/library/music-library/<Artist>"` plus per-dir `.opus`
counts, stable across two consecutive polls. If a completed job's album is
absent from the library, grep `/app/downloads` inside the Tidal container
for the artist name and re-import or re-dispatch the orphan.

## Artist search caps at 10 — resolve misses by URL

Artist search returns only the top 10 hits ranked by popularity, so legacy or
low-popularity acts never surface, or surface as unrelated modern acts. When
artist search returns the wrong entity or nothing, do not fall back to
candidate #1: resolve a track through the Tidal session to get the `album_id`,
then dispatch by URL:

    rygrab.py --url <album_url> --platform tidal --platforms tidal

(`--platforms` overrides the default lane set; a bare `--platform` does not.)
`/discography` only queues — it cannot enumerate without dispatching. The lane's
resolver function is importable and can list an artist's full Tidal discography
without queuing; use it for gap auditing.

Merged pages: if an artist dir holds titles that do not match the band's known
catalogue (e.g. Rush albums under Strife), the Tidal page is merged with another
act. Trim to the right tracks or resolve by URL instead of the artist page.

## Short artist names resolve to the wrong entity

One-word names are the top source of wrong-artist imports. `Benny` resolves to
**Benny Ibarra** (Latin pop); `Conway` to an unrelated Conway. Dispatch the full
performer name (`Benny The Butcher`, `Conway The Machine`) and read the job
titles back. A bad group cannot be deleted — cancel every job in it
(`POST /download/jobs/<id>/cancel`, ids from the lane's `jobs.db`) and
re-dispatch under the right artist.

## Dispatch

- `env -u HEADLESS_TOKEN python3 <skill>/scripts/rygrab.py --artist "<Artist>"`
- The resolve step prints per-lane `id` + `title`: verify the title matches
the request character-for-character before jobs drain (a wrong entity still
imports and lands under the wrong artist dir).
- The lane replies `{"group_id": ..., "queued": N}`. N is what the resolver
returned, NOT what the provider catalog holds — read the group's jobs to see
what was actually enqueued.
- Lane-side filter (code-read): releases with `num_tracks <= 2` are dropped;
everything larger passes — including EPs and live albums. Default user
preference is **one copy per canonical studio album: lives, comps, EPs and
re-recordings are OUT unless the user explicitly asks for them** (user
profile). So after dispatch, curate the group: cancel non-studio (live/comp/
EP/tribute/re-recording) jobs and edition duplicates (keep the most complete
edition — expanded/deluxe/remaster over base), then let the rest drain.
Cancel via `POST /jobs/tidal/<id>/cancel` (works on queued AND running
jobs); pace at >=2.2s between calls — the aggregator action bucket is 30/min
and a 429 needs a 60s wait + retry. Keep the rare explicit-request case:
if the user says "full discog" or names an EP/live, leave the lane's set
alone.

## Completeness cross-check (the part the lane skips)

The resolver reads the provider's artist-albums listing; `/search/json` reads
search. They disagree in BOTH directions (search surfaces EPs the resolver
misses; the resolver surfaces editions search doesn't list). After dispatching:

1. Group jobs: GET `<lane>/download/jobs/data` (Bearer token), filter
   `group_id == <group>`. Note `id`, `title`, `status` per job.
2. Catalog: GET `<lane>/search/json?q=<artist>&type=album&limit=100`. Filter
   hits by the `artist` field (norm equality) — search returns tribute/
   knockoff matches too.
3. Missing = search hits whose norm title is not in the group and not already
   a library dir. Enqueue each directly:
   `rygrab.py --url <hit.url> --platform tidal --platforms tidal`
   (`--platforms` matters: a bare `--platform` does not override the default
   lane set). Response is `{"job_id": ..., "status": "queued"}` per URL.
4. Scope: auto-enqueue misses that look like bodies of work (EP-size and up,
   typically 5+ tracks). One-song-plus-alternates hits (2–3 trk) are singles —
   leave them out of the auto-set and list them in the report as available.
   Store the search dump to a JSON file under the repo-local `.tmp/` and
   resolve titles from it; never hand-type album names in commands.

## Watch to landing

- Poll `<lane>/download/jobs/data` filtered by `group_id`; terminal states are
  `completed` / `failed` / `cancelled`. Log any failed job's `error`
  immediately — do not wait for the drain to finish to notice it.
- Lanes purge finished groups fast: once the group vanishes from job data,
  verify by library files, not job status.
- Big catalogs run 1h+; run the poll loop as a background watcher with
  notify (snapshots to a log under the knowledge repo `.tmp/`), not as a blocking
  sleep loop in the session.
- Landing check: `ls "/storage/library/music-library/<Artist>"` plus per-dir
  `.opus` counts; stable counts across consecutive polls = done. The
  organizer files by beets tags, so count files, don't trust dir names alone.

## Report shape

Report: dispatched set (title / year / type), what the lane's resolver added
beyond search, singles left out (with an offer), and finish only after the
landing check — never end the task at "jobs queued".


## Historical note: queue caps count jobs, not tracks

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



## Historical note: queue caps count jobs, not tracks

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

