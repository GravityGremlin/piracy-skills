# Manual beets import (library-REPAIR only)

Normal grabs never need this — the organizer imports automatically. Use this
only for repair: splitting a release out of a compilation, re-importing a dir
beets skipped, or fixing a mis-tagged import.

## Running beet

```
docker exec organizer sh -c 'beet -c /app/.config/beets/config.yaml <cmd>'
```

- `config.yaml` = live album-batch config. Single-track hole-fill uses
  `config-provider-singleton.yaml`.
- `-i` is **incremental** (SKIP already-seen dirs); `-I` / `--noincremental`
  **forces** a re-import. A run that prints `No files imported ... Skipped 1
  paths.` is being skipped by incremental state — use `-I`. Reaching for `-i`
  does the opposite of what you want.
- `-A` = import as-is, trust existing tags. Use it after writing correct tags
  yourself with mutagen.
- `remove` prompts for confirmation and hangs a headless run — always pass
  `-f`.
- `move: yes` in the live config **renames in place** (does not copy), and the
  result dir name comes from the beets path template
  (`$albumartist/$album`), so it can differ from your source dir name.

## Back up first, then verify

- `docker exec organizer sh -c 'cp /app/.config/beets/library.db
  /app/.config/beets/library.db-before-<what>'`. The DB is one file and the
  organizer holds it open — do repairs when the queue is quiet.
- After: `beet ls -a albumartist:"<artist>"`, then diff DB dirs against disk
  dirs to catch orphans.

## The tag-matching trap

Beets re-matches against MusicBrainz **by tags**. Files still carrying another
release's embedded track numbers (e.g. box-set numbering `25`–`32`) re-match to
THAT release and re-create its dir — the import silently "succeeds" into the
wrong album.

Fix: rewrite tags BEFORE importing. Strip everything with an ffmpeg remux
(`-map_metadata -1`), then write canonical tags with mutagen (`OggOpus`:
`album`, `albumartist`, `artist`, `title`, `tracknumber`, `tracktotal`,
`date`, `musicbrainz_albumid`). Import with `-A` so your tags are trusted.

## Corruption probes (cheapest first)

- **mutagen is the fast test:** `OggOpus(path)` raises `unable to find final
  Ogg header` on a truncated/corrupt file. Same failure class as the bad-audio
  quarantine.
- **mutagen is also the reliable TAG reader for opus.** `ffprobe -show_entries
  format_tags` can return an empty object on opus files (seen on both
  freshly-remuxed and original Tidal-sourced files), which reads as "no tags"
  and sends you chasing a tag problem that is not there. Read tags with
  `OggOpus(path)` and index keys directly.
- **ffmpeg signals differ in severity.** `CRC mismatch!` alone is a container
  checksum quirk and the audio still decodes. `Error parsing the packet header`
  / `Error during demuxing: Invalid data found` / `non monotonically increasing
  dts` mean real corruption.
- **Do NOT remux a CRC-affected file with `-c:a copy` as a repair** — it can
  truncate the audio (a 3.4 MB file came out at 1.4 MB). The stream, not the
  container, is damaged; re-fetch from another lane instead.
- **Never judge completeness against a GUESSED expected duration.** Fetch the
  reference from MusicBrainz (`/ws/2/release/<mbid>?inc=recordings` → per-track
  `length` in ms) and compare. A guessed duration produced a false
  "truncated" verdict on a track that was in fact complete.

## Re-fetching a corrupt track from slskd

The lane's search API is the right probe (`/search/json?q=<artist> <release>`
with the lane's bearer token); it returns per-peer dirs with `dir_files`,
`dir_lossless`, `username`, and per-file `filename`/`size` — pick a lossless
16-bit peer. The exact enqueue call shape lives in
`references/slskd-dispatch.md`.
