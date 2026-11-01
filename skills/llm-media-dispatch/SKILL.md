---
name: llm-media-dispatch
description: "Use for LLM media acquisition: NLU → intent → lane dispatch."
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [llm, nlu, media, dispatch, nemotron, radarr, ai]
    related: [media-downloader-fleet, media-grabber, anti-bot-scraping, scraping-to-api, blocked-page-recovery]
---

# LLM Media Dispatch

Build a natural-language media acquisition layer: parse user requests with an LLM, map to structured intents, dispatch to source-specific lanes (music, games, movies), monitor, report.

## When to Use

- Building an AI-driven Radarr/Sonarr equivalent that accepts natural language ("get me all versions of Street Fighter Alpha 2") and dispatches to source lanes
- Adding NLU to an existing media fleet (the downloader fleet, *arr stack, custom)
- Need structured intent parsing (media_type, title, consoles, regions, format, priority) from free text
- Evaluating LLM models for JSON-structured output reliability
- Designing lane registry + execution engine for multi-media-type acquisition

## 0. Rule: drive the lane that exists, never rebuild it (user rule, 2026-10-14)

This skill describes the *design* of an NLU acquisition layer. The layer is
already built and live: YARR on your arr stack host (`https://yarr.your-domain.example`, lanes games /
soulseek / web / seerr / library / releases / music-downloader / roms / edge) plus
the downloader fleet for music. For an actual request ("download TimeSplitters for PS2",
"grab artist X's discography") the work is `POST /api/find` → pick →
`POST /api/grab` against YARR, or the lane's own tool for music — see the
`yarr-ops` and `music-grab` skills.

Never hand-roll a downloader, scraper, or per-item enqueue loop to satisfy one
request, and never treat a lane's bug as license to replace the lane: apply the
documented workaround or fix the lane. Writing a bespoke pipeline where a lane
exists is the failure mode this rule exists to stop.

## 1. NLU Model Selection — critical gate

Only `pool/nemotron-3-super` reliably returns clean JSON in `response_format: {type: json_object}` mode.

| Model | JSON Output | Completeness | Verdict |
|-------|-------------|--------------|---------|
| `pool/nemotron-3-super` | ✅ Clean | ✅ All consoles/regions | **Production** |
| `openrouter/nemotron-3-ultra-550b-a55b:free` | ✅ Clean | ❌ Only PlayStation | Unusable |
| `openrouter/nemotron-3.5-lightning:free` | ❌ Thinking dump | ❌ Incomplete | Unusable |
| `openrouter/nemotron-3-super-120b-a12b:free` | ❌ None (404) | — | Unavailable |
| `openrouter/glm-5.2:free` | ❌ 404 | — | Unavailable |
| `oc/nemotron-*` | ❌ OpenCode-only | — | Unusable |

**Rule:** Use `pool/nemotron-3-super` via OmniRoute (`http://IPVPLACEHOLDER:20128/v1`). Always set `response_format: {"type": "json_object"}` and a system prompt that forbids commentary. Lightning/Ultra models dump raw thinking even in JSON mode — they are not reliable for structured output.

## 2. Intent Schema

```python
@dataclass
class MediaIntent:
    media_type: str          # "game" | "music" | "movie" | "tv" | "book" | "auto"
    title: str
    consoles: list[str] = field(default_factory=lambda: ["all"])
    regions: list[str] = field(default_factory=lambda: ["all"])
    format: str = "No-Intro" # "No-Intro" | "Redump" | "TOSEC" | "auto"
    priority: str = "best"   # "fast" | "best" | "complete"
    original_text: str = ""
```

System prompt for NLU:
```
Parse the user request into JSON. Output ONLY valid JSON with keys:
media_type, title, consoles, regions, format, priority.
No markdown, no commentary, no thinking. Just the JSON object.
```

## 3. Lane Registry Pattern

```python
@dataclass
class LaneCapability:
    name: str
    media_types: list[str]          # ["music", "game", "movie", "tv"]
    consoles: list[str] = field(default_factory=lambda: ["all"])
    formats: list[str] = field(default_factory=lambda: ["No-Intro"])
    healthy: bool = True
    dispatch_endpoint: str = ""     # internal lane URL for /download
    search_endpoint: str = ""       # internal lane URL for /search/json

LANE_REGISTRY: dict[str, LaneCapability] = {
    "music-downloader": LaneCapability(media_types=["music"], ...),
    "slskd": LaneCapability(media_types=["music"], ...),
    # Game lanes (to be implemented):
    # "arcade-cps2": LaneCapability(media_types=["game"], consoles=["arcade"], ...),
    # "snes": LaneCapability(...),
}

MEDIA_TYPE_LANES = {
    "music": ["music-downloader", "slskd"],
    "game": [],   # populate when game lanes exist
    "movie": [],
}
```

**Rule:** Filter lanes by `healthy=True` and `media_type` match before dispatch. Always dry-run first.

