# slskd search probing (Soulseek availability + query behaviour)

Use when you need to know what Soulseek actually has for a release, or when a
lane search came back empty and you must decide whether the network or the lane
is at fault. Probing is search-only: it never queues a download.

## Endpoints (slskd 0.26.x, direct on http://IPVPLACEHOLDER:5030)

- `POST /api/v0/searches` body `{"searchText": "<artist album>", "id": "<uuid>"}`
- `GET /api/v0/searches/{id}` -> `state`: `InProgress` | `Completed` |
  `Completed, TimedOut` | `Completed, ResponseLimitReached` (250-user cap) | `Cancelled`
- `GET /api/v0/searches/{id}/responses` -> `[{username, files:[{filename,size}]}]`.
  The metadata route shows an empty responses array once the search completes;
  always read the `/responses` sub-route.
- Header `X-API-Key` from the lane `.env` (`SLSKD_API_KEY`). Verify auth rather
  than assuming either way - an empty key can still get 200 if auth is off.
- Lane-side search-only surface: `GET http://IPVPLACEHOLDER:19496/search/json?q=<query>&limit=30`
  (bearer `HEADLESS_TOKEN`). Use this to confirm the lane agrees with a raw probe.

## Rules that cost time when ignored

1. **Never DELETE a search that is still in flight.** slskd raises
   `DbUpdateConcurrencyException` in its search task and then every subsequent
   search completes with 0 responses until it settles - indistinguishable from
   "not on Soulseek". Let slskd expire finished searches.
2. **Space searches ~40s apart, 60-90s response window.** Back-to-back searches
   get dropped and come back as 0 users, which reads exactly like a real miss.
   For interactive UIs (never probes) an explicit `responseLimit` +
   `searchTimeout` (ms) on the create call bounds completion — popular
   queries ~2s, rare ones at the timeout — at the cost of a truncated
   result set. Probing always keeps the full window; exact shapes:
   `self-hosted-debrid` skill, `references/slskd-source.md`.
3. **A single 0-user sweep is inconclusive - re-query before concluding.**
   Measured on the same account and session: `Da Drought 3` -> 255 users while
   `Lil Wayne Da Drought 3` -> 0 (twice); five phrasings of `Selected Ambient
   Works` -> 0 while `Aphex Twin Xtal` -> 250 responses 43s later, with slskd
   logging each as completed-with-0 and no error. Re-query with a shorter or
   differently-shaped string and compare.
4. **Counts are indicative, not proof of a good copy.** Soulseek matches
   filename substrings, so hits include unrelated releases by the same artist
   and fan-made compilations - a never-distributed one-copy album still shows
   hundreds of "hits". Inspect sample paths and validate a result before
   trusting it; keep one such album as a permanent negative control.
   - Corollary (the ENUMERATION trick): because the match is on FILENAMES, a
     term that lives only in the DIRECTORY name matches NOTHING — querying
     `Artist <album title>` returns 0 even when the folder is widely shared.
     To enumerate an album folder, fire distinctive individual TRACK titles
     and union the dumps. That is also how you size a copy (8 rows, one per
     track = complete) before dispatching it as a `kind=album` seed — see
     `references/slskd-dispatch.md`.
5. **Flush results to disk after every query.** Sweeps are long and
   interruptible; re-running a query costs a minute, losing the sweep costs the
   session. Record state, users, audio-file count and 3 sample paths per query.

### Anniversary/reissue hunts: fire the token ladder, union everything

Five raw shapes for `Apoptygma Berzerk Kathy's Song XXV` (digital single
2025-12-22, scene WEB-FLAC + 2026 vinyl rip), same session:

| shape | responders | contains the reissue? |
|---|---|---|
| `Apoptygma Berzerk Kathy's Song XXV` | 0 | - |
| `Kathy's Song XXV` | 0 | - |
| `Apoptygma Berzerk Kathy's Song` | 111 users / 583 files | **no** - legacy copies only |
| `Apoptygma Berzerk XXV` | 8 users / 50 files | **yes** - every complete copy, incl. scene WEB-FLAC + 24/96 vinyl rip |
| `Kathy's Song Come Lie Next To Me` | 78 users / 280 files | no |

Same pattern in parallel searches: `Tyske Ludder
Creutzfeldt` -> 0 and `Ludder Creutzfeldt` -> 0 while `Tyske Ludder` -> 57
users / 1543 files (`Tyske Ludder Creutzfeld` -> 9). It is the SHAPE, not the
length: in the 2026-09-30 session the 63-char `Tyske_Ludder-Creutzfeld-DE-
Limited_Edition-VINYL-FLAC-2026-FWYH` and every `-DE-Limited…`-onward prefix
of it returned 0 while `Tyske_Ludder-Creutzfeld` answered with the rip-holding
peer - and a 58-char `Mortiis-Ghosts_…-FWYH` folder answered fine. The lane's
album expansion now ladders these prefixes itself (deployed 2026-10-01);
hunters still probe raw with the short shapes.

- Fire AT LEAST: [artist + anniv token], [artist + core title], [full title
  words]. Any one shape can be the only one that reaches the sharers; the
  longest full-phrase shape is the most likely to return 0.
- Union ALL response dumps - plus the lane `/search/json` rows, which carry
  `dir_lossless`/`dir_files` per copy - before concluding anything. A 111-user
  sweep containing zero reissue copies looks rich and proves nothing.
- Shape is more reproducible than time: the same `Apoptygma Berzerk XXV`
  query fired by two different clients returned the identical 8 users.
- Rank the union with `scripts/slskd_rank.py` (see ops-notes), never by
  eyeballing console output - stdout truncation hides result sets you already
  have on disk.

## Measuring off-streaming status (third-party, no auth)

- Deezer: `https://api.deezer.com/search/album?q=artist:"X" album:"Y"&limit=5`
- Apple: `https://itunes.apple.com/search?term=<artist album>&entity=album&limit=5`
- Score on artist + title match, never on raw hit count. Near-misses are
  everywhere (`1017 Thug 3 The Finale` for `1017 Thug`, `Over the Edge Vol. 8`
  for a self-titled record, a single for an album). Print the matched title
  beside the verdict so a wrong call is visible instead of silent.
- Absent on one service is not absent everywhere, and licensing moves. Treat
  "off-streaming" as a dated claim, keep a retired list of releases that have
  since arrived on a DSP, and re-probe before reusing an old finding.

## Artifact shape that worked

- Raw measurements as dated JSON under `docs/data/` (one file per sweep).
- Probe scripts under `scripts/` (`probe_dsp_availability.py`,
  `probe_slsk_availability.py` with an `--only-zero` re-measure mode).
- A render script that rebuilds the markdown document from the JSONs, so the
  document is never hand-edited and every number is traceable.
- Document opens with method + caveats, then tiers the cases (off-streaming and
  rich / off-streaming but thin / negative control / normalization stress /
  controls that are also on DSPs), then retired cases, then how to fire one.
