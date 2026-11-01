# Fleet queue forensics: status, zombies, lane-side cleanup

Read-only first; only cancel/purge/delete what you classified as dead. Ports:
Tidal 19493, slskd 19496 (sidelined lanes 19492/19494 are stopped — entries
pointing there are stale registry, not a queue).

## Reading the queue (three layers)

- Aggregator, public: `GET https://your-domain.example/jobs/unified/json?limit=500` →
  `totals{active,total}`, `services{<lane>:{active,error,total}}`, `jobs[]` with
  id/status/created. `active` = every non-terminal lane job, so one stuck job
  inflates the headline number (a "3 active" panel can be 100% zombies).
- Lane direct: `GET http://IPVPLACEHOLDER:<port>/download/jobs/data?limit=N` (full
  records incl. state, bytes, files, updated_at) and `/download/jobs/summary`
  (per-group counters). Bearer auth.
- slskd ground truth: the daemon itself —
  `curl -H "X-API-Key: <key>" http://IPVPLACEHOLDER:5030/api/v0/transfers/downloads`
  (key in `path-to-credentials`, `api_keys.my_api_key`). A lane job
  with no matching transfer here is lane-side fiction.

## Token discipline

The token the lane accepts is the one in the RUNNING container's env; the
checkout's `.env` can hold an empty/stale value and 401s every call:

```
ENVTOK=$(docker inspect <lane-container> --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^HEADLESS_TOKEN=' | cut -d= -f2-)
```

Never echo the token; compare values via `sha256sum` when you need to prove a
mismatch. A shell-exported `HEADLESS_TOKEN` shadows everything (SKILL.md
pitfall) — `env -u HEADLESS_TOKEN` when in doubt.

## Lane-stall alerts: confirm the wedge before acting

The aggregator's lane-watch classifies a queued row as `frozen_row` when it has
sat queued past the budget (default 900s) with no staging dir — it does **not**
account for queue depth. A legitimate deep batch (hundreds of albums across 8
workers) therefore trips hundreds of false positives while draining normally.

Before treating a stall alert as a wedge, read the lane's
`/download/jobs/stall` and check: `workers.alive` > 0 **and**
`last_activity_age_s` near 0 means the pool is working. A mass `frozen_row` on a
deep queue with a live, active pool is noise — do not restart. A real wedge
shows `workers.alive == 0`, or a silent lane (`last_activity_age_s` >= budget).

## Queue order is LIFO (reverse-dispatch is expected)

`enqueue()` inserts at the FRONT of the worker queue, so the **last**
discography dispatched runs **first**. Seeing the newest batch at the head and
the oldest at the tail is correct behaviour, not a bug. Read
`queue_order.json` in the lane data dir for the real worker order; per-artist
position ranges tell you what is actually next.

## Zombie tells

Non-terminal state for days + `bytes_downloaded: 0` + `updated_at ==
created_at` (+sub-second) + `files: []` + no matching daemon transfer. Duplicate
(peer, path) enqueues are common — when the transfer is gone, both rows are
dead. Confirm magnitudes from the lane DB when the API is awkward:
`/storage/fleet/slskd/data/lane.db` (sqlite; the column is `state`, not
`status`; the `blocked_sources` table holds organizer-gate quarantines).

## Frozen `queued` jobs (worker-pickup race — recover without a restart)

Jobs sit `queued` for tens of minutes, never start, lane log silent, and the
rows show `updated_at == created_at` (nothing wrote after create). Seen
2026-10-05: 2 of 3 albums of one discography batch froze while the third
downloaded fine. Classify with the lane stall surface
(`curl -H "Authorization: Bearer $TOK" http://IPVPLACEHOLDER:19493/download/jobs/stall`)
plus the aggregator's `lane_stall` verdicts: `worker_stalled` = id still parked
in `queue_order.json`; `frozen_row` = popped from the queue and dropped at
worker pickup.

### False-positive pattern: busy lane ≠ stall

A queued job older than the stall budget (default 15 min) does NOT mean the
lane is wedged. When the lane is actively downloading other jobs, a backlog is
normal — especially for large discographies (Bon Jovi's full catalog can queue
78+ jobs behind 8 workers). Before acting on a `frozen_row` alert, check:

1. `workers.alive` in the stall report — 0 = real wedge; 8 = healthy pool.
2. `last_activity_age_s` — if < budget, the lane just wrote; queued jobs are
   waiting their turn, not frozen.
3. Lane log tail — active `Downloading track…` lines prove workers are busy.

The `lane_watch` classifier was fixed (2026-10-13) to only report
`frozen_row` when the lane is silent or the pool is dead. If you see this
pattern recur after a deploy, the classifier regressed — check
`app/search_aggregator/lane_watch.py` `_job_case()`.

Recover each frozen id via pause→resume through the aggregator — resume
re-enqueues into the lane's live queue (no restart; verified 2026-10-05, both
frozen jobs completed and imported):

    curl -X POST http://IPVPLACEHOLDER:19297/jobs/Tidal/<id>/pause
    curl -X POST http://IPVPLACEHOLDER:19297/jobs/Tidal/<id>/resume

Verify: lane log shows `Downloading track…`, row `running` → `completed`,
organizer `DONE` bumps, album lands under `/your-media-path/library/music-library/`.

Fallback for `worker_stalled` when a restart is acceptable (startup recovery
re-queues every queued/running row): from the stack dir,
`docker compose restart tidal-headless` in `/your-stacks-path/fleet`.

The 2026-10-05 root cause (fixed same night): unsynchronized shared-sqlite
reads at worker pickup → InterfaceError / spurious None, and the pickup path
dropped the job with no status write. Pickup misses are now retried and
audited as `job.pickup_miss` in the lane audit_log; if frozen rows recur,
capture the lane log + audit rows before restarting — that is evidence for a
new defect, not a UI hiccup.

## Cleanup sequence (slskd lane)

1. `POST /download/jobs/<id>/cancel` per zombie — flips any non-terminal job to
   `cancelled`. (`delete` alone REFUSES states downloading/queued; `cancel` is
   the door.)
2. `POST /download/jobs/purge` — deletes rows in completed|error|failed|cancelled,
   returns `{"deleted": n}`. Verify `/download/jobs/data` → `[]`.

Tidal lane: terminal jobs are deletable directly — `POST
/download/jobs/<id>/delete` (ids are short hex from `/download/jobs/data`).

## Staging sweep

`/storage/fleet/slskd/<hash>/` = per-job staging (downloaded, pre-organizer).
Finished-import leftovers accumulate there. Before sweeping: confirm the release
already exists in `/your-media-path/library/music-library` under normalized names, check
nothing references the dirs (lane DB `destination`, recent writers), then MOVE
(never rm) to `/your-media-path/junk/<date>-fleet-slskd-staging/`. After a
cross-filesystem move, verify by byte sum
(`find -type f -printf '%s\n' | awk '{s+=$1} END {print s}'`), not `du` — du
reports block/sparse accounting and can look short while every file is intact.

## Reporting shape

Separate "nothing is downloading" from "the UI shows N active": classify each
active row real-vs-zombie with evidence, then close with the aggregator
re-measure (`totals.active == 0`) proving the cleanup.
