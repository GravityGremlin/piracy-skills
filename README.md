# Piracy Skills

A collection of generic, shareable skills for self-hosted media infrastructure. These skills cover the full lifecycle of a media downloader fleet — downloading, transcoding, library maintenance, and operational procedures — plus adjacent tooling for scraping, retro gaming, and content analysis. `piracy-ops` is the routing hub: a plain-language ask ("grab the new Gojira album", "yarr, a show") is classified once and dispatched to lane-fleet skills, arr-stack skills, LLM NLU decoding, debrid sourcing, or ROM retrieval.

## Skills

| Skill | Description |
|---|---|
| `piracy-ops` | Meta-router for the whole acquisition pipeline: one entry point that routes an ask (music, video, ROMs, debrid, scraping, LLM dispatch, handheld sync) to the right specialist skills |
| `media-downloader-fleet` | Audit and harden Flask + beets + opus media downloader fleets: API contracts, search filtering, worker pool patterns, deploy topology |
| `audio-transcode-pipeline` | Correctness rules for audio transcoding pipelines: ffmpeg metadata handling, opus encoding, album art, batch processing |
| `flask-worker-pool-audit` | Six recurring defects in Flask + threading.Event worker pools: race conditions, priority inversion, stuck jobs, state transitions |
| `media-grabber` | User-facing procedures for grabbing media through a downloader fleet: dispatch patterns, queue status, stuck-job cleanup, verification |
| `media-library-ops` | Library deduplication and maintenance: keeper rules, quarantine workflows, gap backfill, media server integration |
| `media-request-ops` | Request intake, validation, prioritization, and fulfillment workflows for media request systems (Overseerr, Ombi, Prowlarr integration) |
| `media-server-fleet` | Multi-server media fleet ops: Jellyfin/Plex/Emby/Navidrome, library sync, user management, transcoding profiles, backup/restore |
| `transcode-fleet-ops` | Distributed transcoding fleet: worker pools, codec selection, quality presets, hardware acceleration (Intel QSV, NVIDIA NVENC, AMD VCN), job queues |
| `docker-fleet-audit` | Docker Compose fleet audit: compose file validation, volume/bind mount correctness, network topology, secret handling, health check patterns |
| `blocked-page-recovery` | 5-rung ladder for blocked pages: Wayback → archive.today → Jina Reader → API pivot → real browser; provenance discipline |
| `scraping-to-api` | Convert scrape-only sites to structured APIs: session management, pagination, rate-limit handling, schema extraction, caching |
| `anti-bot-scraping` | Authenticated session pools for bot-walled APIs (Instagram, X-class): TLS fingerprint mitigation (curl_cffi), soft-block vs hard-fail classification, pool rotation |
| `webamp-ops` | Deploy/operate self-hosted Webamp (captbaritone fork): build pipeline, bundle load-order, butterchurn visualizer, media library window, CDP verification gates |
| `peertube-ops` | PeerTube debugging: stuck imports, failed syncs, lost follows, yt-dlp issues, DB state transitions, log retention caveats |
| `youtube-content` | YouTube transcripts → summaries, threads, blogs; auto-caption fetching, language fallback, output formats |
| `youtube-channel-review` | Verdict workflow: Gen-AI slop / human+slop-packaging / human+plagiarism / human authentic; cadence analysis, transcript sampling, source tracing |
| `console-homebrew-staging` | Research/download/verify/stage console homebrew (PS2 OPL, emulators, exploit installers) into clean SD-card layout + PC tools; GitHub release discovery, ELF verification; PS2 deep reference in `references/ps2-homebrew.md` |
| `rom-collection` | Completionist ROM system: Minerva torrents + TOSEC/NO-INTRO/Redump dats + IGDB enrichment; dat parsing, checksum matching, selective torrent download, library index schema |
| `arr-stack-ops` | Sonarr/Radarr day-2 ops: re-grabbing episodes, release hunting, interactive import, queue cleanup, API verification |
| `self-hosted-debrid` | Self-hosted debrid cache: torrent sourcing, SLSKD slskd source integration, IA redump sources |
| `repo-yard-grab` | Headless download lanes for music: resolve, dispatch, watch the beets import into the library; queue status, stuck-job cleanup, playlist import, Tidal quality entitlements, fresh-release hunting |
| `media-acquisition` | Acquiring media from YouTube into the library: yt-dlp pipelines, progress reporting, post-processing |
| `llm-media-dispatch` | LLM-driven acquisition: natural-language ask to parsed intent JSON to lane dispatch into the fleet |
| `dap-device-sync` | Sync music and playlists to a Rockbox DAP: playlist semantics, folder structure, device quirks |

