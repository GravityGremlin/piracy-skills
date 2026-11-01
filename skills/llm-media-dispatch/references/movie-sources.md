# Movie/TV Sources — Trackers, DDL, Debrid

## Primary Sources

| Source | Type | Content | API | Auth | Notes |
|--------|------|---------|-----|------|-------|
| **Prowlarr + Public Trackers** | Torrent Indexer | Movies, TV, Anime | Yes (Prowlarr API) | Key-based auth | 1337x, RARBG mirrors, RuTracker, Nyaa, ThePirateBay |
| **Real-Debrid** | Debrid/Cache | Torrent + DDL cache | Yes (REST) | API Token | Unrestricted HTTPS links; caches torrents |
| **AllDebrid / Debrid-Link** | Debrid | Similar to Real-Debrid | Yes | API Token | Alternative debrid services |
| **CS.RIN.RU** | DDL Forum | Games + Movies | No (scrape) | Login | Steam underground; links on 1fichier, rapidgator, uploadgig |
| **Stremio + Torrentio** | P2P Streaming | Movies, TV | Addon protocol | None | Real-time; can extract cached torrents |
| **Usenet (NZB)** | NZB Indexer | Movies, TV | Yes (NZBHydra2, etc.) | Key-based auth | High retention; automated with Sonarr/Radarr |
| **Internet Archive** | HTTP + Torrent | Public domain, some modern | Yes | Account for locked | Feature films, TV collections |

## Automation Patterns

### Public Tracker Search → Torrent
```python
# 1. Prowlarr search
GET /api/v1/search?query={movie}+{year}+{quality}+{codec}
# Filter: seeders > 10, size within quality tier, trusted uploader

# 2. Quality tiers
TIERS = [
    {"name": "1080p", "codec": "x265", "size_range": "2-8GB"},
    {"name": "4K", "codec": "x265", "hdr": True, "size_range": "15-50GB"},
    {"name": "Remux", "codec": "original", "size_range": "20-80GB"},
]

# 3. Send to qBittorrent/Transmission
POST /api/v2/torrents/add
  magnets=[magnet_uri]
  category=movies
  save_path=/media/movies
```

### Real-Debrid Integration (Torrent Cache + DDL)
```python
# 1. Add magnet/torrent
POST https://api.real-debrid.com/rest/1.0/torrents/addMagnet
  magnet={magnet_uri}

# 2. Check cache status
GET https://api.real-debrid.com/rest/1.0/torrents/info/{id}
# If cached: files available immediately

# 3. Unrestrict link
POST https://api.real-debrid.com/rest/1.0/unrestrict/link
  link={file_link}
# Returns direct HTTPS download URL

# 4. For DDL links (1fichier, rapidgator, etc.)
POST https://api.real-debrid.com/rest/1.0/unrestrict/link
  link={ddl_url}
# Returns direct HTTPS download URL
```

### CS.RIN.RU / DDL Sites
```python
# 1. Search CS.RIN.RU (requires login)
# Scrape forum for "{movie} {year}"
# Extract hoster links: 1fichier, rapidgator, uploadgig, nitroflare

# 2. Use Real-Debrid to unrestrict
# Most hosters supported
```

### Stremio + Torrentio (P2P Streaming)
```python
# Torrentio addon scrapes public trackers
# Generates .torrent or magnet for Stremio
# Can extract magnet for download via debrid/qBittorrent
# API: https://torrentio.strem.fun/manifest.json
```

## Quality Profiles (Radarr-style)

| Profile | Resolution | Codec | HDR | Size Range | Use Case |
|---------|------------|-------|-----|------------|----------|
| **SD** | 480p | x264 | No | 700MB-1.5GB | Mobile/bandwidth limited |
| **HD-720p** | 720p | x264/x265 | No | 1.5-3GB | TV shows |
| **HD-1080p** | 1080p | x265 | No | 2-8GB | Default movies |
| **4K** | 2160p | x265 | Yes | 15-50GB | 4K HDR |
| **Remux** | Original | Original | Yes | 20-80GB | Archival |

## Radarr/Sonarr Integration

```yaml
# Radarr quality profile
quality_profile:
  name: "AI Radarr Default"
  cutoff: 1080p
  items:
    - quality: HD-1080p
      allowed: true
    - quality: 4K
      allowed: true
    - quality: Remux
      allowed: false
```

## Rate Limits & Gotchas

- **Prowlarr**: Rate limit per indexer; stagger searches
- **Real-Debrid**: 1000 requests/day on free; unlimited on premium
- **Public trackers**: No API; scrape with delays, respect robots.txt
- **Debrid services**: Premium required for unrestricted speeds
- **Usenet**: Requires provider (NewsDemon, Eweka) + indexer
