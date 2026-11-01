# Playlist Import Workflow — Full Trace & Failure Modes

End-to-end path for a Tidal (or other provider) playlist import, with
file:line citations into the prod checkout (`/your-stacks-path/fleet`).

## 1. The flow

```
UI: paste playlist URL
  │
  ▼  app/search_aggregator/aggregator.py — dispatch to owning lane
Tidal /playlist/routes.py:173  POST /download
  │  decomposes playlist into N × kind="track" jobs
  │  each job.data = {playlist_name, playlist_order}
  │  shared group_id
  ▼
tidal /download/controller.py:255  enqueue(job_id)
  │  each track downloads individually
  ▼
tidal /download/controller.py:667  _beets_organize_job()
  │  groups files by album dir
  │  controller.py:688-700 — builds playlist dict:
  │    {name, tracks: [{file: basename, order: int, title: str}]}
  │  passes playlist= to beets_import_album()
  ▼
core/.../beets_integration.py:60  beets_import_album()
  │  stages files → POST /enqueue with playlist field
  ▼
organizer/app.py:481  Manifest(playlist=playlist)
  ▼
organizer/engine.py:1666  run_once() — claim, import, verify
  │  line 1746  _verify_imported_album()
  │  line 1807-1811  → _mirror_playlist(job)
  ▼
organizer/engine.py:1192  _mirror_playlist()
  │  FICLONE reflink library copy → /playlists/<name>/NN - <library_name>
  │  btrfs cross-mount clone; falls back to copy2 on non-btrfs
  │  best-effort: failures log, never fail the import
  ▼
/your-media-path/library/playlists/<name>/01 - Track.opus  (hardlink/reflink)
```

version: 1.1.0

## 2. The three mirror call sites

| Call site | Trigger | Meaning |
|---|---|---|
| `engine.py:1516` | `link_only` job | Tool confirmed track already in library; mirror only |
| `engine.py:1592` | `already_in_library` | Pre-import dedup found it; mirror only |
| `engine.py:1807-1811` | **Normal import success** | beets imported new files; mirror the copies |

The normal-import path is the one that matters for most playlist work. The
other two are safety nets for tracks the tool already had.

## 3. Failure-mode table

| Symptom | Root cause | Diagnose |
|---|---|---|
| `/playlists` empty, no playlist jobs | UI/frontend never sent the playlist download request | Check lane `/download/jobs/data` for `playlist_name` in job data |
| Jobs exist but stuck in lane queue | Lane can't connect to provider or track download failing | Check lane job status; grep for `job.error` in lane logs |
| Jobs COMPLETED but `/playlists` empty | `_mirror_playlist` ran but `_match_library_file` couldn't find library copies | Grep organizer logs for `playlist mirror: no library match` |
| Jobs COMPLETED, library populated, `/playlists` empty | Staging basename ≠ library filename (beets renamed during import) | Compare staging dir names vs library tree; grep for `no library match` |
| Tracks landed in `/playlists` but wrong order | `playlist_order` missing or 0 in job.data | Check job data in lane DB; all orders default to 0 → all named `01 -` |
| Mirror created empty subdir | Playlist name sanitized to empty → `_safe_playlist_dir_name` returns "playlist" | Check for a `/playlists/playlist/` dir |
| Mirror worked but files are full copies | Non-btrfs filesystem (FICLONE unavailable) → copy2 fallback | Expected on non-btrfs; check `df -T` |
| the fleet web UI playlist import fails | Aggregator `/dispatch` validator rejected kind=playlist (400). Fixed 2026-10: added "playlist" to accepted kinds — `fleet_dispatch` already routes it. | `curl -X POST /dispatch -d 'kind=playlist'` should return 200 now |
| Playlist files quarantined | **Misdiagnosis**: empty staging dir after beets `move: yes` consumed files → `_quarantine_unusable_files` returns `remaining=False` → engine logs "all files quarantined — marking DONE" even though nothing was actually quarantined. The real import may have succeeded. Fixed: `staging_consumed` branch distinguishes empty-staging from all-quarantined. | Grep organizer logs for `quarantine:` (actual file moves) vs `all files quarantined` (mislabel). Check if files already landed in library: `find /your-media-path/library/music-library/ -name '<track>'`. Quarantine dirs are created unconditionally per job — empty dir ≠ quarantine. |
| Playlist import FAILED after retries | Multi-album playlist bag forced through one album-mode beets import → lands as compilation album (`Various Artists / …`). Fixed: download_playlist writes per-album subdirs; controller splits into per-album organizer jobs. | Grep organizer logs for `post-import verification failed: staged audio did not land`. Check if tracks landed under `Various Artists/` instead of per-artist dirs. |
| Mirror can't find tracks after successful import | `_mirror_playlist` only searches `target_artist/target_album` dir. Fixed: `_match_library_file_anywhere` searches entire `music_root` with cached index. | Grep for `playlist mirror: no library match`. |
| EAC3-only track kills whole job | `lossy_policy: deny` (old default) aborts the entire download when even one track lacks a FLAC master. | Set `lossy_policy: accept` in tidal.yaml — lossy is logged as last resort, not a hard fail |
| Stale .m3u8 files in /playlists | Pre-existing m3u8 exports from Sep 2026 era reference retired `/music_merged` path. Most targets missing from current library after curation. | `ls /your-media-path/library/playlists/*.m3u8`. Rebuild against current library or re-download missing tracks. |
| Playlist mirror double-numbered | Source files already have `NN -` prefix (from beets compilation import); mirror adds another. Fixed: strip existing `NN -` prefix before adding playlist-order prefix. | `ls /playlists/<name>/` — look for `01 - 01 - Title.opus` pattern. |
| ntfy import failures not firing | `organizer/notify.py` not wired into engine failure paths. Fixed: `notify_import_failure` called on every terminal FAILED path. | Check `docs/import-failure-alerts.md` for channel + trigger table. |

