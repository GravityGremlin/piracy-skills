# Rockbox playlist semantics (primary-source notes)

Source: Rockbox master (`apps/playlist.c`) and the official daily manual. Items
marked MEASURED were read verbatim from that source; INFERRED follows from it.

## Path resolution

`format_track_path()` (playlist.c:529-607) documents the whole rule and is the
function every consumer goes through:

1. **Unix absolute** paths (`/foo/bar`) are kept unaltered, resolved against the
   player root. MEASURED.
2. **Windows absolute** (`C:/foo/bar`) has the drive letter replaced by the
   current volume. MEASURED.
3. **Relative** paths are made absolute by prepending *the directory the
   playlist file lives in* (not the root, not the CWD). MEASURED.

Order of processing: keep only the first line, strip **trailing** tab/space
only, convert `\` to `/`, strip drive letters, append to the playlist directory,
`path_remove_dot_segments()`. Buffer-too-small returns -1 — long paths are
truncated or rejected, so keep paths short.

Consequences:

| Playlist at | Entry | Resolves to |
|---|---|---|
| `/Playlists/a.m3u8` | `Music/X/Y.opus` | `/Playlists/Music/X/Y.opus` — wrong |
| `/Playlists/a.m3u8` | `../Music/X/Y.opus` | `/Music/X/Y.opus` — right |
| `/Playlists/a.m3u8` | `/Music/X/Y.opus` | `/Music/X/Y.opus` — right, location-proof |

## Encoding

- `.m3u8` → decoded as UTF-8, no conversion.
- `.m3u` → ISO-8859-1 → UTF-8 conversion unless a BOM says otherwise.
- Extension changes **encoding only**; relative/absolute handling, `..`
  collapsing and `#` skipping are identical for both.

Use `.m3u8` for any non-ASCII library.

## Parser behaviour

- `#EXTINF` is lenient; unknown `#` lines are skipped.
- Blank lines are ignored.
- Entries are **not deduplicated** — the same file listed twice plays twice.
- Backslashes and Windows line endings are tolerated (`\r\n` truncated at the
  first terminator).

## Playlist Catalogue directory

Default is `/Playlists` at the player root (`PLAYLIST_CATALOG_DEFAULT_DIR =
HOME_DIR "Playlists"`, with `HOME_DIR = "/"` on hardware targets). MEASURED.
It is user-settable, and playlists load from any directory via the File Browser —
the catalogue is only a shortcut. `/Playlists` is the safe default; do not assume
`/.rockbox/playlists`.

## Cost model (how to estimate a sync)

Compute per candidate:

- `entries` and unique source inodes per playlist — the difference is what a
  per-playlist copy wastes.
- `union` across all selected playlists + artist selections; **one copy per
  unique track** is the realistic device cost.
- FAT32 cost per file = size rounded up to the cluster size; use the card's real
  cluster size (`stat -f` / `mkfs.fat -v`), typically 32 or 64 KiB.

On a 128 GB card with 160k-opus (~5 MB/track) that is roughly 24k tracks after
slack — a curated subset every time, so always print the plan before copying.

Verifying a FAT32 layout without hardware: create a loopback image
(`mkfs.fat -F 32`), mount it, sync, unmount and remount, then read the playlists
and `stat` the entries. This catches case-folding, long-path and slack mistakes
that a btrfs test directory never will.
