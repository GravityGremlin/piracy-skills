# Discography grabs - the verification pass

`rygrab.py --artist "<name>"` dispatches the lane resolver's set, but the
resolver is NOT the whole catalog. ALWAYS run the verification pass after a
discography drain; the gap sources below are invisible in the "completed"
statuses.

1. **Resolver-missed releases.** The lane resolver (tidalapi
   `artist.get_albums`, >2-track filter, title dedup) can omit releases that
   search returns - verified: multi-track EPs present in `search/json` were
   skipped by the discography dispatch. Cross-check: fetch
   `/search/json?q=<artist>&type=album&limit=100` on the lane, filter rows
   whose `artist` equals the requested name exactly, diff against the queued
   titles, and enqueue misses individually:
   `--url https://tidal.com/browse/album/<id> --platforms tidal`.
2. **Throttle drops.** Parallel album fetches trip Tidal 429s; the lane
   retries a throttled track 5x then DROPS it silently. Expect per-album
   gaps of 1-4 tracks after any multi-album dispatch. Signatures: library
   opus count equals the lane job's `data.source_quality.lossless_tracks`
   (imports never lose files - a count MATCH means the track was never
   fetched), and the library numbering shows holes (`NN -` prefix absent
   between neighbors).
3. **Fetch-side vs import-side.** Only when the library count differs from
   the lane's lossless count is it an organizer/import problem. Fetch-side
   gaps are repaired per the fleet skill's
   `references/hole-fill-single-tracks.md` (provider-lane hole-fill is
   currently broken - do not re-dispatch the album).
4. **Provider-gap releases (not a resolver miss).** The lane's whole catalogue
   can lack an album the artist really released while carrying an alternate
   pressing of it. Measured 2026-10-17: Thumpasaurus' studio "Gas Cheaper Here"
   never appeared in lane search results — only "Gas Cheaper Here (Refueled)"
   (live). Lyric/alphabet cross-checks against MusicBrainz or the artist's
   Spotify release list expose titles the lane never returned at all; source
   those from slskd or Bandcamp instead of re-dispatching the lane. Never
   present a live/alternate pressing as the studio album.

## Per-album audit recipe

For each album dir on disk: count `NN - *.opus`. Get the lane tracklist via
the in-container script (`with a.app_context(): get_session().album(id).tracks()`)
and diff by track NUMBER - the lane job data enumerates the same set, so the
three counts (Tidal track_count, lane lossless_tracks, library opus) tell the
whole story. Keep the album->id map from the dispatch/job data; a release can
legitimately skip numbers that do not exist on the provider.

## Expectations

- The lane filter includes multi-track EPs and live albums (>2 tracks) and
  excludes 1-2 track singles; house rules (studio albums only) are NOT
  applied by the lane. If the user wants curation, dispatch curated albums
  individually instead of the artist endpoint.
- Gap-check the library with normalized names BEFORE dispatch
  (`rygrab --lib "<artist>"` plus the normalized-match recipe in SKILL.md).
- A discography dispatch is many parallel fetches - if fidelity matters more
  than speed, dispatch in smaller batches to reduce throttle drops.
