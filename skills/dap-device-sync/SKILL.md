---
name: dap-device-sync
description: "Use when syncing music/playlists to a Rockbox player."
version: 1.0.1
author: Gravis Wellz
tags: [rockbox, dap, fat32, playlists, sync]
license: MIT
metadata:
  hermes:
    tags: [rockbox, dap, fat32, playlists, sync]
---

# DAP (Rockbox) device sync

## When to Use

Use when copying albums, artists, or playlists to a Rockbox (or other FAT32-only)
portable player: planning what fits, writing playlists the player can resolve,
re-syncing without re-copying, or pruning what is no longer wanted.

Getting a curated music set and its playlists onto a portable player whose only
filesystem is FAT32. The player's storage is the constraint: no hardlinks, no
symlinks, 4 GiB per file, case-insensitive names, and 32 KiB cluster slack.

## The one rule that decides everything

**On vfat a track stored per playlist costs a full copy per playlist.** Host-side
export trees built from reflinks/hardlinks (`/your-media-path/library/playlists/<name>/`,
`/your-media-path/exports/<artist>/`) are free at home and pure waste on the card. Never
mirror those trees to the device.

Device model instead — one audio tree, playlists as pointers:

```
/Music/<Artist>/<Album>/NN - Title.opus   each track exactly once
/Playlists/<name>.m3u8                    entries point into /Music/...
.rockbox/                                 untouched
.dapsync/manifest.json                    host-owned sync state
```

Measured on this library: 544 playlist entries resolved to 480 unique tracks —
2.49 GiB duplicated vs 2.23 GiB one-copy (10.6%), and the gap grows with every
overlapping playlist.

## Procedure

1. **Inventory the card before writing.** `lsblk -o NAME,SIZE,FSTYPE,LABEL` and
   `findmnt`. A card over 32 GB ships exFAT and must be reformatted FAT32;
   confirm cluster size — it drives the size estimate.
2. **Resolve** each selected playlist to canonical library paths (beets DB or the
   library tree), not to its per-playlist export directory. Keep source order.
3. **Dedupe by canonical library path** across all playlists *and* any
   artist-mode selection already on the card. Rockbox plays the same track twice
   if a file lists it twice — dedupe entries within a playlist too.
4. **Plan, print, then apply.** Report adds / already-present / orphans, bytes
   rounded up to the cluster size, and free space. Refuse to start without a
   headroom margin (512 MiB minimum) — a card that fills mid-run leaves a
   half-written library.
5. **Copy atomically.** Write `<dest>.part`, fsync, rename, set mtime from the
   source, verify the size. An interrupted plain copy leaves a truncated file
   that later size comparisons can accept.
6. **Write playlists last**, temp + rename, UTF-8, LF endings.
7. **Prune only on request** (`--prune`): delete device audio that no selected
   playlist references, never anything under `.rockbox/`.
8. **Verify on the device**, not on the host: re-mount, load a playlist from
   `/Playlists`, confirm first and last entry play. Rockbox resolves paths at
   load time, so a copy that looks right on the host can still fail on device.

## Playlist file rules

- Prefer **player-root absolute** entries (`/Music/Artist/Album/01 - X.opus`).
  Relative entries resolve against the playlist file's own directory, so
  `../Music/...` works from `/Playlists/` but breaks if the file is moved.
- Always `.m3u8`. `.m3u` is decoded as ISO-8859-1 unless a BOM is present.
- `#EXTM3U` + `#EXTINF:-1,Artist - Title` for display; other `#` lines are
  skipped by the parser.
- Backslashes become `/` and trailing spaces/tabs are stripped, so Windows-dumped
  lists are tolerated — do not rely on it.

## FAT32 naming

- Replace `\ / : * ? " < > |` (a `/` in a title becomes `-`).
- No trailing dot or space; avoid reserved stems (`CON PRN AUX NUL COM1..9 LPT1..9`).
- Case-insensitive collisions: two albums differing only by case collide —
  suffix ` [2]`.
- Keep total paths under ~200 chars; Rockbox truncates long paths silently.
- UTF-8 names are fine; transliteration is not required.

## When it does not fit

Cheapest lever first: dedupe (always on) → drop per-playlist `cover.jpg` (one
cover per album) → curate by per-playlist byte cost → device-only re-encode
(`ffmpeg -c:a libopus -b:a 96k`, ~40% smaller) cached by source path+size so
re-syncs are free. Never shrink the library copy to make the card fit.

## Pitfalls

- Do not assume hardlinks/reflinks exist on the card, and do not "optimise" by
  linking. The card is a copy target, full stop.
- FAT32 slack is ~0.3-0.5% for 5 MB tracks — negligible. Duplication, not
  cluster size, is where the bytes go; optimise the layout, not the block size.
- A playlist referencing an absolute path that was renamed keeps pointing at the
  old file until it is gone; rewrite playlists whenever the device tree changes,
  in the same run.
- Tag-based browsing needs its own tagcache rebuild; a correct file layout alone
  does not populate the Database menu.

Depth and primary-source citations (Rockbox `format_track_path()`, catalogue
defaults, encoding rules) live in `references/rockbox-playlist-semantics.md`.
