# Taste-fill sweep: finding + filling missing studio albums

Scoped fill job (not a blind discography grab) against the downloader
fleet. Proven end-to-end on the downloader fleet.

## Discovery

1. Pick artists from the gap audit (scripts/gapclean_audit.py rows + a
   taste filter), not by hand-listing.
2. Per artist: collect library album-dir norm names, then query a lane
   /search/json?q=<artist>&type=album&limit=200.
3. Missing = result album whose norm title is absent AND not a prefix
   match of a present dir (that is an edition-of-present). ALWAYS filter
   by the result's artist field (norm equality): plain album search
   returns tribute/lullaby/spa-knockoff albums and cross-artist matches
   (searching CORPSE returns Cannibal Corpse albums).
4. Hand-curate the final list from machine candidates: studio albums
   only (lives/comps/remixes/singles out per house rules). A search hit
   typed "album" that holds 1-2 tracks is a single wearing album type -
   it will land as a new 1-track dir; that is a kept single, not a fill
   failure, so do not re-dispatch it.
5. Titles/URLs stay server-side: store JSON under the quarentine scope
   dir and resolve by norm-keyword against the stored titles. Never
   hand-type album names in commands - typed literals get mangled in
   transit.

## Dispatch

- rygrab.py --url <lane url> --platform <lane> --platforms <lane>. The
  --platforms override is REQUIRED when any default lane auth is expired
  (default priority includes tidal); --platform alone does not
  override the default lane set.
- Lane fallback ladder: Tidal only (Qobuz + Deezer sidelined and
  Spotify decommissioned — all 2026-09-21).
- Lanes purge completed job groups fast: job ids die quickly. Verify
  landings by re-reading library dir audio counts, never by job status.
- Silent-failure diagnosis: job produces files surfaced
 error gets checked docker logs <lane>-headless --since 90m for
 per-track 'Failed get download URL' lines before any re-dispatch;
 signature move down ladder instead re-sending (same
 lane, same result).
- Organizer had TWO silent-drop bugs (found + fixed 2026-09-13,
 commits 658330f/225f557/e751db9): (1) already_in_library gate passed
 on album-dir presence alone - track-aware _library_has_identity and
 _library_has_identities now check title-core/track-number per track;
 (2) _verify_imported_album passed on 'album dir has audio' without
 proving the staged files landed - now requires staged byte-sizes in
 the library census. Symptom was hole-fill tracks 'done' in 300ms
 then never appearing; audit rows (event=done/skip/reason) are the
 ground truth, not queue DONE count.
- Beets routes tracks by their OWN tags: a single-track grab of 'Scarred'
 (album tag Scarred) becomes Combichrist/Scarred/, not the intended
 album dir. Verify landings against the beets DB (/app/.config/beets/
 library.db inside organizer) or library-wide title search, not the
 planned dir. Umlauts/leet ('Lügner!'→'Lugner!') also defeat naive
 matching.
- beets config quirk: Qobuz track titles stored tracklist-style omit
 words ('Burning Down House' vs 'Burning Down the House') - fuzzy
 title matching must tolerate this.
- Some titles exist on only one lane: Spotify lacks the Revolting Cocks
  Sex-O Olympic-O original (only the MiXXX-O remix, which is out by
  house rules). A blocked title waits on lane repair; it does not take
  a substitute edition.

## Landing verification + dup resolution

- Beets re-routes tracks by tags: the grabbed edition can land in a
  DIFFERENT dir than the URL's edition (combined deluxe vs separate
  disc; plain artist dir vs comma-credit artist dir). Merge against the
  dir the organizer actually created.
- Verify track count >= 8 (or known tracklist) before calling a landing
  a full album.
- If the grab supersedes a pre-existing copy of the same album,
  quarantine the loser only after every loser track title-matches the
  keeper; scripts/gapclean_phase8_fill_dedupe.py is the reference
  implementation (keeper = bigger count; tie keeps the pattern-defined
  keeper).

## slskd lane (bootlegs, rarities, MB-unknown material — user intent)

slskd's role in the fleet is NOT mainstream catalog (the four provider
lanes already cover that): it exists for gap filling, bootlegs, and
material the main services do not have. Dispatch order for any grab:
search all four provider lanes first; only when the title is absent
everywhere, fall to slskd.

