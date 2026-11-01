---
name: media-downloader-fleet
description: "Audit/harden Flask+beets+opus media downloader fleets: API + filtering."
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [flask, fleet, beets, opus, ffmpeg, gunicorn, audit, media-downloader]
    related: [flask-worker-pool-audit, audio-transcode-pipeline, media-grabber]
---

# Media Downloader Fleet Pipeline

Audit and harden Flask + beets + opus media downloader fleets. Covers API
contracts, search filtering, worker pool patterns, deploy topology, and
operational procedures for self-hosted media acquisition infrastructure.

> **Deploy from the PROD checkout.** Containers typically mount the stacks
> directory, but the deploy engine's pull/parity gates may run in a dev
> checkout: a deploy run from the dev tree can recreate containers against
> stale code and still report OK. Pull the stacks checkout, deploy from there,
> then verify the SERVED page.

## Core Architecture

A media downloader fleet typically consists of:

- **Downloader lanes** — Flask apps that accept download jobs via HTTP API,
  fetch from upstream sources (streaming services, P2P networks), and stage
  files for import
- **Aggregator** — a central Flask app that routes search queries to multiple
  lanes and merges results
- **Import Pipeline** — a beets-based import pipeline that processes staged files,
  fetches metadata, and adds them to the library
- **Library** — the final media collection served by a media server

### Typical Directory Layout

```
/path/to/stacks/           # Docker Compose stacks
  lane-a/                  # One downloader per source
  lane-b/
  aggregator/              # Search aggregation + job dispatch
  import pipeline/               # Beets import pipeline
  traefik/                 # Reverse proxy config
/path/to/downloads/         # Staging area for incoming files
/path/to/library/           # Final organized library
```

## API Contract

### Job Status Codes

- `202 Accepted` — job enqueued (not 200)
- `404` — job does not exist
- `400` — invalid state transition
- `200` — success (including resume of COMPLETED jobs)

### Core Endpoints

```
POST /download/enqueue          # Enqueue a single track/album
POST /download/discography       # Enqueue a full discography
GET  /download/jobs/<id>         # Get job status
POST /download/jobs/<id>/<action>  # cancel, retry, pause, resume, priority
GET  /jobs/unified/json          # UI-facing job list
```

### Contract JSON

The enqueue/discography contract must be frozen and versioned. Key fields:

```json
{
  "job_id": "uuid",
  "status": "queued|running|done|failed",
  "source_quality": {
    "lossless_tracks": 12,
    "lossy_tracks": 0
  },
  "data": { ... }
}
```

## Worker Pool Patterns

See `flask-worker-pool-audit` for the six recurring defects in Flask +
threading.Event worker pools. The most critical:

1. **`_queue_event.clear()` race** — clear inside the lock, never outside
2. **Priority inversion** — priority jobs must skip the FIFO queue
3. **Stuck job detection** — jobs stuck in RUNNING need a timeout sweep

## Search & Filtering

### Aggregator Route Layout

The aggregator typically exposes:

```
GET /search?q=<query>&source=<lane>     # Search one lane
GET /search/all?q=<query>                # Search all lanes
GET /resolve?url=<source_url>            # Resolve a URL to a job
```

### Filtering Rules

- **Quality filtering** — filter by bitrate, codec, format
- **Source filtering** — allow/deny specific sources
- **Deduplication** — skip results already in the library
- **Content filtering** — explicit/clean, language, region locks

### Result Normalization

All lanes must return a normalized result schema:

```json
{
  "title": "...",
  "artist": "...",
  "album": "...",
  "year": 2024,
  "track_number": 1,
  "duration_ms": 123456,
  "bitrate_kbps": 320,
  "format": "flac",
  "source": "lane-name",
  "url": "...",
  "size_bytes": 12345678
}
```

## Deploy Topology

### Container Layout

Each lane runs as a separate container. The aggregator and import pipeline are
also separate containers. All share a common network for inter-service
communication.

### Health Checks

- Each lane exposes `/health` returning 200 when ready
- The aggregator waits for all lanes before marking itself healthy
- The import pipeline watches the staging directory for new files

### Verification After Deploy

