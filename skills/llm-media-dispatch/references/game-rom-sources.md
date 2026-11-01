# Game ROM Sources — Detailed Comparison

## Primary Sources

| Source | Type | Console Coverage | API | Hash Verification | Notes |
|--------|------|------------------|-----|-------------------|-------|
| **Minerva Archive** | Torrent | All (MAME, consoles, handhelds) | No (HTML scrape) | Via DAT cross-ref | Torrent per browse URL; aria2c native |
| **Internet Archive** | HTTP + Torrent | All (No-Intro, Redump, MAME sets) | Yes (search, metadata, torrent) | Built-in | Rate limited; locked items need account |
| **r-roms Megathread** | Curated links | Nintendo, Sony, Sega, Arcade, Handhelds | No (static HTML) | Labeled No-Intro/Redump | Scrape HTML → extract IA/Minerva URLs |
| **No-Intro DATs + IA** | DAT + Archive | Cartridge-based (NES, SNES, GB, GBA, N64, etc.) | DAT from no-intro.org | CRC32/MD5/SHA1 | Primary for cartridge systems |
| **Redump DATs + IA** | DAT + Archive | Disc-based (PS1, Saturn, Dreamcast, PS2, GC, Wii) | DAT from redump.org | SHA1/MD5 | Primary for optical media |

## Automation Patterns

### No-Intro DAT → Internet Archive Pipeline
```python
# 1. Download DAT
curl -o "{console}.dat" "https://datomatic.no-intro.org/index.php?page=download&system={console}"

# 2. Parse for target game (using DATROMTool or custom)
# Get: name, CRC32, MD5, SHA1, region

# 3. Search IA
search_query = f'"No-Intro {console}" "{game_title}"'
# OR by hash: f'md5:{md5_hash}'

# 4. Get item metadata
# GET https://archive.org/metadata/{identifier}

# 5. Download
# Direct: https://archive.org/download/{identifier}/{filename}
# Torrent: https://archive.org/download/{identifier}/{identifier}.torrent
# Use aria2c for both
```

### Minerva Archive (Torrent-Based)
```bash
# Browse URL pattern
https://minerva-archive.org/browse/{console}/{game-slug}
# Extract .torrent link from page
# Download with aria2c
aria2c "https://cdn.minerva-archive.org/torrents/{console}/{game}.torrent"
```

### Direct IA Item Download
```python
# Search
query = f'"No-Intro {console}" "{game_title}"'
# Get item list
# Pick item → get file list from metadata
# Filter by region/format
# Download via direct link or torrent
```

## Tools (Headless-Compatible)

| Tool | Language | Purpose | Headless |
|------|----------|---------|----------|
| `silverlays/NoIntro-Roms-Downloader` | Python/PyQt6 | Download datted ROMs from IA | Yes (can run headless) |
| `andrebrait/DATROMTool` | Python | Cross-platform DAT parser | Yes |
| `andrebrait/1g1r-romset-generator` | Python | 1 Game 1 ROM filtering | Yes |
| `alucryd/oxyromon` | Rust | Download DATs, organize ROMs | Yes |

## Source Selection by Console Type

| Console Type | Primary Source | Backup Source |
|--------------|----------------|---------------|
| Cartridge (NES, SNES, GB, GBA, N64) | No-Intro DAT → IA | Minerva |
| Disc (PS1, Saturn, Dreamcast, PS2, GC, Wii) | Redump DAT → IA | Minerva |
| Arcade (MAME, FBNeo) | MAME sets on IA | Minerva |
| Handheld (GBC, GBA, DS, PSP) | No-Intro DAT → IA | Minerva |

## Rate Limits & Gotchas

- **Internet Archive**: ~100 req/min for search; locked items need account
- **Minerva**: No official API; scrape with delays
- **No-Intro DATs**: Download from datomatic.no-intro.org (may require login for latest)
- **Redump DATs**: Download from redump.org (may require login)
- **aria2c**: Use for both HTTP and torrent; `--seed-time=0` for hit-and-run
