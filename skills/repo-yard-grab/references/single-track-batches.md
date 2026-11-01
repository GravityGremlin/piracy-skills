# Batches of single songs from a list (song-list requests)

Use when the user pastes a LIST of songs (often noisy: wiki bullets, quiz text,
video-description pastes, adjacent stray lines) and asks to "find them / add them
to the library". The paste is a raw lead, not a spec: extract song+artist pairs,
ignore non-song lines (they are usually paste overflow from the source page).

## 1. Presence check FIRST — flexible matching or you re-download what exists

For each song, search music-library with variant-tolerant patterns:

Match with variant SETS on BOTH sides — naive normalized equality reports
nearly a third of real hits as missing (measured 65% → 98% on a 49-track
fixture):

- titles: strip leading track numbers; strip bracketed/parenthetical content
  (`(Album Version)`, `(feat. …)`, remaster tags); curly vs straight
  apostrophes (`I'm` vs `I’m`)
- artists: allow "The"-less dirs (`The Dirty Heads` ↔ `Dirty Heads`), feat/with
  and `&`-splits (`Angus & Julia Stone` ↔ an `Angus Stone` dir)
- title-only matches are never safe — require artist evidence even when the
  title looks unique. Measured 2026-10-23 on a 46-track chart list: uniqueness
  alone reported 14 wrong songs as present (Nelly `Just a Dream` → a Blossom
  track, Korn `Never Never` → Dennis Brown, P!nk `Blow Me` → Stock Hausen).
  Different acts share titles constantly. When the artist dir differs, verify
  the candidate file's OWN tags with ffprobe (`format_tags` and `stream_tags`:
  artist + album_artist) and count it present only if the tag matches — that is
  the comp/guest-placement case (Kelis `Acapella` is on David Guetta's *One More
  Love*). Anchor `find -iname` probes to the artist for the same reason.
- comps count as present (a song on a "#1s" comp is IN the library; note the
  source in the report; backfilling the canonical studio album is a separate ask)

Loose `find -iname '*boogie*'` matches unrelated tracks — anchor patterns to the
artist. Verify hits with ffprobe before claiming presence.

## 2. Dispatch missing songs as track jobs pinned to Tidal

Resolve each missing song to its CANONICAL release via the aggregator search
(the user's quoted year disambiguates editions; prefer the original album version
over Classic Masters / 100 Hits comps):

    GET http://IPVPLACEHOLDER:19297/search/json?q=<artist+title>&type=track&sort=best

Then one job per song:

    POST http://IPVPLACEHOLDER:19297/download
      service=tidal  kind=track  url=https://tidal.com/track/<ID>
    -> {"job_id": "...", "status": "queued"}

- Include the Tidal track ID from the search result — never guess it. If Tidal
  lacks the song, fall back to slskd (see `slskd-dispatch.md`).
- The lane auto-enqueues each finished download to the organizer itself; no
  manual beets step. Expect per-track fetch well under ~2 min; the organizer
  polls every ~30 s then converts to opus.
- Watch with `/jobs/unified/json?sort=newest&limit=200` matched by job id;
  terminal states completed/failed. All jobs `completed` does NOT guarantee
  import — keep watching the library (next step) until files appear.
- A job that completes with `phase: "duplicate-skipped"` means the lane found
  the track already in the library — treat as satisfied and verify the
  library; do NOT re-dispatch. (Job records carry: id, service, status,
  phase, progress, title=URL, created, files, error.)

## 3. Landing shape (provider-singleton import)

Each track lands as a singleton inside its album dir:

    /your-media-path/library/music-library/<AlbumArtist>/<Album>/NN - <Title>.opus (+ cover.jpg)

A brand-new "album" dir may hold just the one track — that is the designed shape,
not a defect; later hole-fills merge into it. So the successful-search targets are
`<AlbumArtist>/<Album>/NN - Title.opus`, not `<Artist>/<Title>/`.

## 4. Verify, then refresh the webamp catalog

- Files: confirm the exact paths, ffprobe `codec_name=opus` + sane duration (note:
  opus files carry cover art as a second stream, codec mjpeg — do not misread it
  as the audio codec; ffprobe `-show_entries format=duration` works).
- Webamp (same host as the clones): from the webamp dev checkout run
  `bash docs/sync-library.sh --check` (baseline + drift), then `--install`
  (writes prod + exp via `ssh your-user@your host`, stashes previous builds, resolve-checks
  both origins). Then independently fetch both origins' `/library-data.js`, md5-compare
  to the fresh build, and parse (`raw_decode` — the file ends with
  `;window.dispatchEvent(new Event("wa-library"));`, a plain json.loads chokes) to
  confirm the new artist/track entries and probe their URLs (HTTP 206).
- The generator is deterministic: unchanged starters = byte-identical `library.js`;
  only the catalog md5 should change. If starters change unexpectedly, stop and diff.
