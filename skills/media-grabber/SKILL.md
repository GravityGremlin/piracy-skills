---
name: media-grabber
description: "Use when grabbing media (albums, discographies, tracks, playlists) via a downloader fleet — resolve, dispatch, and watch downloads through the beets import pipeline into the media library. Also covers fleet queue status, stuck-job cleanup, and hunting fresh releases."
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [media, fleet, download, beets, grab]
    related: [media-downloader-fleet, media-library-ops]
---

# Media Grabber

Grab albums/discographies/tracks through your downloader fleet's headless
lanes. Downloads auto-stage into the beets import pipeline and land in
the media library — no manual beets, ever.

> **Prerequisites.** Execute each example against your own fleet by setting:
>
> ```bash
> export FLEET_URL="http://<aggregator-host>:<port>"   # aggregator base URL
> export LANE_URL="http://<lane-host>:<port>"          # one downloader lane's base URL
> export FLEET_TOKEN="<aggregator bearer token>"
> export LANE_TOKEN="<that lane's bearer token>"
> ```
>
> `<aggregator-host>`, `<lane-host>` and the masked `Bearer ***` values in the
> commands below mean these variables.

> **This is the user-facing entry point** for grabbing media through the
> fleet. For deep audit, hardening, deploy topology, and E2E test runs,
> see the `media-downloader-fleet` skill.

Check the release DATE before hunting a "missing" release: lanes only carry
released material, so a future-dated album resolves to the artist's back
catalogue and looks exactly like a broken search. "Not out until <date>; only
the lead single exists" is a correct answer — say it and offer the single
instead of dispatching the album title.

Discographies can arrive SHORT (source throttling silently drops tracks).
After any discography dispatch, verify per-album file counts against the
lane job's `data.source_quality.lossless_tracks`.

**Active lanes:** configure per your fleet. A peer's "FLAC" may be a lossy
re-wrap — check its ancestry with a spectral cutoff comparison — see `repo-yard-grab/scripts/spectral_cutoff.py` in this repo (same-run
128k/fake-chain calibration).

## Source Quality: Lossless First, Lossy as a Very Last Resort

Standing rule: the download SOURCE must be lossless wherever possible;
lossy formats only when nothing lossless exists anywhere. Even though the
import pipeline converts to opus 160k, a lossy source is a double-lossy artifact
— never accept one silently. Every provider lane should have a
delivered-quality gate (default `deny`); P2P lanes are exempt by design
(peers supply whatever exists) and should log their format mix at group
finalize.

- **Asking for lossless is not the same as getting it.** A lane's request
  is honest; the delivery is not always. A subscribed account with
  premium access can still receive AAC for every lossless/hi-res request
  on tested tracks. Always verify the delivered format, not just the
  request parameters.

## P2P Transfer Reliability — Two Failure Classes

Never conflate these:

- `Transfer rejected: File not shared.` — PEER side: advertised but not
  shared. Retry other peers (the same dir is often hosted elsewhere, and a
  peer that rejected once can succeed later).
- `Transfer failed: Connection timed out.` — NETWORK side: the peer is
  unreachable or too slow. Retry later or try a different peer.

## Queue Status and Stuck-Job Cleanup

### Checking Queue Depth

```bash
# Per-lane job counts
curl -s http://<lane-host>/jobs/unified/json | python3 -m json.tool

# Stuck jobs (RUNNING for > 5 minutes)
curl -s http://<lane-host>/jobs/unified/json | \
  python3 -c "
import json, sys, time
jobs = json.load(sys.stdin)
now = time.time()
for j in jobs:
    if j['status'] == 'running' and now - j.get('started_at', 0) > 300:
        print(f\"STUCK: {j['id']} - {j.get('title', 'unknown')}\")
"
```

### Cleaning Stuck Jobs

```bash
# Cancel a stuck job
curl -X POST http://<lane-host>/download/jobs/<job_id>/cancel

# Retry a failed job
curl -X POST http://<lane-host>/download/jobs/<job_id>/retry
```

