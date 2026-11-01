# Playlist Curation & /playlists Maintenance

`/playlists` is the hardlink-export tree (beets never organizes it). A playlist
is a folder `<Name>/` of per-track links (organizer mirror names them
`NN - <lib filename>`; hand-built ranked lists use `NNN - <Title>.<ext>` with
the rank prefix = playlist order) plus a sibling `<Name>.m3u8`. `/playlists` is
a *sibling* of the Navidrome scan root and is NOT scanned — Navidrome imports
m3u8 only from inside its library roots, so to surface a playlist there also
write `music-library/<Name>.m3u8` with entries relative to the library root
(historic playlists were auto-imported exactly this way from the old library
root; wait for the scan schedule — auto-scan is hourly and the organizer scan
trigger is disabled). Run mutations inside the organizer container
(`docker exec organizer python3 ...`) — it mounts both `/music` and
`/playlists`; the host paths work too.

## Rebuild an m3u8 against the current library

Old m3u8s rot: they may carry a retired path prefix (e.g. `/music_merged/`) and
reference tracks that were junked or moved. Rebuild by basename match, never by
trusting stored paths:

1. Index the library: walk `/music`, map `filename -> path` for
   `.opus`/`.mp3`/`.flac` (a full walk is seconds at ~150k files).
2. Per old track line: basename in the index -> write the resolved library
   path; absent -> KEEP the original line so the miss stays visible, and count
   it as missing.
3. Format: `#EXTM3U`, then per track `#EXTINF:-1,<Artist> - <Title>` followed
   by the path line. For entries inside the playlist folder, write a relative
   path (`<Name>/NN - Title.opus`) so the file moves with the tree.

Report found/missing counts per playlist. Missing tracks are a user decision
(restore from junk / re-download / drop) — never silently prune.

## Prune the folder, not just the m3u8

A rebuild that only relinks leaves every file from an earlier pass on disk:
ones whose names came from a parser bug (Wikipedia `data-sort-value="X"|`
prefixes leaking into the artist field) and ones renumbered when the rank order
changed. After any rebuild, diff the directory against its own m3u8 — every
`.opus`/`.mp3` whose basename is not referenced is stale — and verify with
`count(referenced) == count(files)`.

Quarantine rather than delete. Playlist entries are hardlinks to library files,
so moving the link loses nothing and costs no space: `mv` them to
`/storage/library/.stale-playlist-names/<Name>/` (outside `/playlists`, so
players and scanners ignore it). Report the count; a non-zero orphan count
means an earlier build was wrong, not merely untidy, and the same builder will
keep producing them until its naming or ordering is fixed.

## Backfill missing tracks (search + enqueue)

For each missing track (artist + title from the old m3u8 path):

1. Search: `GET http://IPVPLACEHOLDER:19297/search/json?q=<title artist>&type=track&sort=best`.
   The aggregator is LAN-unauthenticated by design — no token needed from the
   host (it holds the lane tokens server-side). Prefer a hit whose title
   matches the playlist's defining keyword; title-only queries return wrong
   songs surprisingly often.
2. Enqueue: `POST http://IPVPLACEHOLDER:19297/download` form fields
   `service=tidal&kind=track&url=https://tidal.com/track/<ID>` — use the
   exact `url` from the chosen search row, never a guessed id. Returns
   `{"job_id": ..., "status": "queued"}`. Direct lane enqueue
   (`:19493/download/enqueue` with the lane bearer) also works but needs the
   lane token; the aggregator route needs none.
3. Reject wrong-version rows BEFORE dispatching: remix / live / acoustic /
   karaoke / instrumental / tribute at TITLE and ALBUM level (word-boundary
   `live`, so `Alive` survives — an `Acoustic Live & Rare` comp can outrank
   the studio album on `sort=best`). Prefer Tidal + lossless + studio
   album over comps. On an approximate-title or weak-artist row, flag it in
   your dispatch log instead of dispatching silently.
4. Pace ~2 s between dispatches; batches of ~20 (the lane queue is LIFO, so
   new enqueues run first). Track your own job ids — `/download/jobs/data`
   caps at a rotating 500 rows; `/jobs/unified/json` and
   `/download/jobs/summary` are better for batch bookkeeping. When the queue
   is empty singles land fast (measured ~15 in 6 min) — ETA from queue depth,
   not from the enqueue rate.

New enqueues run FIRST (the lane queue is LIFO) — a backfill never waits behind
an older deep backlog.

## Link landed tracks into the playlist folder

1. Wait for the ORGANIZER import, not the lane job: a lane job can read
   `completed` while the library copy is still importing. If the library match
   is absent, retry on a later tick (`NOMATCH` is retryable, not terminal).
2. Match on NORMALIZED artist + title: normalize the path RELATIVE to `/music`
   for the artist (the artist lives in directory names, not the file stem) and
   the filename stem for the title; require both before a title-only fallback.
