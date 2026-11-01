# archive.org per-game sets — verified identifier map

Every item below holds ONE ARCHIVE PER GAME (not whole-set dumps) — the
property that makes single-game targeted downloads possible. Searching only
fetches the item's metadata JSON; item size is irrelevant to cost.

## Wired console → IA identifiers

| Console | Identifiers |
|---|---|
| Sega Saturn | `redump_sega_saturn_202204` + `noaen-redump-sega-saturn` (mirror; extra region coverage) |
| PlayStation (PS1) | `ef_Sony_PlayStation1_Redump_Collection_1..4of4` + `PS1_EU_Arquivista` (EU titles the main parts miss) |
| PlayStation 2 | `PS2-Redump-2024-Individual-Games-Part1..17` |
| PlayStation 3 | `PS3-Redump-2024-Individual-Games-Part1..34` |
| GameCube | `GameCube-Redump-2024-Individual-Games-Part1..2` |
| Wii | `Wii-Redump-2024-Individual-Games-Part1..6` |
| Nintendo 3DS | `3DS-Redump-2024-Individual-Games-Part1..2` |

Seen but not wired: `PS1_JP_Arquivista` (JP PS1), `sony_playstation2_<letter>`
(PS2 per-letter Redump), `Gamecube-Redump-2024-Myrient-Zipped` (whole-set
.ZIPs — wrong shape for single games).

## Verification recipe for a NEW collection

1. Search for candidates:
   `https://archive.org/advancedsearch.php?q=title%3A%22<group>%22&fl[]=identifier&fl[]=title&rows=50&output=json`
2. Confirm per-game shape: fetch `https://archive.org/metadata/<id>` and
   count `.zip/.7z/.rar` files. Hundreds-to-thousands of game-named archives
   = usable; a handful of multi-GB blobs = whole-set dump, skip.
3. Probe before calling it wired: dry-run resolve one known game → real
   download → serve check (HTTP 206 + magic bytes).

## Matching notes

- Set filenames use ` (Region)` suffixes and ` - ` separators
  ("Mortal Kombat - Special Forces (USA).zip") — the normalizer strips both,
  so plain user input ("Mortal Kombat Special Forces") matches directly.
- Some sets carry `00 Goodies/...` dirs (manuals/scans) whose names contain
  game titles; the title-cut + prefix ranking filters almost all, but a
  stray hit in results is usually one of these.
- Multi-region requests return up to one candidate per region; a plain
  request returns the single best candidate.
- Download URLs need percent-encoding of spaces/parens; the resolver emits
  quoted URLs and the cache UNQUOTES names for disk (see SKILL.md pitfalls).
