---
name: self-hosted-debrid
description: "Use when building or fixing a self-hosted debrid cache."
version: 1.2.0
author: Gravis Wellz
license: MIT
metadata:
  hermes:
    tags: [debrid, torrents, qbittorrent, roms, archive.org, fastapi, media-acquisition]
---

# Self-hosted debrid cache

## When to Use

- Building or extending a debrid-style download service: submit magnet /
  .torrent URL / direct URL → download → shareable link.
- Importing files produced by ANOTHER downloader (slskd/Soulseek grabs,
  external clients) into cache ownership, or checking a local master
  library so users don't re-download what already exists.
- Debugging one that misbehaves: jobs erroring, download links 404ing,
  files landing in the wrong directory, searches finding nothing, jobs
  stuck at 100% because an import step failed silently.
- Wiring new content sources (console collections, DDL hosts, Soulseek)
  into an existing cache/resolver.

Class task: the user submits a magnet / .torrent URL / direct URL, the
service downloads it, and the result is served as a shareable HTTPS link
with range support. Proven shape: a FastAPI "cache-api" + qBittorrent as
the torrent engine + content on disk, behind the cluster reverse proxy,
fronted by a natural-language entry point. A live instance: the search stack —
the `search-ops` skill has the concrete deployment, ports, and deploy loop for
that instance; this skill is the transferable engineering.

## Engine quirks (qBittorrent 5.x — all live-probed)

The engine slot is swap-safe: `references/torrent-clients.md` documents the
same five operations against aria2 (CLI + JSON-RPC) and Transmission (RPC
handshake), plus the env-var contract every engine variant expects.

- **5.2 renamed pause/resume**: `/api/v2/torrents/resume` and `/pause`
  return 404 "Endpoint does not exist" — the working names are
  `/api/v2/torrents/start` and `/stop`. Wrap as try-new, fall back on 404
  so older engines keep working. A bare `/resume` silently broke queue
  pause/resume AND every selective-flow start until live-probed.
- **`torrents/add` returns a JSON body on SUCCESS in 5.1+**:
  `{"added_torrent_ids":[…],"failure_count":0,"success_count":1}`.
  Never treat any non-"Ok." body as failure — parse the JSON and raise
  only when `failure_count>0` with `success_count==0` (keep the legacy
  plain-text "Fails." check for old engines). Getting this wrong raises
  AFTER a successful add and kills the whole selective setup.
- **`/torrents/files` names are relative to savepath and already include
  the set's top-level dir.** Post-grab existence checks and pruning must
  use `savepath/<name>` with NO extra prefix — prefixing a job's display
  name makes the check miss every file and the prune no-op silently.
- Login success is HTTP 204. For set-torrent grabs, compute the v1
  infohash yourself from the downloaded `.torrent` bytes (sha1 of the
  bencoded `info` dict) instead of waiting on name-based resolution.

## Architecture (the parts that matter)

- **Cost model (swarm vs patronage).** Classify every component by what a
  new participant costs: SWARM = marginal cost ≈ 0 and participation is
  self-financing (BitTorrent seeding, Soulseek, federated PeerTube/Funkwhale
  instances, ActivityPub/Nostr relays — the downloader already wanted the
  file). PATRONAGE = one operator pays storage, bandwidth, electricity;
  benefit diffuses to whoever connects (central cache-api, catalogue DB,
  Jellyfin/Navidrome serving, the master library). In practice qBittorrent
  with unbounded seeding (`ratio_limit: -2`, `seeding_time_limit: -2`) makes
  the *distribution* side swarm-shaped while the *serving* side stays
  patronage-shaped. Consequence: a cache that is only patronage components
  becomes a subsidy target as it grows; pair it with seeding/federation so
  participation pays for itself, and never build a public free alternative
  as a single central HTTP server — that is the shape enforcement punishes
  and the shape that kills the operator's budget.

- API layer owns submit / status / delete / manifest AND file serving.
  Torrents go to the engine (qBittorrent Web API); direct URLs (Internet
  Archive, DDL) are streamed by the API itself — no torrent engine involved.
- One DB row per task with `id = sha256(infohash-or-URL)[:16]` — repeat
  submits return the existing row instantly (dedupe for free).