3. Create the link (match the folder's existing naming; `Artist - Title.opus`
   for curated folders, rank-prefixed titles for ranked lists): **hardlink
   first** (`os.link`) — verified same-inode across the `/music` and
   `/playlists` mounts (same btrfs, dev 60; works on the host AND inside the
   organizer container), so the user's "hardlinks" requirement is literally
   satisfiable and the files are reachable from both trees at zero extra
   space. Fall back to FICLONE reflink (`fcntl` ioctl `0x40049409`), then
   `shutil.copy2`. Make it idempotent: skip when the dest exists and
   `os.path.samefile(dst, src)`; unlink+relink only when the source changed.
   Verify afterwards with `os.path.samefile` / matching inodes.
4. Rebuild the m3u8 when the batch settles; verify by counting the folder.

Resumable watch-loop that works: every ~30 s, re-check lane statuses for your
job ids, link each `completed` track whose library match now exists (retrying
`NOMATCH` ticks), and rebuild the m3u8 once nothing is pending. Every step is
exists-checked, so reruns are safe. Run it as a tracked background process
(not a detached nohup + echo, which exits immediately and never notifies).

## Naming pitfalls

- Strip any existing leading `NN - ` from a library filename before adding a
  playlist-order prefix — a compilation import can already carry `01 - ` per
  file, and prefixing it again yields `01 - 01 - Title.opus`.
- Keep m3u8 track order = download order when known; a bag import loses
  per-track order and alphabetical fallback looks wrong to the user.

## Batch build: playlists from a researched track list

For "build a playlist for each <dimension>" jobs (genre × year chart lists,
top-N lists, media-soundtrack batches):

1. Research each list to JSONL with `rank`, `artist`, `title`, `sources`,
   `evidence_urls` — one file per playlist. Parallel research subagents work
   well (standing user preference); one list per subagent beats one category
   per subagent when lists run 100–200 tracks.
2. Presence-check ALL tracks against the library ONCE (walk
   `/your-media-path/library/music-library`, index both direction-variant sets — see
   `single-track-batches.md` §1 for the variant rules that close most
   false-missing gaps). Measure present/missing per list and report BEFORE
   dispatching — that is the volume estimate and the CATALOG-FIRST gate.
3. Dispatch the missing set, deduped ACROSS playlists (a song shared by two
   lists downloads once; each playlist links its own copy). Keep a resumable
   log keyed by normalized `artist|title` holding the chosen row + job_id;
   re-runs skip already-dispatched keys.
4. Run a monitor loop instead of babysitting: rebuild the index → re-match
   unresolved tracks → link what landed → rebuild each m3u8 → snapshot
   counts. Exit on complete or stalled (counts unchanged across cycles AND
   queues empty); notify on exit (the user's >1h-job reporting rule). Every
   step must be idempotent so the loop and any single step can be re-run at
   any time.
5. Ranked lists >99 tracks: prefix files with 3 digits (`001 - …`) so
   lexicographic sort still matches rank order. Keep unresolved tracks
   visible in the m3u8 as `# MISSING: <rank>. <Artist> - <Title>` comment
   lines (players skip comments; gaps never silently disappear — the ruling
   "never silently prune" extends to never silently omit).
6. Audit before declaring done: spot-check newly linked paths against the
   expected song — title-only fallbacks are where wrong picks hide (a
   same-title track by another artist gets linked otherwise).

## Curation research (user preference)

- Propose additions from WEB research (best-of lists, genre playlists, reddit
  threads, DJ setlists) — NOT a blanket catalog keyword search; keyword dumps
  miss the canon the user actually means.
- Honor the playlist's defining constraint strictly and verify every pick
  against it (e.g. "the title must contain <keyword>" — that IS the concept of
  the playlist).
- Present picks grouped by sub-genre with a one-line why; then grab the
  approved set.
- The user tracks curated playlists as a standing interest — check for an
existing `/playlists/<Name>/` folder before creating one.
- **A ranked pick must be the version the user can actually hear.** A
  streaming-metrics source (Music Metrics Vault / the Spotify artist page)
  names the studio album; the LANE may carry only an alternate pressing.
  Measured 2026-10-17: Thumpasaurus' "Gas Cheaper Here" (2021 studio) was
  absent from the Tidal lane, which held only "Gas Cheaper Here (Refueled)"
  (live) — so 3 of the top-5 entries resolved to live takes. Check what
  actually landed (beets DB or the artist dir) BEFORE linking, substitute
  knowingly (studio preferred; a live take is acceptable when no studio
  pressing exists anywhere), and say which version each pick is. Never
  present a live/alternate take as the studio track. A missing studio
  pressing is a slskd/Bandcamp errand, not a dead end.