- slskd API: `X-API-Key` header (key lives in
  your slskd config file, under `web.api_keys`), base
  `http://IPVPLACEHOLDER:5030`. Flow: `POST /api/v0/searches
  {"searchText": "...", "fileLimit": 50}` -> poll `GET /api/v0/searches/
  <id>` until Completed -> `GET /api/v0/searches/<id>/responses`
  (includeResponses on the search route returns empty; responses route is
  authoritative) -> `POST /api/v0/transfers/downloads/<username>` with
  `[{'filename', 'size'}]` pairs URL-encoding the username. Responses
  carry backslash Windows paths; filter by folder substring, not exact
  filename.
- Downloads land in slskd's configured complete dir (check the
  `downloads:` key in slskd.yml — currently `/storage/nzbdl/complete` =
  `/your-media-path/nzbdl/complete/<folder>`), NOT the container /app/downloads.
- Stage grabs under `/storage/fleet/<Artist> - <Album>/` and enqueue
  the organizer with `source_kind: "slskd"` — the organizer's MusicBrainz
  gate then validates tags (see organizer-mb-gate notes below).
- Prefer lossless responders (FLAC) over mp3 when both exist; verify
  tags with mutagen after transfer, before staging.

## Organizer MusicBrainz gate (source_kind slskd/upload)

- Untrusted-source imports (source_kind != provider) run a GATED beets
  config: MB autotag, strong_rec_thresh 0.02, quiet_fallback skip,
  duplicate_action keep. Clean exit with nothing landed -> staging moves
  to `/storage/fleet/quarantine/gated/<job_id>/` and the job FAILS
  `no_musicbrainz_match` (no retry). Kill switch env
  ORGANIZER_MB_GATE_KINDS. Gate code: organizer/engine.py
  `_import_gated`; gated config ships in repo as organizer/config-gated.yaml.
- Single-track hole-fills MUST import singleton mode: the engine picks
  `--singletons` when the staging dir holds exactly one audio file.
  Album-mode matching of a 1-file dir vs a 12-track MB release scores
  ~0.6 (missing-track penalties) and always skips; track-level scores ~0.
- Landing proof is TWO checks ORed: staged byte-size census match, and
  beets-DB items added since import start (gated config has
  import.write: yes, which rewrites tags and changes sizes). The DB check
  also yields the actual landing dirs for enrichment — never enrich from
  the manifest's target names, beets lands under MB-corrected names.
- The gate is a MusicBrainz dependency, not a quality gate: bootlegs ARE
  often registered in MB (proven: the Tool 'Tales From The Darkside'
  bootleg matched and landed cleanly), but genuinely unregistered
  material will fail-closed to quarantine. That quarantine pile is the
  intended review surface for rarities — inspect and hand-import, do not
  loosen the threshold.
- **Quarantined-but-correctly-tagged releases: re-import with asis.**
  Proven 2026-09-18 (Burzum Filosofem, Gojira Possessed 1997 EP): files with
  complete correct tags (artist/album/date/tracknumber verified via mutagen)
  still skip under the tight threshold, and a manual `beets import --quiet
  --quiet-fallback asis --singletons` on the quarantined dir lands them
  perfectly. Tool: `tools/slskd-headless/scripts/retry_quarantined.py`
  (dry-run default, `--yes` to import; retries every gated batch, or one
  via job-id). ALWAYS verify tags with mutagen before trusting asis — the
  gate exists because slskd tags can lie wholesale; asis is only safe on
  files you have personally inspected.
- Synthetic-gate-test gotcha: generate test FLACs with real duration
  (`ffmpeg -f lavfi -i sine=...`) — mutagen-built zero-sample files take
  a track_length penalty of 1.0 and fail the threshold even with perfect
  tags. Rate-limit awareness: beets retries hammer musicbrainz.org and
  503s mask as 'no match'; space gated tests out.

## Title-core normalization (dup verification)

Apply in this order - later steps corrupt earlier ones: strip trailing
"(Bonus Track)"/"(Album Version ...)"/"(... mix)" parentheticals; strip
leading track numbers; map the spade suit char to "spade"; map "&" to
" and " (spelled-out vs symbol titles differ between releases); map leet
chars 0/1/3/4/5/7/8 to o/l/e/a/s/t/b; strip brackets; alnum-lowercase.
Stripping track numbers after leet mapping turns "04" into "oa" and
breaks prefix matching.