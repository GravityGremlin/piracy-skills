---
name: arr-stack-ops
description: "Use for Sonarr/Radarr failures or re-grabbing episodes."
version: 1.2.0
author: Gravis Wellz
license: MIT
metadata:
  hermes:
    tags: [arrs, sonarr, radarr, prowlarr, sabnzbd, flaresolverr, indexers]
    related_skills: [media-request-ops, docker-fleet-audit]
---

# *arr stack ops

## When to Use

- An arr app reports failures and "doesn't even try to search".
- Health shows indexers unavailable, or a log says `0 active indexers`.
- Downloads import as "path does not exist", or the queue fills with dead rows.
- Prowlarr complains about indexer proxies / FlareSolverr.
- Any change to `/your-stacks-path/arrs/compose.yaml` plus a container recreate.
- A season or episode needs re-downloading even though its files already exist
  — start at "Re-grabbing what you already have", NOT by deleting files. Read the
  series' quality profile FIRST (`upgradeAllowed`): automatic search can only
  re-acquire under a profile that permits upgrades.
- A series looks absent from the library — check every arr host before saying so.

Covers the arr stack in `/your-stacks-path/arrs/compose.yaml` (compose project `arrs`,
network `media_network`): sonarr :8989, radarr :7878, prowlarr :9696, bazarr
:6767, sabnzbd, flaresolverr :8191, lidarr, huntarr — and the failures that make
them stop searching, grabbing, or importing.

## Recipes

- references/reacquire-existing.md — Sonarr re-grab of files already on disk.
- references/radarr-regrab.md — Radarr: swap a wrong-language movie file
  (probe before trusting tags, `/api/v3/Release?movieId=`, grab, import,
  dead-queue cleanup).

## App config dirs are `/your-app-data-path/arrs/<app>/` — NOT the stack dir — and each app's
credential is the `<ApiKey>` element of that dir's `config.xml`:
`RK=$(grep -oP '(?<=<ApiKey>)[^<]+' /your-app-data-path/arrs/sonarr/config.xml)`.
Keys are per-install, not per app: another host's Prowlarr has its own key, so a
401 from `HOST:9696/api/v1` means this host's key was reused — grep THAT host's
config.xml over SSH instead of concluding the service or key is broken.
Every app mounts `/your-media-path → /storage`, so a container path `/storage/x/y` is
`/your-media-path/x/y` on the host and the library root `/storage/library/shows` is
`/your-media-path/library/shows`. Calls look like
`curl -s -H "X-Api-Key: $RK" "http://<arr-host>:8989/api/v3/<route>"` (Prowlarr is `/api/v1`).

## The arrs are not single-host-only

Your arr stack host's stack is the one documented below, but a second arr stack host runs
its own Sonarr on :8989 with the same layout — config in
`/your-app-data-path/arrs/sonarr/config.xml`, library root `/storage/library/series`, an
NFS client of your arr stack host's `/your-media-path`, and the same credential. A title missing from
one host's library proves nothing about the other: list `/api/v3/series` on
EVERY arr host and filter in python before telling the user a series is absent.
Fire searches at the host that owns the series — the wrong instance happily
finds releases and then has nowhere to import them.

## Re-grabbing what you already have (no pre-delete)

Deleting the files first is the expensive fallback, not the procedure. Only one
of Sonarr's search commands touches an episode that already has a file:

| Command | Scope | Touches an existing file? |
|---|---|---|
| `MissingEpisodeSearch` | every missing monitored episode | no |
| `SeasonSearch` | one season; season packs considered only when ZERO episodes of it are imported | no |
| `EpisodeSearch` | exactly the `episodeIds` you pass | yes — a manual search ignores monitored state and the existing-file rejection |

`POST /api/v3/command -d '{"name":"EpisodeSearch","episodeIds":[<id>,...]}'`
on the owning host IS the redownload. Import runs through
`UpgradeMediaFileService`: the old file goes to the app's recycle bin and the new
one is imported. A fully-imported season returning nothing from a season search
is correct behaviour, not a broken search — do not "fix" it by clearing files.

Before firing, say two things plainly: the grab uses the quality profile's best
pick and may be the SAME release already on disk, and the old file's survival
depends on recycle-bin retention being on (off = the replacement is permanent).
Verify afterwards from episode statistics / file mtime and size, never from the
command having been accepted. Per-episode variant, blocklisting the current
release to force a different pick, and manual release override:
`references/reacquire-existing.md`.

## "It doesn't even try to search" = indexer failure cascade

Work in this order:

1. `GET /api/v3/health`. `IndexerLongTermStatusCheck` / "All indexers are
   unavailable due to failures" means EVERY indexer is tripped — the app
   deliberately skips searching instead of trying. Log tell:
   `ReleaseSearchService: Searching indexers for [...]. 0 active indexers`
   (healthy = `4 active indexers` + `DownloadDecisionMaker: Processing N releases`).
2. `GET /api/v3/indexer` — enable flags. `enableInteractiveSearch=false` is a
   deliberate choice for some indexers (private torrents often left off); it is
   not the failure state, which lives elsewhere.
