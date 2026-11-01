---
name: rom-collection
description: Build a complete ROM collection system using Minerva torrents, classic databases (TOSEC, NOINTRO, GOOD), and IGDB linking. No web UI — CLI/API driven. Covers torrent metadata, dat validation, dat-to-rom matching, and IGDB enrichment.
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [rom, collection, minerva, tosec, nointro, good, igdb, dat]
    related_skills: [console-homebrew-staging]

---

# ROM Collection System

Generic framework for a completionist ROM collection: Minerva torrents + TOSEC/NOINTRO/GOOD dats + IGDB metadata. CLI-first, no web UI.

## Data sources

| Source | Format | Purpose |
|--------|--------|---------|
| **Minerva** | .torrent (giant, ~1TB+) | PS2 CHD/ISO collection, verified dumps |
| **TOSEC** | .dat (XML) | Authoritative catalogs per system (checksums, names, variants) |
| **NO-INTRO** | .dat (XML) | Curated "best" dump per game, no bad dumps/overdumps |
| **GOOD** | .dat (older) | GoodTools era, mostly superseded by NO-INTRO |
| **Redump** | .dat (XML) | Optical media focus (PS1, PS2, DC, GC, Wii, etc.) |
| **IGDB** | REST API | Game metadata (covers, release dates, genres, platforms, companies) |

## Workflow

```
1. Download Minerva .torrent → extract file list (btlist.py)
2. Parse TOSEC/NO-INTRO/Redump dats → build checksum→game map
3. Match local files (CHD/ISO/ZSO) against dats by SHA1/MD5/CRC32
4. Classify: VERIFIED / NEEDS_REPLACE / MISSING / UNKNOWN
5. For MISSING: queue from Minerva torrent (selective download)
6. Enrich VERIFIED with IGDB metadata (cover, genre, release date, etc.)
7. Output: structured library index (JSON/SQLite) for frontends
```

## Dat parsing (XML → dict)

```python
import xml.etree.ElementTree as ET

def parse_dat(dat_path):
    """Return {checksum: {name, system, region, version, ...}}"""
    tree = ET.parse(dat_path)
    root = tree.getroot()
    out = {}
    for game in root.findall('.//game'):
        name = game.get('name')
        rom = game.find('rom')
        if rom is not None:
            crc = rom.get('crc')
            md5 = rom.get('md5')
            sha1 = rom.get('sha1')
            size = rom.get('size')
            for chk in (sha1, md5, crc):
                if chk:
                    out[chk.upper()] = {
                        'name': name,
                        'system': root.get('name', 'unknown'),
                        'crc': crc, 'md5': md5, 'sha1': sha1, 'size': size
                    }
    return out
```

## CHD hash extraction (for matching)

```bash
# CHD hashes embedded in header — extract without full conversion
chdman info -i game.chd | grep -E 'SHA1|MD5|CRC32'
# Or use python-chd library for programmatic access
```

## IGDB enrichment (requires Twitch OAuth client credentials)

```bash
# Get access token
curl -X POST "https://id.twitch.tv/oauth2/token" \
  -d client_id=$IGDB_CLIENT_ID \
  -d client_secret=$IGDB_CLIENT_SECRET \
  -d grant_type=client_credentials

# Search game
curl "https://api.igdb.com/v4/games" \
  -H "Client-ID: $IGDB_CLIENT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'search "Shadow of the Colossus"; fields name,cover,first_release_date,genres,platforms,summary;'
```

## Output schema (library index)

```json
{
  "games": [
    {
      "id": "sha1:ABC123...",
      "name": "Shadow of the Colossus",
      "system": "PS2",
      "region": "USA",
      "version": "1.01",
      "files": [
        {"format": "CHD", "path": "/library/PS2/Shadow of the Colossus (USA).chd", "sha1": "ABC123...", "size": 3221225472}
      ],
      "dat_matches": [
        {"source": "Redump", "dat_name": "Sony PlayStation 2", "status": "VERIFIED"},
        {"source": "NO-INTRO", "dat_name": "Sony PlayStation 2", "status": "VERIFIED"}
      ],
      "igdb": {
        "id": 12345,
        "cover_url": "https://images.igdb.com/...",
        "first_release_date": "2005-10-18",
        "genres": ["Action", "Adventure"],
        "platforms": ["PlayStation 2"],
        "summary": "..."
      }
    }
  ]
}
```

## Selective torrent download (Minerva)

```bash
# List torrent contents with piece mapping
python3 btlist.py minerva-ps2.torrent --indexed > manifest.json

# Download only needed pieces (requires libtorrent/rtorrent/qbittorrent with piece selection)
# Or use aria2c with --select-file= and --bt-prioritize-piece=
```

Engine choice is yours: aria2c is the canonical CLI here, and the same five
torrent operations are documented for a qBittorrent/Transmission engine in
`self-hosted-debrid/references/torrent-clients.md` (env-var contract included).

## Verification checklist

- [ ] Every local game has ≥1 dat match (TOSEC/NO-INTRO/Redump)
- [ ] Dat status: VERIFIED (checksum match) or NEEDS_REPLACE (wrong dump)
- [ ] IGDB enrichment rate ≥90% for VERIFIED games
- [ ] MISSING list actionable: Minerva has it → queue download; else → flag for sourcing
- [ ] Library index export loads in target frontend (RomM, custom TUI, etc.)