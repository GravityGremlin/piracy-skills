---
name: peertube-ops
description: "Use when debugging PeerTube imports, syncs, stuck videos."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [peertube, docker, yt-dlp, debugging]

---

# PeerTube Ops

Operating a self-hosted PeerTube instance: imports, channel syncs, transcoding, stuck videos.

## Layout & access

- Config: `/path/to/peertube/config/local-production.json` (active; same volume as /config in-container). Backups as `*.bak-*` alongside.
- DB: `docker exec peertube-postgres psql -U <user> -d peertube` — schema is quoted camelCase ("videoImport", "videoChannelSync"); timestamps are timestamptz, NOT epoch millis.
- yt-dlp: `/data/bin/yt-dlp` in-container, auto-updates itself (check `--version` before blaming it).
- Channel sync state: `videoChannelSync.state` 3=SYNCED, 4=FAILED.
- Import state: `videoImport.state` 3=failed, 6=waiting; 2=PROCESSING (rows stuck at 2 with videoId NULL = dead processing, reset to 1=PENDING to re-run).

## Videos not showing (lost follows)

If browse/discover/API listings return 0 videos while the DB has published rows, the likely cause is **LOST FOLLOWS**, not storage or the queue. Listings only include local videos or videos shared by a followed actor.

**Signature:** list `total: 0` but direct `/api/v1/videos/<uuid>` returns 200.

**Recovery:** re-follow servers (videoShare rows survive). Steps:
1. Identify followed actors missing: `SELECT * FROM "videoChannelFollow" WHERE "followingActorId" IN (...)`
2. Re-follow via API or direct DB insert into `videoChannelFollow`
3. Trigger resync: `POST /api/v1/server/followers/sync` or wait for next cron

## Stuck imports / transcodes

**Stuck at PROCESSING (state=2, videoId=NULL):**
```sql
UPDATE "videoImport" SET state = 1 WHERE state = 2 AND "videoId" IS NULL;
```

**Failed transcodes (state=3):**
```sql
SELECT * FROM "videoImport" WHERE state = 3;
-- Check logs for ffmpeg errors, then reset to PENDING (1)
UPDATE "videoImport" SET state = 1 WHERE id = '<uuid>';
```

**Channel sync FAILED (state=4):**
```sql
SELECT * FROM "videoChannelSync" WHERE state = 4;
-- Inspect "lastSyncError", fix root cause (usually yt-dlp version or private video), reset:
UPDATE "videoChannelSync" SET state = 1 WHERE id = '<uuid>';
```

## yt-dlp issues

- Check version in-container: `docker exec peertube /data/bin/yt-dlp --version`
- Test a failing URL directly: `docker exec peertube /data/bin/yt-dlp -v "https://youtube.com/watch?v=..."`
- Common fixes: update yt-dlp (`docker exec peertube /data/bin/yt-dlp -U`), add cookies for age-gated/private, adjust format selector in config (`ytdlFormatSelector`)

## Log retention caveat

Docker daemon log rotation (`max-size`, `max-file`) limits retained logs. Never say "since forever" — anchor stats to `--since` or first/last log timestamps. If history is disputed, it may simply not exist.

## Verification checklist

- [ ] `videoChannelSync` states: all SYNCED (3) or explained FAILED (4)
- [ ] `videoImport` states: no stuck PROCESSING (2 with NULL videoId)
- [ ] API listings return videos for followed actors
- [ ] yt-dlp version current, test URL works
- [ ] Transcode queue draining (no backlog > 24h)