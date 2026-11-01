# Organizer staging-root allowlist

Every lane that stages downloads into a directory the organizer imports from
must have that directory BOTH in the organizer's `ORGANIZER_STAGING_ROOTS`
(a comma list) AND mounted into the organizer's `volumes:` in the prod override
(`compose.prod.yaml`). Base `compose.yaml` mounts a lane's staging dir for the
lane's OWN service — that does not make it visible to the organizer, and the prod
override replaces the organizer's env block wholesale (`!override`), so a root
expected only in the base file is silently absent in prod.

## Symptom

Downloads land and complete (files fully transferred to the lane's staging dir),
but the grab's import never proceeds. The lane's enqueue loop is rejected:

```
organizer enqueue HTTP 422: source_path escapes staging/queue root:
resolved to /storage/fleet/slskd/<group>, not under /your-app-data-path,
/import/sabnzbd, /storage/fleet/tidal/import_staging,
/storage/fleet/qobuz/import_staging
```

The lane retries the enqueue forever (~every 1.5 s), so the jobs never finalize
and no re-download is needed once the config is fixed.

## Lane staging paths

| lane | staging dir |
|---|---|
| default | `/your-app-data-path` |
| sabnzbd | `/import/sabnzbd` |
| tidal | `/storage/fleet/tidal/import_staging` |
| qobuz | `/storage/fleet/qobuz/import_staging` |
| slskd | `/storage/fleet/slskd` |

`/storage` is the container-side name for the NFS tree; the host path is
`/your-media-path`, so the mount is
`/your-media-path/fleet/slskd:/storage/fleet/slskd` (match the sibling lane
mounts — do not add `:ro`, the sibling imports are read-write and cleanup may
unlink staged files).

## Fix

1. In `compose.prod.yaml`, append the missing root to `ORGANIZER_STAGING_ROOTS`
   and add the matching `volumes:` line to the `organizer` service.
2. Validate: `docker compose -f compose.yaml -f compose.prod.yaml config` and
   confirm the env value renders with the new root.
3. Commit → push → deploy per the repo's push discipline (the compose edit and
   any Dockerfile changes are ONE atomic unit).
4. Recreate the organizer so the mount/env take effect; the staged grabs then
   import without re-downloading.

## "post-import verification failed: staged audio did not land"

Do not treat it as a broken import. Three causes, in order of frequency:

1. **Beets incremental history** — the exact source path is in
   `state.pickle` `taghistory`, so beets prints `Skipped 1 paths` and exits 0
   without importing anything. See the section below.
2. **Duplicate / stale DB row** — beets says `This album is already in the
   library! Skipping.` This fires on the DB row alone, even when the row's
   item paths no longer exist on disk, so a half-imported album blocks its own
   repair. Confirm with:
   `select i.path from items i join albums a on a.id=i.album_id where a.album like '%<album>%'`
   plus a filesystem existence check under `/music`.
   If every listed path is missing, the row is debris from an interrupted
   import: drop it so the duplicate gate stops firing, then re-enqueue.
   Back up `library.db` first, then
   `BEETSDIR=/app/.config/beets beet -c /app/.config/beets/config.yaml remove -af id:<album_id>`
   (`-a` album, `-f` no prompt, no `-d` so nothing is deleted from disk).
   Re-verify the albums/items count for that title is zero before enqueueing —
   a surviving row means the remove silently matched nothing.
3. **Edition mismatch** — a Tidal edition with a different track count than
   the copy on disk makes the job look like a partial download when it is
   really "already owned".
