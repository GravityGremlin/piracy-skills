# Verifying a track download across the downloader fleet

Use when the user asks whether a specific track/album landed in the library.

## Where to look (order of speed)

### 1. Library filesystem (fastest, authoritative)

```bash
find "/your-media-path/library/music-library" -iname "*artist*" -type d 2>/dev/null
find "/your-media-path/library/music-library" -iname "*trackname*.opus" 2>/dev/null
```

The organizer files by beets-derived tags, not the requested title — search by
both artist AND track name, as separate globs.

### 2. Lane queues (still in flight)

```bash
TOKEN=$(grep '^HEADLESS_TOKEN=' path-to-credentials | cut -d= -f2)
for port in 19492 19493 19494 19496; do
  curl -s -m 5 -H "Authorization: Bearer $TOKEN" \
    "http://IPVPLACEHOLDER:$port/download/jobs/summary" | python3 -c "..."
done
```

Check each lane's `/download/jobs/summary` for queued/running/error groups
matching the artist or track.

### 3. Organizer queue (staging/beets processing)

```bash
TOKEN=$(grep '^FLEET_ORGANIZER_TOKEN=' path-to-credentials | cut -d= -f2)
curl -s -m 5 -H "Authorization: Bearer $TOKEN" \
  'http://IPVPLACEHOLDER:19298/queue/status'
curl -s -m 5 -H "Authorization: Bearer $TOKEN" \
  'http://IPVPLACEHOLDER:19298/queue/data?status=FAILED&limit=20'
```

- `/queue/status` → `READY`, `PROCESSING`, `DONE`, `FAILED` counts.
- `/queue/data?status=FAILED` → inspect failed job details (error messages).

### 4. Staging directories (orphaned/stalled)

```bash
find /storage/fleet -path "*/import_staging/*" -iname "*artist*" 2>/dev/null
find /your-app-data-path -path "*/import_staging/*" -iname "*artist*" 2>/dev/null
```

Lane container path `/app/import_staging/<X>` maps to host
`/your-app-data-path/<tool>/import_staging/<X>`.

### 5. Docker volume for organizer data

The organizer DB lives in a Docker volume (`fleet_organizer-data`):
```bash
docker volume inspect fleet_organizer-data 2>/dev/null
# → Mountpoint: /var/lib/docker/volumes/fleet_organizer-data/_data
sqlite3 <mountpoint>/organizer.db "SELECT title,artist,status FROM jobs WHERE artist LIKE '%...%' LIMIT 20;"
```

## Queue status is not landing proof (measured false-positive class)

The organizer's landing proof is a heuristic. `reason=gated_import_landed`
comes from the beets DB census (target-name guarded) or a byte-size fallback,
and `reason=already_in_library_gated` is a SKIP that imports nothing at all.
Measured 2026-10-17 (Stick - Heavy Bag): the byte-size fallback returned true
on ONE coincidental size match — the staged `06 Zero.mp3` equalled an unrelated
`Suicidal Tendencies/13/11 - Living the Fight.opus` — so the job went DONE,
its staging was deleted, the quarantine/FAILED path was skipped, and the album
was never imported (`Stick/` held only the other album; the beets DB had no
`Heavy Bag` row). The fallback now demands a FULL-set match (fleet
c053e19), but the census can still mis-fire: a `done` row is a claim to verify,
not a result.

Verify by content, in this order:

```bash
ls "/your-media-path/library/music-library/<Artist>/<Album>"          # on disk
sqlite3 /your-stacks-path/beets/config/library.db \
  "select albumartist, album, count(*) from items where album like '%<Album>%' group by 1,2;"
```

Recovery when DONE was a false positive: the staging copy is already deleted,
so re-fetch the source (slskd complete dirs often survive under
`/storage/slskd/complete/<Album>/`; otherwise re-dispatch the album) and
re-import per `references/manual-beets-import.md`. The peer's original share
dir is often still searchable — fire a FRESH search rather than re-reading an
old response dump (dumps go stale: "peer offline, or the search window
closed").

## Common findings

- **Organizer says DONE but the album is not on disk** → false landing proof,
  staging already deleted. Re-fetch and re-import (see the section above).
- **Not in library, not in any queue** → never dispatched, or job was
  purged after completion. Ask user to re-dispatch.
- **In library, different artist/album dir** → beets filed it by embedded
  tags, not request title. Normal.
- **In staging, lane queue empty** → drain stalled. Copy to quarantine or
  re-enqueue.
- **In FAILED queue** → check error; retry via group API or re-dispatch.