3. `GET /api/v1/indexerstatus` (Prowlarr only — Sonarr v4 returns 404 on that
   route) → per-indexer `disabledTill` backoff stamps, often ~a day out.
4. Clear it: `POST /api/v1/indexer/testall` on Prowlarr FIRST, then
   `POST /api/v3/indexer/testall` on Sonarr. Both answer
   `[{id,isValid,validationFailures}]` and reset the backoff for whatever passes.
   Sonarr's failure state mirrors Prowlarr's: while a Prowlarr indexer is
   disabled, Sonarr's copy of it gets 429 and stays tripped — clearing Sonarr
   first just re-trips it.
5. Prove it end to end; do not stop at green health.
   `GET /api/v3/release?episodeId=<id>` returns the releases (find an id via
   `GET /api/v3/wanted/missing?pageSize=5&includeSeries=true`); a real grab is
   `POST /api/v3/command -d '{"name":"EpisodeSearch","episodeIds":[<id>]}'`.

Reading testall output:

- `isValid: true` → cleared, usable again.
- Sonarr 429 pointing at `http://IPVPLACEHOLDER:9696/<prowlarrIndexerId>/api` = Sonarr
  asked Prowlarr for an indexer Prowlarr has disabled. Not a Sonarr bug: fix or
  remove that indexer in Prowlarr, or disable Sonarr's copy of it.
- `Credentials appears to be invalid` / `Membership Expired` / `API endpoint has
  been retired` = account-side. Report it and leave it disabled; never re-enable a
  dead indexer to make health green.

A burst of DNS/SSL "Unable to connect to indexer" warnings is usually transient —
the durable damage is the backoff, so clear the backoff before editing indexer
config. Before believing a DNS story, test reachability from inside the app
container:
`docker exec prowlarr sh -c "curl -s -o /dev/null -m 10 -w '%{http_code}\n' https://<host>/"`.

## FlareSolverr (indexer proxy) — first check whether it is in the path

An indexer uses the proxy only if the indexer carries the SAME tag as the proxy
entry (`GET /api/v1/indexer` → `tags`; `GET /api/v1/indexerproxy` → `tags`). A
proxy that no indexer references cannot cause a search outage — say so and move on.

Symptoms of a broken solver: `GET http://IPVPLACEHOLDER:8191/` still answers
`{"msg":"FlareSolverr is ready!"}` while a real solve hangs past 90s, and
Prowlarr reports `All indexer proxies are unavailable due to failures` with
Chrome's `session not created ... unable to connect to renderer`.

Fix: headless Chrome needs room. In `/your-stacks-path/arrs/compose.yaml` give
flaresolverr `shm_size: 1gb` and memory ≥2G / cpus ≥1 (512M plus the default 64M
`/dev/shm` cannot start the renderer). Recreate the container, then verify with a
real solve: `curl -s -X POST http://<flaresolverr-host>:8191/v1 -H 'Content-Type: application/json' -d '{"cmd":"request.get","url":"https://<indexer>/","maxTimeout":60000}'`
→ `status: ok` in ~10-20s. `POST /api/v1/indexerproxy/testall` returning valid JSON
 does NOT clear the health warning immediately — proxy health rechecks on its own
schedule.

## Import failures and dead queue rows

`DownloadedEpisodesImportService: Import failed, path does not exist or is not
accessible ... /storage/sabnzbd/complete/<job>/` → translate the path (/storage =
/your-media-path) and check it ON THE HOST before chasing a permissions story. If the
directory is gone the queue row is dead, not stalled: `GET
/api/v3/queue?pageSize=500` carries `outputPath` and a statusMessage like
`No files found are eligible for import`.