- File serving is PUBLIC (shareable by design) with Range → HTTP 206 so
  browsers stream/resume. Submit/delete/list stay behind a credential.

## Pitfalls (each cost a debugging cycle)

- qBittorrent 5.x `auth/login` returns **204 No Content** on success (older
  5.x/4.x return 200 body "Ok."). Accept 204 as success or the health check
  reports the engine "down" while it is fine.
- Save-path alignment: the API hands qBittorrent ABSOLUTE save paths
  (`/cache/games`); the qbt container must mount the same tree at the same
  path (`/host/storage:/cache`). A conventional `/downloads`-only mount
  makes every job fail with file errors.
- Accept singular AND plural category keys (`game`/`games`,
  `movie`/`movies`) or downloads land in the fallback dir.
- Direct downloads: UNQUOTE (percent-decode) the URL path before writing the
  file to disk, and QUOTE when building manifest/download URLs. Literal
  `%20`/`%28` in on-disk names break serving (404 on the obvious path).
- URL-submitted torrents have no infohash — backfill by normalized
  name-match against the engine's torrent list (strip non-alphanumerics on
  both sides: "Ubuntu 24.04.3 Live Server" ↔ `ubuntu-24.04.3-…iso`).
- qBittorrent's first-boot temp password rotates; don't script the login.
  Pre-seed `qBittorrent.conf` with `WebUI\AuthSubnetWhitelist=IPVPLACEHOLDER/12`,
  `WebUI\AuthSubnetWhitelistEnabled=true`, `WebUI\LocalHostAuth=false` so
  docker-network peers skip auth entirely.
- Dead public trackers flip jobs to engine `error` within seconds. When a
  magnet fails, retry with a known-live swarm (e.g. an Ubuntu release
  torrent) before suspecting your plumbing — defunct trackers
  (leechers-paradise et al) are the usual cause.
- Verify a finished archive cheaply: range-fetch the first bytes and check
  magic numbers — `curl -r 0-5 | od -A x -t x1z`; 7z = `37 7a bc af 27 1c`,
  zip = `50 4b 03 04`. Catches truncated files and HTML error pages without
  downloading the whole file.
- Selective grabs from SET torrents (one .torrent per collection, thousands
  of files inside): add with `stopped=true`, set all files `priority=0`
  (filePrio ids are PIPE-separated `0|1|2` — comma lists fail 400 — and
  chunked ~500 ids/call), set the target `priority=1`, THEN start. Any
  priority call after the start races the downloader — a good swarm has
  already pulled the whole set. Recipe: `references/set-torrent-sources.md`.
- A patched source file is NOT live until the API container restarts: the
  code is bind-mounted with no `--reload`, so both the served responses and
  a probe run inside the container can be stale. Whenever behaviour is
  unchanged right after an edit, compare the module's mtime against the
  server process start time (`docker exec <api> stat -c %y <module>` vs the
  uvicorn start) before re-debugging the logic.
- Probe the live stack from INSIDE the API container
  (`ssh <host> 'docker exec -i <api> python3 -' < probe.py`): env creds are
  in place, the engine resolves by docker name, and secrets never enter
  your transcript.

## Direct-URL mode (Internet Archive / DDL)

- Stream with httpx (`follow_redirects=True`, no total timeout), write in
  ~1 MB chunks, update progress in the DB ~1x/s, isolate each job in its
  own subdirectory.
- Prefer Content-Length as the total for progress; some hosts omit it —
  fall back to progress-less "downloading" state.

## External-downloader imports (the slskd / Soulseek pattern)

Registering files that ANOTHER downloader produced (slskd, other
clients), plus the availability-first UX on top:

- Two import semantics, chosen by ownership. MOVED: when the producer
  prunes its own tree (slskd retention deletes completed downloads),
  serving in place rots — rename into cache ownership (instant on one
  filesystem). SERVED-IN-PLACE: read-only master libraries (music /
  movies collections) — never copy, never delete on job removal;
  deleting the job only unregisters the row.
- Pinned slskd grabs land FLAT: `<downloads>/<destination>/<basename>`,
  no remote subdirectories. Verify the on-disk layout with find BEFORE
  wiring the import; a wrong rel path makes the import 404.
