# Acquisition / "piracy" skill family

Which skill owns which part of media acquisition. Read this before adding a new
acquisition procedure: the lane almost always already has an owner, and a
parallel path is the failure mode the user rules out.

| Skill | Owns |
|---|---|
| `yarr-ops` | The YARR stack on your arr stack host: NLU frontend, lanes (games, web, seerr, releases, soulseek, library, roms, edge, music), `/api/find` -> `/api/grab`. Entry point for any "get me X" request that is not music-in-library work. |
| `music-grab` | Music grabs through the downloader fleet (one downloader per provider service) plus the verification rule: done = in beets DB or on disk, not "grab accepted". |
| `music-downloader-fleet-pipeline` | The downloader fleet as a fleet: Flask+beets+opus pipeline audit/hardening, API and filtering. |
| `music-library-ops` | The merged music library itself: dedupe, canonical-album rules, maintenance. |
| `self-hosted-debrid` | The debrid cache layer and its qBittorrent backing. |
| `arr-stack-ops` | Sonarr/Radarr/Prowlarr/SAB behaviour when the arrs stop working. |
| `jellyfin-fleet` / `jellyseerr-ops` | Playback/scan side and the request front-end for movies and TV. |
| `llm-media-dispatch` / `ai-radarr-pipeline` | NLU -> intent -> lane dispatch design for new pipelines. |
| `tdarr-fleet-ops` | Transcode job reports and audits after acquisition. |
| `scraping-to-api`, `anti-bot-scraping`, `privacy-frontends` | Reaching sources that block plain requests. |

## Auditing this family

When asked to review/audit acquisition skills:

1. Audit read-only. Grabs are side effects: `POST /api/grab` and lane enqueues
   start real downloads. Probe with `GET`s and file reads only.
2. Judge each skill on four axes: (a) are its factual claims still true against
   the live cluster, (b) does it duplicate another skill above, (c) does it push
   a bespoke script where a lane/umbrella already exists, (d) does it break a
   standing convention (no `/tmp` staging, no loose files in `~`, secrets only
   from your credential store, Forgejo not GitHub).
3. Anchor every finding to `path:line` or command output, and label measured vs
   inferred. "Verify, never assume" applies to the skill text itself: a skill is
   a claim, not evidence.
4. Report drift as the finding it is — a bumped live version, renamed lane, or
   moved path with unchanged skill text. Do not silently rewrite skills while
   auditing; report corrections as old -> new pairs so the edit is reviewable.