## Dispatch Patterns

### Single Album

```bash
curl -X POST http://<aggregator-host>/download/enqueue \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://source.example.com/album/12345",
    "quality": "lossless",
    "source": "lane-name"
  }'
```

### Full Discography

```bash
curl -X POST http://<aggregator-host>/download/discography \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "artist": "Artist Name",
    "source": "lane-name",
    "quality": "lossless",
    "include_singles": false,
    "include_eps": true
  }'
```

### Track Search and Grab

```bash
# Search for a track
curl -s "$FLEET_URL/search?q=artist+track+title&source=<lane>" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Grab the first result
curl -X POST http://<aggregator-host>/download/enqueue \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "<resolved-url>", "source": "lane-name"}'
```

## Verification After Grab

After any grab dispatch:

1. **Check job status** — poll `/download/jobs/<id>` until DONE or FAILED
2. **Verify file count** — compare actual files in the library dir against
   the job's `source_quality.lossless_tracks`
3. **Verify format** — spot-check that files are the expected format
   (not a lossy re-wrap labeled as lossless)
4. **Check import pipeline import** — confirm beets imported the files (not
   stuck in staging)

### Verifying Landed Files

Lane job IDs may purge from the summary endpoint within minutes. Verify
landings by globbing the artist's album dirs server-side (track counts
before/after), not by job status.

```bash
# Count files in artist's album dirs
find /path/to/library/<artist> -name "*.opus" | wc -l

# Compare against expected
# (expected = sum of source_quality.lossless_tracks across dispatched jobs)
```

## Common Pitfalls

- **Import Pipeline dedupes imports against the library** — tracks already held
  in ANY edition dir get routed there or skipped, so album grabs land
  partially across edition dirs. Recheck every edition dir of the artist
  after a grab.
- **Long typed path literals** (album/track names with spaces/punctuation)
  get mangled in tool input: derive paths via server-side glob/listdir,
  never hand-type album names into shell commands.
- **Text mangling in tool I/O** — some sessions mangle text in both tool
  inputs and outputs (=, # comment prefixes, leading indents, small words).
  All file edits should go through verified heredoc splices with
  syntax verification.
- **Case/accent variants split one artist's albums** — `Alice In Chains` /
  `Alice in Chains`, `Alizee` / `Alizée`. The dedup gate is deliberately
  strict, so the variant spelling is not recognised as present, and that
  album is re-downloaded and re-imported. Measure it by folding the artist
  dir list and counting collision groups.
- **Fold BOTH sides before calling an album absent** — accents, beets path
  sanitisation (`:`→`_`), and a trailing year qualifier are the same album.
  An unfolded comparison invents "not imported" and turns a safe prune
  into data loss.
- **Tidal `abuse_detected: User account is suspended due to abuse` self-lifts**
  in roughly 8 h with no code, credential or config change. Do not retire the
  lane or re-auth on the first burst: compare the LAST `abuse_detected`
  timestamp in `docker logs <tidal>` against the FIRST successful download
  after it. If a download succeeded later, the lane recovered on its own and
  the suspension was time-based.

## Progress Protocol

When running downloads/discography waves, follow user-facing progress
protocol:

- Stage labels: DOWNLOADING / CONVERTING OPUS / IMPORTING / DONE
- Include counts (e.g., "DOWNLOADING 3/12")
- Poll every ~5 minutes
- Report failures immediately with the error class

## Fleet Freeze Procedure

For maintenance or emergencies:

1. Stop accepting new jobs (disable the enqueue endpoint)
2. Wait for running jobs to finish (or cancel them)
3. Stop the import pipeline
4. Perform maintenance
5. Restart the import pipeline
6. Restart the lanes
7. Re-enable the enqueue endpoint

## Authentication

Lanes typically use bearer token auth. The token is passed via the
`Authorization: Bearer <token>` header. Tokens should be:

- Stored in environment variables, not in code
- Rotated regularly
- Scoped per-lane (not shared across lanes)
- Never logged or displayed in output