## 4. Game ROM Sources & Targeted Download Strategies

### 4.1 No-Intro DAT → Internet Archive Pipeline (primary)

```
1. Download No-Intro DAT for console (from no-intro.org or GitHub mirrors)
2. Parse DAT → get CRC32/MD5/SHA1 for target game
3. Search IA: "No-Intro {console} {game title}" OR by hash
4. Get IA item → extract direct download URL or .torrent
5. Download via aria2c (supports HTTP + torrent)
6. Verify hash against DAT
```

**Tools to leverage (headless):**
- `silverlays/NoIntro-Roms-Downloader` (PyQt6, can run headless)
- `andrebrait/DATROMTool` (cross-platform DAT parser)
- `andrebrait/1g1r-romset-generator` (1 Game 1 ROM filtering)
- `alucryd/oxyromon` (Rust, downloads DATs, organizes)

### 4.2 Minerva Archive (torrent-based)

```
- Minerva provides .torrent per browse URL
- Use aria2c for torrent downloads
- Browse URL: https://minerva-archive.org/browse/{console}/{game}
- Torrent URL: extract from page or use API if available
```

### 4.3 Direct Internet Archive Item Download

```
- IA search: "No-Intro {console} {game title}"
- Get item metadata → file list
- Pick file matching region/format
- Download via IA direct link (account for locked items) or .torrent
```

### 4.4 Redump for Disc-Based (PS1, Saturn, Dreamcast, etc.)

```
- Redump DATs → IA search "Redump {console} {game}"
- Disc images: .cue/.bin, .iso, .chd
- Larger files → prefer torrent (IA provides .torrent per item)
```

### 4.5 r-roms Megathread (curated links)

```
- Static HTML, console-organized, No-Intro/Redump labeled
- Scrape HTML → extract IA/Minerva URLs
- No official API
```

## 5. Movie/TV Sources & Targeted Download Strategies

### 5.1 Public Tracker Search → Torrent

```
- Prowlarr + public trackers (1337x, RARBG mirrors, RuTracker, Nyaa)
- Search: "{movie} {year} {quality} {codec}"
- Quality tiers: 1080p x265, 4K HDR, Remux
- Filter by seeders, size, trusted uploader
```

### 5.2 DDL via CS.RIN.RU / DDL Sites

```
- CS.RIN.RU has movie sections
- Links often on 1fichier, uploadgig, rapidgator
- Use debrid service (Real-Debrid API) to get direct links
```

### 5.3 Debrid + Stremio/Torrentio

```
- Torrentio scrapes public trackers → generates .torrent
- Real-Debrid caches torrent → gives direct HTTPS link
- API: Real-Debrid REST (add magnet, check cache, get download link)
```

## 6. Execution Engine Pattern

```python
def execute_intent(intent: MediaIntent, dry_run: bool = False):
    lanes = get_lanes_for_media_type(intent.media_type)
    if not lanes:
        return {"error": f"no healthy lanes for media type: {intent.media_type}"}
    
    if dry_run:
        return {"intent": intent, "selected_lanes": lanes, "dry_run": True}
    
    results = []
    for lane in lanes:
        result = dispatch_to_lane(lane, intent)
        results.append({"lane": lane, "result": result})
        if result.get("job_id"):
            break  # success
    return {"intent": intent, "results": results}
```

**Rule:** Always dry-run first. Dispatch to first healthy lane; stop on first success.

## 7. Current Endpoints (the downloader fleet /ai/)

| Endpoint | Purpose |
|----------|---------|
| `GET /ai/health` | Lanes + model info |
| `POST /ai/parse` | NL → intent |
| `POST /ai/enumerate` | Game title → ROM list (via LLM) |
| `POST /ai/execute` | Parse + dispatch (dry_run optional) |
| `GET /ai/lanes` | Registry status |

## 8. Pitfalls

- **Thinking dump models**: Lightning/Ultra dump raw reasoning even with `response_format: json_object`. Only `pool/nemotron-3-super` works.
- **JSON mode requires system prompt**: Must explicitly forbid commentary/thinking in system prompt.
- **Model returns single console per call**: `/ai/enumerate` returns one console per invocation; call multiple times or extend prompt.
- **No game lanes yet**: `/ai/execute` correctly returns "no healthy lanes for media_type: game" — implement game lanes before game acquisition works.
- **OmniRoute auth**: Use `HERMES_CUSTOM_IPVPLACEHOLDER_CREDENTIAL` env var for OmniRoute calls.
- **NLU timeout**: Set 30s timeout; nemotron-3-super typically responds in 2-5s.

## 9. References

- `references/game-rom-sources.md` — detailed source comparison, APIs, automation patterns
- `references/movie-sources.md` — tracker, DDL, debrid patterns
- `references/intent-schema.md` — full MediaIntent schema with examples
- `references/nlu-prompts.md` — system prompts for parsing, enumeration