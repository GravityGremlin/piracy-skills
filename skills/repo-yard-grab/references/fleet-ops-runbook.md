# Fleet ops runbook

Deep-fleet operations extracted from the grabber's SKILL.md: lane
enable/disable, queue purge, decommission operator pass, and the
pre-trust fleet liveness status check.
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

Never treat a Spotify search result as a download URL.

reat YouTube as a verified last resort, not a lane.

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
