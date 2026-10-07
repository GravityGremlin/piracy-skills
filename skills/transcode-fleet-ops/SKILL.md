---
name: transcode-fleet-ops
description: "Use when reviewing transcode job reports, transcode audits, developing/testing/deploying transcode plugins, diagnosing size-gate veto loops and no-conversion cases, or working with a Tdarr transcode fleet."
version: 1.0.0
tags: [tdarr, transcode, av1, ffmpeg, fleet]
metadata:
  hermes:
    tags: [tdarr, transcode, fleet, av1]
    related_skills: [media-server-fleet]
---

# Transcode fleet ops

A transcode fleet runs Tdarr server+node pairs (Docker Compose, web UI port
8266) across multiple hosts. Job-report review is recurring — dated audits
live in a dedicated directory (e.g., `audits/tdarr-audit-YYYY-MM-DD.md`).

## Topology

### Primary host

- Runs `tdarr-server` + `tdarr-node` from a compose stack (e.g.,
  `/opt/stacks/tdarr/` or `~/stacks/tdarr/`).
- Web UI on port 8266.
- **Server DB/reports**: `<data-dir>/server/Tdarr/DB2/` (JobReports =
  per-job dirs of `.txt` logs).
- **Live library config, file/queue state**: SQLite at
  `<data-dir>/server/Tdarr/DB2/SQL/database.db`. The `*JSONDB` dirs beside it
  are empty shells on some builds, so the DB is the only place to read plugin
  inputs, verdicts, and per-file sizes. Open read-only:
  ```python
  sqlite3.connect('file:...database.db?mode=ro', uri=True)
  ```
  Tables `filejsondb` / `librarysettingsjsondb` / `jobsjsondb` are
  `id, timestamp, json_data` blobs. Field semantics:
  - `file_size` in MB
  - `bit_rate` in bps
  - `duration` in seconds
  - `newVsOldRatio` = new/old × 100 (NOT percent saved)
  - `TranscodeDecisionMaker` = verdict string
  - `bumped` / `holdUntil` for queue management
- **Server text logs**: `<data-dir>/logs/Tdarr_{Server,Node}_Log.txt`
  (mounted `/app/logs` in the container).
- **Library**: on a storage mount (e.g., `/storage/library/movies/...`).
- **Transcode cache**: `/storage/tdarr_cache` + `/var/cache/tdarr`.

### Additional hosts

Each additional host runs its own `tdarr-server` + `tdarr-node` pair with its
own data directory and library path. The fleet is managed by having each node
report to a central server, or by running independent stacks per host.

## API notes

- The API endpoint varies by Tdarr version. On some builds, `/api/v2/get-table`
  returns 404 — read the SQLite DB directly instead.
- Always open the DB read-only to avoid corrupting live state.

## Job report parsing

See `references/report-parsing.md` for detailed recipes on:
- Scoping a time window of job reports
- Classifying reports by tail markers (`[-success-]` / `[-error-]`)
- Identifying source files from report content
- Extracting veto numbers from size-gate messages (homoglyph-safe)

## Size-gate veto loops

See `references/size-guard-math.md` for:
- Preset tiers and their size estimates
- The floor guard logic (why big files are skipped, not converted)
- How the size gate and the encoder plugin are coupled

## Plugin development and deployment

See `references/plugin-deploy.md` for:
- Plugin repo layout and naming conventions
- Deploy runbook (copy to plugins dir + restart server)
- Backup and rollback procedures
- Common incident classes (downmix budget stacking, remux re-encode bloat)

## AV1 encoding

See `references/av1-encoder-bench-2026-09.md` for:
- Container toolchain versions (FFmpeg, SVT-AV1, HandBrake, mkvtoolnix)
- Param support matrix (accepted vs. rejected options)
- Preset clamping behavior
- Measured encoding performance on real sources

## Guard simulation

`scripts/guard-sim.py` models the AV1 floor guard to answer:
- "Why do large H.264 files never convert?"
- "What would preset X / floor Y do to the backlog?"

Usage:
```bash
python3 guard-sim.py                       # live inputs from librarysettingsjsondb
python3 guard-sim.py --preset balanced --floor 5
python3 guard-sim.py --min-gb 20 --limit 15
python3 guard-sim.py --all                 # every video codec, not just h264
```

Set `TDARR_DB` environment variable to point to a different database file.

## Common incident classes

1. **Downmix budget stacking** → size-gate upperBound veto loop. An audio
   downmix plugin budgets growth per worker cycle vs the staged file; a fresh
   budget in a later cycle allows too much growth → veto → revert → re-fail
   every scan. Fix: budget cumulative vs the original file size.

2. **Remux re-encode bloat**. Container remux plugins with unlimited CRF can
   blow up small files (e.g., 695 MB AVI → 1481 MB = +212%). Fix: cap
   `-maxrate` at ~1.05× source video bitrate.

3. **Homoglyphs break text regexes**. Plugin/log text contains non-ASCII
   look-alikes inside words, so regexes like `r"which (\d+)%"` silently fail.
   Workaround: anchor on ASCII substrings and extract numbers from raw bytes.

4. **Live-file gotchas**. Job reports are live — the verdict line is appended
   minutes after job events. Classify by markers in the last ~3000 chars, not
   by first-match.

## Audit workflow

1. Scope a time window of job reports.
2. Classify reports (success/error/running).
3. Identify repeat failures (same job dir with reports on multiple days).
4. Extract veto numbers and identify the plugin/step causing the veto.
5. Check the size-gate math (see `references/size-guard-math.md`).
6. Propose a fix (plugin config change, size-gate adjustment, or manual
   intervention).
7. Document the audit in a dated markdown file.
