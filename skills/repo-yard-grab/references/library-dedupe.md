music-library library dedupe regroup

Class: bulk repair`/your-media-path/library/music-library`(canonical library,
organizer-written). Covers duplicate-artist/album merging, twin-track
trimming, stub-dir regrouping, gap backfill. All work move-to-quarantine
(reversible)delete. Quarantine root:
`/your-media-path/__Junked/quarentine/<name>-<date>/`.

## Gap definition (user, 2026-09-13)

Missing SINGLES are not gaps. Album-level gap = dir with >=3 tracks whose
leading track numbering has holes (scripts/gapclean_album_holes.py), plus
blocked titles (Sex-O Olympic-O, deezer lane). n<3 dirs = singles, ignored
until the user reopens that lane.

### The authoritative gap signal: the file's own TRACK tag

Filename numbering holes are a weak proxy. The strong signal is the embedded
`TRACK` tag, which beets wrote from the release's real tracklist at import:
`n/N` with N>1 PROVES the album is short by N-n. Read it with mutagen
(`OggOpus(path)["tracknumber"]`) — ffprobe `format_tags` can come back empty on
opus. Classify each 1-track dir:

    tag_total_gt1    TRACK "n/N", N>1    definitive gap (N-n missing)
    tag_pos_gt1      TRACK "n",  n>1     probable (part of an album, no total)
    album_named_dir  dir named for the album, no total — ambiguous

Library-scale context: ~45% of this library's album dirs hold ONE track, and
those split roughly 45% fragments / 55% legitimate singles.

### Compilation fragments inflate gap counts — filter them out

A 1-track slice of a chart compilation carries `TRACK "x/500"`, so a naive
`implied_tracks` read scores it as 499 missing tracks **of that artist**.
Unfiltered this reported 190,850 "missing" tracks; two guards brought it to
36,440, and the popular/studio-album filter to 7,376:

- Drop albums whose name or album tag matches a compilation pattern
  (greatest/hits/best of/rolling stone/1001 songs/top N/anthology/...).
- Drop `implied_tracks > ~40` — a real album, not a chart list.

`Rolling Stone 500 Greatest Songs` here is ONE compilation split across 168
artist dirs / 257 tracks. Those fragments are not gaps: consolidate into a
single `Various Artists/<album>/` keeping the rank as track number (merge, so
all 257 survive).

### Incidental artists are not gap-fill targets

Separate artists whose whole library presence is a compilation fragment or a
single pulled-in song. Incidental when real (non-compilation) tracks <= 3 AND
no own-album gaps; substantial when it owns >=1 multi-track album and >=8 real
tracks. ~743 of 4,311 fragment-bearing artists were incidental — one song off a
chart compilation filed under their own name. Never read those as incomplete
discographies.

### Verify before it enters the fill list

Check each candidate against MusicBrainz: the TRUE track count, and that the
release is a studio album at all. An edition mismatch is not a gap (the library
holding the Deluxe 21-track while the tag implies a 12-track standard is
complete, not short). Tag-implied counts also disagree with what a lane actually
serves — see `references/manual-beets-import.md` on box-set numbering traps.

## User's standing rules (1-copy-per-album library policy)

- Keep ONE copy per canonical studio album; lives, comps, remixes, dubs,
  EP fragments go to dated quarantine, not deleted.
- Keep the most-complete edition (deluxe/expanded/Refill-style bonus) as
  the single copy.
- Explicit wins over clean/radio/edited twins; censored-title twins
  (`____`) get dropped when an uncensored sibling exists.
- Removal is always `mv` into quarantine with artist-preserved paths,
  so restore = copy back.

## Keeper decision: which twin survives

Title normalization finds the clusters; it does NOT decide the keeper. Rank on
these, in order:

- **Beets registration is decisive only when one side HAS rows.** Query the
  items table for the dir path (`SELECT count(*) FROM items WHERE path LIKE
  '<artist>/<album>/%'`). A registered dir is the live copy; an unregistered
  twin is a disk orphan safe to move. But the DB holds only the
  organizer-imported subset — most of the library predates it and shows **0
  rows on BOTH sides**, so "0 rows" alone proves nothing library-wide. When
  neither side is registered, fall back to substance (album/file count) plus
  the same-act check below, and abort if an intended orphan IS registered.