## Usage

Each skill is a self-contained `SKILL.md` file in its own directory under `skills/`. They are designed to be loaded by AI coding assistants (Claude Code, OpenCode, Hermes, etc.) as procedural knowledge for working with self-hosted media infrastructure.

## Design Principles

- **Generic** — no cluster-specific paths, hostnames, IPs, or service names. All paths use placeholders like `/path/to/library`.
- **Technical** — preserves all the hard-won technical knowledge: API patterns, race conditions, transcode correctness, library management rules.
- **Practical** — includes real code patterns, verification checklists, and operational procedures that work in production.
- **Shareable** — MIT licensed, no internal references, useful for anyone running similar infrastructure.

## Tailoring this suite to your stack

The skills were lifted from a specific self-hosted deployment, then sanitized.
They are runbooks, not configs: swap the tokens below for your own values and
every procedure transfers without editing prose.

### Placeholder vocabulary (consistent across all skills)

| Token | Meaning |
|---|---|
| `<lane-host>`, `<aggregator-host>`, `<arr-host>`, `<media-server-host>`, `<gateway-host>` | The machine running each attached service. |
| `IPVPLACEHOLDER` | A LAN address the original deployment knew by name; replace with your host, or (for scripts) point the matching `FLEET_*`/engine env var at it. |
| `/your-media-path`, `/your-stacks-path`, `/your-app-data-path` | Volume roots: media library, Docker/Compose stacks, container app data. |
| `***` inside an HTTP header | A run-time credential — your own bearer token, not a secret shipped in the repo. |
| `X-Api-Key: $RK` / `$FLEET_TOKEN` / `$MEDIA_API_KEY` | Env-defined credentials; grab them from the referenced config file or admin UI before running commands. |

### Component expectations

- **Import stage** — any beets-class organizer with a staging root and library it
  writes on import. `media-downloader-fleet` documents the API contract the
  downloader lanes assume; the arr skills are independent of it.
- **Media server** — Navidrome/Jellyfin/Plex/Emby all work; the sanity checks in
  `media-library-ops` use the API surface they all share, keyed by a
  `MEDIA_API_KEY` env var.
- **Torrent/download engine** — qBittorrent (canonical for the debrid pattern),
  aria2c (canonical for ROM sets), or Transmission as a drop-in RPC engine. All
  three speak the same five operations: see
  `skills/self-hosted-debrid/references/torrent-clients.md` for the env-var
  contract and per-engine commands.
- **arr stack (optional)** — Sonarr/Radarr/Prowlarr plus SABnzbd (usenet) or a
  torrent download client; `arr-stack-ops` documents both download paths.
- **NLU gateway (optional)** — `llm-media-dispatch` expects an
  OpenAI-compatible endpoint plus an `NLU_API_KEY`; everything else works
  without it.

### What is deliberately yours to swap

`FLEET_*` env vars are the only place fleet topology lives in the bundled
scripts — the original `.env` names are yours to reuse. Nothing in this repo
requires SABnzbd/qBittorrent/aria2 specifically: they are the documented
engines, and the docs say exactly which endpoints and settings to change to
swap any of them.

## Contributing

These skills are maintained as a community resource. Primary public surface and PR target: `https://github.com/GravityGremlin/piracy-skills`. The same tree also lives on the project's self-hosted Forgejo (`https://fj.gravitywell.xyz/gravitas/piracy-skills`), which is auth-gated and serves as the canonical copy.