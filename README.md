# Piracy Skills

A collection of generic, shareable skills for self-hosted media infrastructure. These skills cover the full lifecycle of a media downloader fleet: downloading, transcoding, library maintenance, and operational procedures.

## Skills

| Skill | Description |
|---|---|
| `media-downloader-fleet` | Audit and harden Flask + beets + opus media downloader fleets: API contracts, search filtering, worker pool patterns, deploy topology |
| `audio-transcode-pipeline` | Correctness rules for audio transcoding pipelines: ffmpeg metadata handling, opus encoding, album art, batch processing |
| `flask-worker-pool-audit` | Six recurring defects in Flask + threading.Event worker pools: race conditions, priority inversion, stuck jobs, state transitions |
| `media-grabber` | User-facing procedures for grabbing media through a downloader fleet: dispatch patterns, queue status, stuck-job cleanup, verification |
| `media-library-ops` | Library deduplication and maintenance: keeper rules, quarantine workflows, gap backfill, media server integration |

## Usage

Each skill is a self-contained `SKILL.md` file in its own directory under `skills/`. They are designed to be loaded by AI coding assistants (Claude Code, OpenCode, etc.) as procedural knowledge for working with self-hosted media infrastructure.

## Design Principles

- **Generic** — no cluster-specific paths, hostnames, IPs, or service names. All paths use placeholders like `/path/to/library`.
- **Technical** — preserves all the hard-won technical knowledge: API patterns, race conditions, transcode correctness, library management rules.
- **Practical** — includes real code patterns, verification checklists, and operational procedures that work in production.
- **Shareable** — MIT licensed, no internal references, useful for anyone running similar infrastructure.

## Contributing

These skills are maintained as a community resource. If you have improvements, bug fixes, or new skills for media infrastructure, please contribute via pull request.

## License

MIT — see [LICENSE](LICENSE) for details.