- **Prefer the registered copy even when the orphan looks better on one
  metric.** Do not merge by swapping the library pointer.
- **Measure quality at FORMAT level:** `ffprobe -v error -show_format -of json
  <file>` → `format.bit_rate`. Opus exposes no stream-level `bit_rate` (it
  reads 0), so a stream-level probe returns nothing and you cannot rank by
  bitrate at all.
- **Byte size only ranks files with the SAME filename.** Same names + different
  sizes = a different encode of the same track (rank by bitrate). Different
  filename sets = a different edition — diff the tracklists before assuming
  either is redundant.
- **Edition pairs are not automatic duplicates.** Two dirs whose normalized
  titles match where one is Deluxe/Expanded/Anniversary are different
  releases. Keep the more complete one as the single copy ONLY if the
  tracklists are equal; otherwise they are genuinely distinct.
- **Hardlinks reveal prior passes.** `stat -c '%h %i' <file>` — a link count of
  2 means the file is already mirrored into `__Junked`; check before treating a
  dir as untouched.

## Box set / compilation triage (do this BEFORE any hole-fill)

A dir that reports "short" (lane `expected_tracks` N, `fetched_tracks` M<N) is
NOT automatically a hole to fill. Test whether it is a compilation first:

1. Normalize each track title (lowercase, strip the `NN - ` prefix, drop a
   trailing parenthetical, collapse non-alphanumerics), then ask how many of
   this dir's tracks also appear in OTHER album dirs of the same artist.
2. If most map out to the canonical albums, it is a box set/compilation. The
   "missing" tracks are usually just the one album whose own dir already
   exists — nothing is actually absent.
3. Confirm identity externally before acting: Discogs/Spotify/Amazon label it
   Box Set / compilation, and the missing track NUMBERS correspond to a real
   release already in the library.
4. A compilation is not a library gap. Per the house rule it goes to
   quarantine — do not re-dispatch it to "fill" its gap.
5. **The only part worth keeping** is a release the library LACKS (an EP or era
   not held as its own dir). Split that subset out as its own album dir,
   renumber from `01`, and quarantine the compilation.

## Artist-dir merge (article / case / punct variants)

Safety order: unicode-fold (safe), then **article** ("The X" vs "X"), then
case/punctuation. The latter two are NOT blind merges.