4. **Retag identity mismatch (provider lane)** —   autotag landed the album
   under a different artist credit than the dispatch sent (single artist →
   `"Dope D.O.D."` becomes `"Dope D.O.D., Onyx"`; a year suffix may be added),
   so the verifier's dir match misses an import that worked. Check
   `ls -d /your-media-path/library/music-library/*/*"<Album>"*` before believing the
   error; if the audio is there, force the job DONE instead of re-importing —
   and do not loosen `_landed_dir_matches` to "fix" it (that guard is what
   stops a sibling job certifying another job's landing).

## Silent skip: beets incremental taghistory

The provider beets config (`/app/.config/beets/config.yaml`; the separate
`ORGANIZER_BEETS_GATED_CONFIG` serves untrusted sources) sets
`import.incremental: yes`, and beets records
every imported/skipped source path in `$BEETSDIR/state.pickle` under
`taghistory`. A path that was attempted once (even when the import failed or
the files were later deleted) is skipped forever afterwards, with no error:
`beet import -p <dir>` prints `No files imported … Skipped 1 paths`.

Diagnose inside the container:

```
docker exec organizer python -c "
import pickle; d=pickle.load(open('/app/.config/beets/state.pickle','rb'))
print(len(d.get('taghistory') or []))
print([t for t in (d.get('taghistory') or set()) if any(b'<album>' in p for p in t)])"
```

Fixes, cheapest first: re-stage the album under a NEW path (bypasses the
history entry), prune just that tuple from `taghistory` (back up
`state.pickle` first), or turn `incremental` off for that run — duplicate
detection already covers the re-import case it was guarding. Never conclude
"the audio is bad" from a silent skip; check the history first.

## Bulk re-import of an orphan staging tree

Work the whole tree through the organizer — it is the single library writer;
do not run `beet import` against the live DB by hand.

1. Triage each album dir against the library (normalize names, strip the
trailing `(YYYY)`, fuzzy-match artist at ≥0.86 then album at ≥0.86) and
   against the beets DB: `no row` / `row with all items missing` /
   `row partially on disk` / `row complete on disk`. Skip the complete ones.
2. Enqueue the rest, one POST per album:

```
POST http://IPVPLACEHOLDER:19298/enqueue
Authorization: Bearer <ORGANIZER_TOKEN>
{"source_path": "/your-app-data-path/tidal/import_staging/<Artist> - <Album> (YYYY)",
 "target_artist": "<Artist>", "target_album": "<Album>", "priority": 2}
```

A missing bearer returns `{"error":"Unauthorized"}`; the token is the
`ORGANIZER_TOKEN` in `docker inspect organizer --format '{{range .Config.Env}}…'`.
`/enqueue` is fire-and-forget (`201 {id, status: "READY"}`) and there is no
`GET /queue` — read state from the queue directories.

3. Monitor `READY / PROCESSING / DONE / FAILED` counts in
   `/app/data/queue/`: the organizer batches ~20 albums into a single `beet
   import` invocation, so DONE can sit at 0 for many minutes while album dirs
   are already appearing under `/music`. Expect ~45–60 s per album at steady
   state. A container restart loses nothing (queue files are on disk) but
   re-runs the in-flight batch. An already-imported album returns HTTP 422 —
   treat that as "done", not as a failure.

Count queue files with `find`, never `ls | wc -l`, when the command is nested
inside `ssh … docker exec sh -c '…'`: the quoting collapses the glob and `ls`
errors into `2>/dev/null`, yielding a confident `0`. Use:

```
docker exec organizer sh -c 'for s in READY PROCESSING DONE FAILED; do
  printf "%s=" $s; find /app/data/queue/$s -maxdepth 1 -name "*.json" -printf "." | wc -c; done'
```

A zero DONE count measured that way is a measurement bug until proven
otherwise — spot-check `/music` for freshly created album dirs first.

When the tree has drained, retire the old FAILED records instead of leaving
them to poison later reads. Most of them are pre-fix artifacts for albums that
now import cleanly under the same `source_path`; count how many FAILED
`source_path`s match a just-imported DONE job before deciding. Move, never
delete:

```
docker exec organizer sh -c "mkdir -p /app/data/queue/FAILED.retired-$(date -u +%Y%m%d-%H%M%S) &&
  mv /app/data/queue/FAILED/*.json /app/data/queue/FAILED.retired-<ts>/"
```

Spot-check the survivors first: a FAILED entry whose audio is already in the
library (retagged credit, singleton import) is resolved, not a bug to chase —
see the retag case above.

A queue that looks frozen (`READY` unchanged, `PROCESSING` at 0, no scheduler
log lines) is usually not stalled: the organizer interleaves a whole-library
maintenance pass (beets path sync + ffmpeg opus backlog) between batches. Check
for live `beet`/`ffmpeg` processes and CPU before declaring a hang; batches
resume when the pass ends.

Give the organizer room: a 20-album beets batch holds the whole batch in
memory and 1 GB OOM-kills it. Run it at 4 GB / 4 CPUs, applied live with
`docker update --memory 4g --memory-swap 4g --cpus 4 organizer` (no restart,
in-flight batch survives) and persisted in `compose.prod.yaml`'s organizer
`deploy.resources.limits`. The host has dozens of GB and threads; the
organizer is the fleet's only library writer, so starving it just serializes
the queue.

## Path migrations leave orphan staging trees

When a lane's staging mount moves (e.g. `/your-app-data-path/tidal/import_staging` →
`/storage/fleet/tidal/import_staging`), the old tree keeps COMPLETE
untouched audio that will never import, and the queue fills with failures whose
`source_path` all share the old prefix. Distinguish this from N broken albums:
one prefix = one root problem.

Trust the running container, not the compose files — `compose.prod.yaml` and
`compose.yaml` can disagree, and only the applied config matters:

```
docker inspect tidal-headless --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

If nothing mounts the old directory, the audio there is orphaned. Triage it
against the library by album before acting, and never delete under
`/your-media-path` (or a `/storage` view of it) without explicit user confirmation.

## Pitfall when fixing

Do NOT recreate the organizer while a bulk beets re-import is running inside it
(a `docker exec organizer … beet import` job): recreating the container kills
that process. Wait for the import to finish (watch the DB item count) before
recreating to apply the staging-root change.