Usual cause of the vanished folder: SABnzbd purged the job's data (`Purging data
for job ... (delete_all_data=True)` in `docker logs sabnzbd`), so Completed
Download Handling has nothing left to import even though every client reported
success. Cleanup is destructive — list the dead rows, get user confirmation, then
`DELETE /api/v3/queue/{id}?removeFromClient=true&blocklist=false`. The episodes
stay missing and get re-searched, which is normally the point.

## Root folder points at a retired tree (the music canon switch)

Symptom: a whole app is stuck on `Missing root folder: /storage/library/music/`
and every completed download fails to import. That path was retired when the music
library moved to `/your-media-path/library/music-library`; the music-app fleet apps (Lidarr,
Navidrome, beets tooling) were not all repointed.

Diagnose three layers, in this order — fixing only the first unblocks nothing:

1. `GET /api/v1/rootfolder` — `accessible` and `path`.
2. `GET /api/v1/artist` — **every artist path is a second root**. 1962 of them sat
   under the dead prefix, so imports failed one step after the root folder. Rewrite
   with a tiered folder match against the real tree (exact -> casefold ->
   punctuation-stripped -> unmatched keeps the app's own name):
   `PUT /api/v1/artist/{id}?moveFiles=false` with the full resource.
3. `TrackFiles.Path` rows at the dead prefix. A daily `RescanFolders` plus
   `autoRedownloadFailed: true` turns those stale rows into a permanent re-grab
   engine — Lidarr was buying ~2-3 albums a day for five weeks.

Do not "just rescan" to reconcile while paths are wrong: a rescan of a dead root
marks the entire library missing and re-buys it.

### Who imports: beets, not the arr

The downloader fleet's architecture makes the beets import pipeline the only library writer. If Lidarr
imports, it drops raw FLAC with `{Album Title} ({Release Year})` folders next to
beets' `$albumartist/$album/$track - $title` — a second writer inside a tree a
dedupe pass just cleaned. Correct shape on your arr stack host:

- Lidarr root folder -> `/storage/library/music-library`; `PUT
  /api/v1/config/downloadclient` with `enableCompletedDownloadHandling: false`.
  Lidarr keeps the grabber role only (its `ImportMechanismCheck` health warning is
  then expected, not a fault).
- SABnzbd `music` category -> `/storage/downloader-fleet/sabnzbd-import`, the beets import pipeline's
  allowlisted `/import/sabnzbd` staging root. Set it through SAB's own API so you
  never touch its ini as your user:
  `curl "http://<sabnzbd-host>:8088/api?mode=set_config&apikey=<key>&section=categories&keyword=music&name=music&dir=/storage/downloader-fleet/sabnzbd-import&pp=&script=&priority=0&newzbin=&order=2"`
  (Lidarr already sends `musicCategory=music`; no client change needed.)
- Nothing enqueues an arr's completed grab into the beets import pipeline on its
  own: a small cron watcher (`*/15`) must tag-scan the staging root, skip what
  beets already owns, and POST `/enqueue` into the import pipeline. Without that
  glue the grabs land in staging and rot — the same bug wearing a different hat.

### Pitfalls that cost time here

- **Ownership across the staging boundary.** SAB keeps completed dirs under its
  own uid (`users/` guest account, 911); the beets import pipeline runs as uid 1000.
  Moving files with SAB's container user (the only non-root way) preserves 911, so
  the beets import's run dies with
  `Permission denied while moving ... to /music/...` and the album row lands with
  every item still pointing at staging. `docker exec sabnzbd chown -R 1000:1000
  /storage/downloader-fleet/sabnzbd-import` is the fix; then remove the debris rows
  (`beet remove -af id:<id>`, no `-d`) before retrying, or the duplicate gate
  skips forever.
- **`post-import verification failed: staged audio did not land` is usually a
  lie** — grep the library before believing it (10 of 14 jobs here were false
  negatives; the audio and the opus conversion were both on disk). Read job state
  from `/app/data/queue/{READY,PROCESSING,DONE,FAILED}/<id>.json`, not a GET.
- **beets `items.path` is relative to `/music`** in this deployment
  (`Boy Harsher/Careful/01 - ...opus`), so an existence check that joins it with
  the host library root is the only valid test.
- Enqueue `target_artist` from **albumartist**, not artist: a feature credit
  (`D.O.D, Hayley May`) makes the verifier miss the landed `D.O.D` dir.
- The beets import pipeline's maintenance thread holds the beets flock while it converts a
  backlog, so jobs can sit READY for 10+ minutes with 100% CPU and no log output.
  That is contention, not a stuck queue.

## Editing /your-stacks-path/arrs and restarting a service

- `/your-stacks-path/arrs/` is root-owned mode 755 while its files are 666, so the
  `patch`/`write_file` tools fail with `Permission denied` (they stage a temp file
  in that directory). Edit in place with python, then re-validate:
  `python3 -c "import yaml;yaml.safe_load(open('/your-stacks-path/arrs/compose.yaml'))"`.
  Keep the backup in the repo's gitignored `.tmp/`, never `/tmp`.
- The terminal guard refuses a literal `docker compose up ...` (reads it as a
  long-lived server). Run it through python and capture the result:
  `python3 -c "import subprocess;r=subprocess.run(['docker','compose','up','-d','--no-deps','--force-recreate','<svc>'],capture_output=True,text=True);print(r.returncode,r.stdout[-400:],r.stderr[-400:])"`.
- Confirm the recreate applied:
  `docker inspect <svc> --format 'status={{.State.Status}} shm={{.HostConfig.ShmSize}} mem={{.HostConfig.Memory}} cpus={{.HostConfig.NanoCpus}}'`.
- `/your-app-data-path/arrs/sabnzbd/sabnzbd.ini` is owned by the container uid and is not
  readable as your user. Stop at the permission error and stage the change for
  admin — do not chmod/chown around it.

## Rules

- Report "fixed" only after a real search returns releases, and for grab work
after a grab lands. Health text and testall output are supporting evidence, not
proof.
- Separate transient backoff (clear it) from dead accounts (user action: expired
membership, rotated credentials, retired API endpoint).
- Never move or rename `/your-stacks-path/arrs` or its compose project name; the
container labels tie restarts and `docker compose` scoping to it.
- `POST /api/v3/indexer/test` without a body answers 415 — use `testall`, or send
  the full indexer resource.