**Verify same-act before merging any case/punct/article pair.** Album titles
reveal genre and era; if they disagree the dirs are different acts however
similar the names:

    Subhumans      UK anarcho-punk (The Day the Country Died, EP-LP)
    The Subhumans  Canadian punk (Incorrect Thoughts 1985, New Dark Age Parade)
    Trex           drum & bass (DLR Remix, Dopamine VIP)
    T. Rex         glam rock (Tanx, Bolan's Zip Gun)

Merging those on name similarity destroys a discography.

**Direction = the substantial side** (more albums/files); the stub folds in.
The article-bearing form is the convention when both sides are real, but
substance wins when they disagree.

**Collision refusal is triage, not a dead end.** The dry run refuses any pair
whose normalized album name appears on BOTH sides. Most such collisions are
the SAME recording with a year/edition suffix (`GI` vs `GI (1979)`,
`Hold It In (2014)` on both sides). Resolve at content level: equal track
count AND total duration within ~5s → same recording; keep the keeper-side
copy, quarantine the source-side twin, and the freed name lets the rest of the
pair merge. Differing count/duration means distinct releases — leave those for
a manual keeper call.

**Guest/credit-suffixed dirs are mostly NOT merge candidates.** A suffix sweep
(`feat.`, `with`, `&`, `,`, ` x `, ` vs. `, `_`) matched ~1,150 dirs across
~600 base artists here, but only ~16 shared an album name with the base and
most were legitimate distinct singles. Classify by album size before merging:
every album ≤2 tracks → real single; ≥4 tracks → real collaboration. Require
the separator form — plain prefix clustering over-matches (`Break` →
`Breakfast`).

Planner with collision guards, content-level twin comparison, and rollback
emission: `scripts/artist-merge-plan.py`.

## Generic / odd artist dirs

Dirs named `_`, `VA`, `Various`, `Various Artists`, `NONE`, `Soundtracks`,
`Original SOUNDTRACK`, `d` hold REAL releases whose artist tag is missing.
Resolve by reading the audio file tags, then rename or move the album into the
right artist dir — never delete for the name alone.

Short names are not automatically junk: `K7`, `L7`, `M1`, `T3`, `U2` are real
bands, and `X` is X Japan (BLUE BLOOD, Jealousy, Los Angeles, Vanishing Vision
are genuine albums). Read the album titles before flagging a name as generic.

## Proven one-shot scripts (live in /var/tmp/dedupe-audit/, re-usable patterns)

- `audit.py` — library-wide dup scan: duplicate artist dirs (normalize
  casefold+alnum), duplicate album clusters (version-words regex strip:
  deluxe/expanded/remaster/year/etc), twin tracks (same track number +
  normalized title), format twins, fragment dirs. Writes report.txt.
- `gaps.py` — empty album dirs, missing track numbers per album
  (disc-aware `01-02` numbering), zero-byte files. Writes gaps.txt.
- `stubs.py` — album dirs with <3 audio tracks (1-track stub census).
- `dedupe_albums.py` — moves duplicate album dirs to quarantine, keeping
  most-files then dated copy; SKIPS clusters where tie-copies have
  different content (compare track sets, not names).
- `stub_regroup2.py` — merges 1-2-track stub dirs into real album dirs by
  the files' own ffprobe tags. SEE PITFALLS below before adapting.

## Pitfalls (all observed, each cost hours)

- Artist dirs with leading special chars ('*NSYNC') break glob/editing
 everywhere. Quarantine the odd dir, recreate as clean name ('NSYNC'),
 AND retag the files (mutagen easy tags) so Navidrome groups under the
 letter users actually browse (n, not *).
  `re.sub(r"[/\x00]","_", os.path.join(BASE, artist, album))` turns the
  WHOLE path's slashes into `_`, producing literal `_your_media_library...`
  dirs scattered across the tree. Apply `re.sub` to each component before
  joining.
- **Reject polluted tags before trusting them for paths.** ffprobe tag
  values can contain absolute paths/URLs; a dest built from such a tag
  with a naive sanitize pollutes the tree (same mangling as above).
  Rule: tag starting with `/` or containing `_mnt` → fall back to
  directory-name-derived artist/album.
- **Probe tags in parallel (16x ThreadPoolExecutor).** Sequential ffprobe
  over ~17k files = 60-90min; parallel = ~10-20min. One probe call per
  file, all three tags (artist/album_artist/album) from that single call.
- **Hash-compare on collision.** When target filename exists, sha256 both
  files: identical → remove incoming; different → rename with
  `(stub N)` suffix, keep both.
- **Same-name clusters with different content are NOT dupes.**
  `(Remix 2016)` vs `(remix 2016)`, clean vs explicit, year-comp variants,
  non-Latin titles — normalized names collide, content differs. Compare
  track sets before any merge; skip cluster on disagreement.
- **Check `ps aux | grep ffmpeg` before touching tmp files.** Organizer
  conversion legitimately writes `tmpXXXXXXXX.opus` beside finals and
  renames on completion; deleting mid-flight loses an hour of conversion.
  `tmp*.opus` with a zero-byte or duplicate final = leaked intermediate
  (organizer restart mid-transcode); sweep only those.
- **Read output files with leading-space stripping in mind.**
  Audit reports indent lines with 2 spaces; `l.strip()[2:]` double-strips
  a leading space of paths containing spaces. Use `l[3:]` on exact-width
  formats or parse with regex capturing to end-of-line.
- **Library-scale scans (~200k files) take minutes.** Run in background
  with notify; do not foreground-block. Ntfy progress every ~4k dirs on
  long passes; user confirmed hourly+ ntfy warranted, sub-hour not.

## Root causes already fixed (don't re-investigate)

- Stub explosion (17k 1-track album dirs): Tidal track-mode mega-
  dispatch, one dir per track. File metadata intact — regroup by tags.
- `tmp*.opus` leak: organizer restarted mid-transcode leaves 0-byte
  intermediates; finals survive.