1. **Verify the SERVED path, not the path you assumed** — extract real paths
   from served HTML (`<script src>`, `<link href>`) before probing
2. **Probe every endpoint your change touched** — the health gate only waits
   on `/`, so a refactor breaking another route still deploys "healthy"
3. **Check container boot command** — `docker inspect -f '{{json .Config.Entrypoint}} {{json .Config.Cmd}}' <container>`
   to see what actually runs at boot

### Common Deploy Pitfalls

- **Two sources of truth for boot command** — keep the command in one place,
  or the script silently rots
- **Stale code in containers** — always deploy from the prod checkout
- **Entrypoint override** — Dockerfile CMD can be overridden by compose
  `command:`, making entrypoint scripts unreachable

## Queue Numbers: Which One Is the Truth

Before reporting queue depth, know the three layers:

1. **Aggregator `/jobs/unified/json`** — UI-facing job records only (hundreds)
2. **Lane `jobs.db`** — the real work queues (thousands)
3. **Import Pipeline DB** — DONE/FAILED/PROCESSING/READY

A monitoring cron can alert on lane activity + staging regrowth. It does NOT
cover per-lane queue age, so a lane can sit frozen for days without a report.

## Adding a New Lane — Integration Audit Checklist

After the code is green and the lane is deployed, verify on prod:

- **Don't stop at backend wiring — the last mile is what the UI actually
  SENDS.** Two opposite failures, one cause: a capability the backend
  implements that no user can reach.
  - (a) *No control exists.* The lane has full support in the backend but
    the UI shows no toggle — the lane is complete but unusable.
  - (b) *The control exists but sends the wrong parameters.* Before designing
    a feature, read the route's accepted fields and the lane's enqueue kinds —
    the capability is often already there and the only gap is a parameter the
    UI never sends.

- **Verify the lane appears in the aggregator's source list**
- **Verify the lane's health endpoint responds**
- **Verify a test download completes end-to-end**
- **Verify the import pipeline picks up the staged file**

## Operational Procedures

### Commit Discipline

- **Often, frequently, with clear terse notes.** Every completed unit of work
  gets a commit and push before moving to the next. Commit messages explain
  what changed and why, briefly. No bulk commits that bundle multiple
  unrelated changes.

### CI Verification

- **Verify every CI stage before calling the gate green.** CI runs stages in
  order and exits on the first failure, so a long-red early stage (lint) means
  later stages have never run at all. "Lint is clean now" is not "CI is green" —
  clear the blocker, re-run the whole pipeline, and report the stages you
  actually watched pass.

### Audit Doc Staleness

- **Audit docs go stale within hours — verify findings against live prod.**
  Before executing any audit finding, repro it live (curl the endpoint,
  `docker ps`, `git log -p <file>`) — don't trust the doc. A stale finding that
  is verified closed is a clean close; a stale finding that is executed wastes
  a commit and risks a regression.

### Parallel Test Fixes

When fixing many test failures across tools, use batch delegation:

1. **Categorize failures by root cause** (not by test file)
2. **One subagent per cluster**, each given the exact test command, the
   absolute repo path, and the instruction to find root cause AND fix
3. **Aggregate results** — each subagent reports root cause + fix + test count
4. **Run per-tool verification** — `for tool in ...; do pytest tools/$tool/tests/; done`

## Security Considerations

- **Path safety** — import pipeline import must enforce resolve()+parents containment
  (traversal attempts rejected)
- **Token scrub** — never log or display API tokens
- **CSRF protection** — all state-changing endpoints need origin validation
- **Rate limiting** — public-facing routes need per-IP rate limits

## Monitoring

- **Fleet queue monitor** — periodic check of lane queue depths + staging
  directory growth. Alerts when inflow > drain (staging regrowth).
- **Per-lane health** — each lane's `/health` endpoint should be checked
- **Import Pipeline backlog** — count of files in staging waiting for import

## References

For deeper coverage of specific topics, see:
- `flask-worker-pool-audit` — worker pool race conditions and fixes
- `audio-transcode-pipeline` — ffmpeg transcode correctness rules
- `media-grabber` — user-facing download dispatch procedures
- `media-library-ops` — library dedup and maintenance rules
