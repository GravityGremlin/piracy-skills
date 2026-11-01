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
| `console-homebrew-staging` | Research/download/verify/stage console homebrew (PS2 OPL, emulators, exploit installers) into clean SD-card layout + PC tools; GitHub release discovery, ELF verification |
| `ps2-homebrew` | PS2 homebrew reference: OPL/wOPL current state, exFAT vs APA, MX4SIO speeds, boot methods, emulator landscape, CHD→ISO→ZSO pipeline, Minerva workflow |
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

## Contributing

These skills are maintained as a community resource. Primary public surface and PR target: `https://github.com/GravityGremlin/piracy-skills`. The same tree also lives on the project's self-hosted Forgejo (`https://fj.gravitywell.xyz/gravitas/piracy-skills`), which is auth-gated and serves as the canonical copy.