## 4. Live diagnostic commands

```bash
# 1. Did playlist jobs dispatch?
curl -s -H "Authorization: Bearer $TIDAL_TOKEN" \
  http://IPVPLACEHOLDER:19493/download/jobs/data | \
  python3 -c "import json,sys; jobs=json.load(sys.stdin); \
    [print(j.get('id',''),j.get('status',''),j.get('data',{}).get('playlist_name','')) \
     for j in jobs if j.get('data',{}).get('playlist_name')]"

# 2. Is the organizer processing?
curl -s -H "Authorization: Bearer $ORGANIZER_TOKEN" \
  http://IPVPLACEHOLDER:19298/queue/status

# 3. Did the mirror run? (organizer container logs)
docker logs fleet-organizer 2>&1 | grep -i 'playlist mirror' | tail -20

# 4. What's actually in /playlists?
ls -laR /your-media-path/library/playlists/ 2>/dev/null

# 5. Quarantine: are files actually there or is it a mislabel?
docker exec organizer find /storage/fleet/quarantine/ -name '*.flac' -newer /tmp -type f 2>/dev/null | head -5
# Empty? Check if tracks already landed in library instead:
find /your-media-path/library/music-library/ -name '<track_name>' -type f 2>/dev/null

# 6. Full job lifecycle (organizer audit trail)
docker logs organizer --since 30m 2>&1 | grep '<job_id>'

# 7. ntfy import-failure channel
# Subscribe: https://your-domain.example/fleet-imports
# Test: curl -d 'test' https://your-domain.example/fleet-imports
```

Tokens: `FLEET_ORGANIZER_TOKEN` and `HEADLESS_TOKEN` (Tidal) from
`path-to-credentials`.

## 5. ntfy alert channels

| Channel | URL | Purpose |
|---|---|---|
| `repo-alerts` | `https://your-domain.example/repo-alerts` | Download-queue alerts (aggregator notify.py) |
| `fleet-imports` | `https://your-domain.example/fleet-imports` | Import failures (organizer engine) — quarantine, verification, gated, mirror |

Import-failure notifications always include: job_id, specific failure reason, timestamp, source_path, target_artist/album, retries. No generic "import failed" messages.

See `docs/import-failure-alerts.md` for the full trigger table and subscription methods.

## 5. Key design facts

- **Dual-use by design**: tracks live in BOTH `/music` (Navidrome library)
  and `/playlists` (export folder). They are the same files — hardlinks/reflinks.
- **Beets never touches `/playlists`**: the organizer's beets import writes
  only to `/music`; the mirror is a separate post-import step.
- **Per-job, not per-playlist**: each track is an independent job with the
  playlist metadata attached. There is no single "playlist job" — the playlist
  is reconstructed from the per-track metadata at mirror time.
- **`_safe_playlist_dir_name`**: sanitizes playlist titles to `[a-zA-Z0-9 ._-]`
  max 120 chars. Special characters become `_`.
- **Lossy fallback**: `tidal.yaml` ships `lossy_policy: accept` (user decision 2026-10): EAC3-only
  tracks download as lossy (loudly logged, recorded in source_quality) instead
  of killing the whole job. FLAC is still requested first — lossy is the last
  resort for tracks with no lossless master. Essential for playlist imports
  where one bad track shouldn't fail the entire playlist.
- **Tidal FLAC entitlement**: per OAuth client pair, NOT per account. The "flac"
  client pair (device_login.py) gets FLAC 16/44.1 catalogue-wide; the legacy
  pair gets AAC 320/EAC3. Re-authenticate with `docker exec -it tidal-headless
  python /app/app/tidal/device_login.py` when EAC3 appears on a HiFi account.
- **Tidal entitlement**: FLAC delivery is per OAuth client pair, NOT per account.
  The lane must use the "flac" client pair (device_login.py) — the legacy
  pair gets AAC 320/EAC3 even on a HiFi account. See lossless-sourcing.md.
  If a track fails with EAC3/LOW, the session is on the wrong client pair.
- **Fleet web UI**: sends all result rows to `/dispatch`. The validator now accepts
  `kind=playlist`, so playlist dispatch through the fleet web UI works. Direct playlist
  imports also work via the aggregator API or the fleet UI.
- **Per-album import**: `download_playlist` writes `<playlist>/<artist>/<album>/` subdirs;
  the controller splits into one organizer job per album. This prevents the
  compilation-album failure mode where a multi-artist bag lands as `Various Artists / …`.
- **Whole-library mirror**: `_match_library_file_anywhere` searches the entire
  `music_root` (cached index, built lazily) when the per-dir match fails.
  Invalidated on tree writes (beets import, opus conversion).
- **Staging-consumed gate**: empty staging dir after beets `move: yes` is
  `staging_consumed`, NOT `all_files_quarantined`. The engine checks if the
  import actually landed before marking DONE.