- Import records carry a meta JSON (source, peer, console): it drives
  delete semantics (purge cache-owned dirs, never library masters) and
  later browsing/grouping.
- Purge safety: resolve() the target and require `is_relative_to(root)`
  before rmtree. Same guard on the PUBLIC file route — rel_path is
  client-supplied and must not escape save_path via '..'.
- A job stuck at 100% "downloading" after all transfers succeeded = the
  import call is failing and the error is being swallowed. Surface
  import errors into job status; first check the import endpoint's
  response and the destination dir's real path.
- Availability-first: index the master library (dir names — artist/album
  and movie dirs), rebuilt on a timer + once at boot, and check it
  before downloading; hits serve in place (instant links). Gate the
  check by the request's media type — a game query must not surface the
  "Doom" movie or soundtrack albums.
- Exact slskd search/enqueue/transfer API shapes (with the search-limits
  trick that cuts completion from ~45 s to ~2 s):
  `references/slskd-source.md`.

## Targeted single-item acquisition (the "get me ONE game" pattern)

Curated per-game collections on archive.org are the best source: Redump /
No-Intro sets where every game is its own archive. Fetch an item's metadata
JSON for its file list — a 900 GB item costs the same as a 1 GB one (only
the list is fetched). Full verified identifier map + wiring recipe:
`references/ia-redump-sources.md`.

Resolver rules that survived contact:
- Cache each item's file list to disk (24 h TTL) AND warm every source at
  startup (bounded concurrency, ~6 in flight) — first-search latency
  otherwise kills the UX.
- Normalize titles: lowercase, strip punctuation, fold roman numerals
  (Mortal Kombat 2 == Mortal Kombat II), then cut the title at the FIRST
  ` (` marker ("Virtua Fighter (USA)" → "virtua fighter").
- Rank: exact title > title-prefix > guarded fuzzy tiers; then retail
  before flagged builds; region (usa > world > europe > japan); disc
  number; size asc (last tiebreak only — never size-first, "Virtua
  Fighter Kids" must not beat "Virtua Fighter").
- Flagged builds rank below clean retail but stay selectable: NON-RETAIL
  (beta/proto/demo/sampler/preview — match promo words by WORD BOUNDARY
  so "Demolition" stays clean), TRANSLATION ("[T-"), HACK, BAD DUMP.
  A promo disc winning the size tiebreak is the classic preselection
  failure — it looks like the game but downloads a sampler.
- Fuzzy matching must be GUARDED or it reintroduces "Tower of Doom" ↔
  "Doom" noise: word-boundary substring only for queries ≥8 chars;
  all-tokens-present (any order) only for ≥2 tokens; queries under 4
  chars are exact-only.
- Dedupe key = (title, region, rev, flag, FORMAT, DISC). Mirror items
  carry duplicates, but format and disc MUST be in the key: without
  format the PBP copy masks the CUE/BIN copy (different user choices);
  without disc a multi-disc set collapses to Disc 1 only.
- Selection default: ONE best release per platform; multi-disc sets
  expand to all discs of the chosen release — never half a game.
- **Fan-out rule for "all" sentinels**: when the platform/console filter is
  a sentinel meaning "search everywhere", the code MUST iterate every wired
  source. Mapping "all" to an empty list no-ops every console-less request —
  user-visible symptom: "the UI doesn't find anything".
- Offer a dry-run mode that returns ranked candidates without downloading —
  it is the fastest way to debug bad or empty matches.

## Wiring a new source (verification recipe)

1. Find candidate items via archive.org advancedsearch (title fields +
   `output=json`).
2. Check shape: `https://archive.org/metadata/<id>` — per-game sets are
   hundreds+ of game-named archives (good); a handful of multi-GB blobs is
   a whole-set dump — for direct-URL sources that means no single-item
   targeting (skip), but for set-TORRENT sources it is first-class: the
   engine can selective-download just the requested file.
3. Wire the identifiers, then probe in order: dry-run one known item → real
   download → serve check (HTTP 206 + correct magic bytes) before calling
   it wired.
4. Set-torrent sources (one .torrent per collection — worked example:
   Minerva Archive: no auth, JSON search + filters API, per-set .torrent
   with trackers): full recipe in `references/set-torrent-sources.md`.
