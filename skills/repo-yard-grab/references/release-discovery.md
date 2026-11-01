# Finding fresh releases (scene sites → lanes)

The user's targets arrive as scene release names —
`Artist-Title-Edition-FORMAT-YEAR-GROUP` (FORMAT: VINYL / 2CD / WEB / 24BIT;
groups seen: FWYH, FALCON, OBZEN, TOTENKVLT, ERP) — and are often hours old when
asked about. "Find X" means: locate it, then map it to a lane.

## Where to look

- **scnlog.me** — public and searchable: `https://scnlog.me/?s=<query>` renders
  release name, post date/time (site says times are shown in your local
  timezone), size, category and group tag, newest-first. Genre categories exist
  under Music/ (FLAC, Darkwave, Industrial, Psychedelic, …).
- **goldesel.bz** — German DDL board. Product pages
  `/audio/flac/<id>-<slug>` are public (scene name, Datum, tracklist, bitrate);
  the category feed `/audio/flac` lists the freshest posts (date/time, genre,
  quality, size). Row titles on the listing are NOT `<a>` links — read them
  from `document.body.innerText` (skip the ~2k-char nav header), or go straight
  to a product page once you have the id.
- **predb.me** sits behind a Cloudflare bot check even in a real browser — skip
  it; scnlog is the usable pre-DB-ish index.
- Reads of these sites through keyless scraping backends can 403; driving the
  real browser and slicing `document.body.innerText` is the reliable path.

## Map a release to a lane (in order)

1. Library gap-check with normalized names (SKILL.md "Before grabbing: what is
   actually missing").
2. Tidal / tidal: `GET /search/json?q=<artist title>&type=album&limit=8` on
   the lane (bearer) → album id → enqueue as usual. Label digital releases
   (WEB/24BIT posts) frequently mirror what Tidal holds.
3. Soulseek / slskd: lane `/search/json?q=...` — space queries ~40s
   (`references/slskd-search-probing.md`). Read per-directory `dir_lossless`,
   `bit_depth`, `format`: the scene rip, a label copy and mp3s coexist as
   separate directories; only `dir_lossless: 0` rows are lossy.
4. Day-0 reality: scene-share peers DO carry a post within hours - measured
   2026-09-30/10-01: one peer (`SKYLiGHT_D`, shares organized
   `@@music/<Genre>/<YYYYMM>/<scene name>`) held all three targets of the day
   (FWYH vinyl FLAC, FWYH 2CD deluxe FLAC, FALCON 24BIT WEB) while mp3 twins
   sat on several other peers. The failure mode is search shape, not
   availability: the full scene folder name can return 0 responders
   network-wide and the LANE display may miss the rip-holding peer entirely -
   probe raw (`scripts/slskd_probe.py` + `slskd_rank.py`) with short prefixes
   (`Artist`, `Artist-Title`) before concluding it is not there. Album
   enqueues from such a peer now survive the dropped full-name search (lane
   expansion ladder, 2026-10-01). Vinyl-only/deluxe rip imports can still
   quarantine at the MusicBrainz gate.

## Upgrade-watch pattern

Report what exists NOW and which edition it is; grab only when the user accepts
the later-upgrade path for the cited exact edition. The watch = re-run the same
Tidal + slskd searches days later; vinyl/deluxe rips show up as new peer
directories (check `dir` names for edition markers).
