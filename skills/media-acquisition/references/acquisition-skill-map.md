# Acquisition skill family

Which skill owns which part of media acquisition in this repo. Read this before
adding a new acquisition procedure: the lane almost always already has an owner,
and a parallel path is the failure mode these rules exist to prevent.

| Skill | Owns |
|---|---|
| `media-grabber` | Grabbing music/albums/discographies through the downloader fleet's user-facing entry point, plus fleet queue status and release hunting. |
| `repo-yard-grab` | The full downloader-fleet grab runbook: dispatch, queue forensics, playlist import, lossless sourcing, verification. |
| `media-downloader-fleet` | The downloader fleet as a fleet: Flask + beets + opus pipeline audit/hardening, API contracts, deploy topology. |
| `flask-worker-pool-audit` | Worker-pool defect catalogue the fleet audit drills into. |
| `media-library-ops` | The merged music library itself: dedupe, canonical-album rules, maintenance. |
| `audio-transcode-pipeline` | ffmpeg/opus/metadata correctness rules after acquisition. |
| `transcode-fleet-ops` | Distributed transcode fleet ops and job-report audits. |
| `arr-stack-ops` | Sonarr/Radarr/Prowlarr/SAB behaviour when the arrs stop working. |
| `media-request-ops` | Request intake and fulfillment workflows in front of the arrs. |
| `media-server-fleet` | Playback/scan side of the media servers. |
| `llm-media-dispatch` | NLU → intent → lane dispatch design for new pipelines. |
| `self-hosted-debrid` | The debrid cache layer and its torrent backing. |
| `rom-collection` / `console-homebrew-staging` | ROM dat-verified collection and console homebrew staging. |
| `media-acquisition` | YouTube-specific acquisition. |
| `dap-device-sync` | Last-mile sync to a Rockbox handheld. |
| `scraping-to-api`, `anti-bot-scraping`, `blocked-page-recovery` | Reaching sources that block plain requests. |
| `piracy-ops` | The routing hub that ties the above together. |

Targets listed in `piracy-ops`'s route table without a directory here are private
operational skills (internal fleet ops and the NLU front-end); the routing intent
is public, the playbooks are not.

## Auditing this family

When asked to review/audit acquisition skills:

1. Audit read-only. Grabs are side effects: `POST /api/grab` and lane enqueues
   start real downloads. Probe with `GET`s and file reads only.
2. Judge each skill on four axes: (a) are its factual claims still true against
   a live deployment, (b) does it duplicate another skill above, (c) does it push
   a bespoke script where a lane/skill already exists, (d) does it contradict
   this repo's conventions (placeholder paths, no secrets anywhere).
3. Anchor every finding to `path:line` or command output, and label measured vs
   inferred. "Verify, never assume" applies to the skill text itself: a skill is
   a claim, not evidence.
4. Report drift as the finding it is — a bumped live version, renamed lane, or
   moved path with unchanged skill text. Do not silently rewrite skills while
   auditing; report corrections as old -> new pairs so the edit is reviewable.
