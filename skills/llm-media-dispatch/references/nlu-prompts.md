# NLU Prompts — System Prompts for Parsing & Enumeration

## 1. Intent Parsing (NL → MediaIntent)

```
Parse the user request into JSON. Output ONLY valid JSON with keys:
media_type, title, consoles, regions, format, priority.

media_type: "game" | "music" | "movie" | "tv" | "book" | "auto"
title: string (the media title)
consoles: array of strings, or ["all"] for every console
regions: array of strings, or ["all"] for every region
format: "No-Intro" | "Redump" | "TOSEC" | "MAME" | "FBNeo" | "FLAC" | "MP3" | "Remux" | "1080p" | "720p" | "EPUB" | "PDF" | "auto"
priority: "fast" | "best" | "complete"

No markdown, no commentary, no thinking. Just the JSON object.
```

### Example Input/Output

**Input:** `"get me all versions of Street Fighter Alpha 2 for every console"`

**Output:**
```json
{
  "media_type": "game",
  "title": "Street Fighter Alpha 2",
  "consoles": ["all"],
  "regions": ["all"],
  "format": "No-Intro",
  "priority": "complete"
}
```

**Input:** `"chrono trigger usa and japan on snes ps1 ds"`

**Output:**
```json
{
  "media_type": "game",
  "title": "Chrono Trigger",
  "consoles": ["SNES", "PS1", "DS"],
  "regions": ["USA", "Japan"],
  "format": "No-Intro",
  "priority": "best"
}
```

**Input:** `"skinny puppy remission flac"`

**Output:**
```json
{
  "media_type": "music",
  "title": "Skinny Puppy - Remission",
  "consoles": ["all"],
  "regions": ["all"],
  "format": "FLAC",
  "priority": "best"
}
```

## 2. ROM Enumeration (Game Title → ROM List)

```
List every home console {game_title} was officially released on.
For each console, list every region and the exact No-Intro ROM filename.
Output as a JSON array of objects with keys: console, regions (object mapping region name to filename).
No markdown, no commentary, no thinking. Just the JSON object.
```

### Example Output

```json
[
  {
    "console": "Arcade CPS2",
    "regions": {
      "World": "Street Fighter Alpha 2 (World 960314).zip",
      "USA": "Street Fighter Alpha 2 (USA 960314).zip",
      "Japan": "Street Fighter Alpha 2 (Japan 960314).zip"
    }
  },
  {
    "console": "Super Nintendo/SNES",
    "regions": {
      "World": "Street Fighter Alpha 2 (World).smc",
      "Japan": "Street Fighter Alpha 2 (Japan).smc"
    }
  },
  {
    "console": "Sega Saturn",
    "regions": {
      "Japan": "Street Fighter Zero 2 (Japan).cue",
      "USA": "Street Fighter Alpha 2 (USA).cue",
      "Europe": "Street Fighter Alpha 2 (Europe).cue"
    }
  },
  {
    "console": "PlayStation",
    "regions": {
      "USA": "Street Fighter Alpha 2 (USA).cue",
      "Europe": "Street Fighter Alpha 2 (Europe).cue",
      "Japan": "Street Fighter Zero 2 (Japan).cue"
    }
  },
  {
    "console": "Game Boy Color",
    "regions": {
      "World": "Street Fighter Alpha 2 (World).gbc",
      "Japan": "Street Fighter Zero 2 (Japan).gbc"
    }
  }
]
```

## 3. Movie/TV Enumeration (Title → Quality Options)

```
List available quality tiers for {movie_title} ({year}).
For each tier, specify: resolution, codec, HDR, typical size range, and example release name pattern.
Output as a JSON array of objects with keys: tier, resolution, codec, hdr, size_range, example_pattern.
No markdown, no commentary, no thinking. Just the JSON object.
```

### Example Output

```json
[
  {
    "tier": "1080p",
    "resolution": "1920x1080",
    "codec": "x265",
    "hdr": false,
    "size_range": "2-8GB",
    "example_pattern": "The.Matrix.1999.1080p.BluRay.x265.10bit.AAC5.1-[GROUP]"
  },
  {
    "tier": "4K",
    "resolution": "3840x2160",
    "codec": "x265",
    "hdr": true,
    "size_range": "15-50GB",
    "example_pattern": "The.Matrix.1999.2160p.BluRay.REMUX.HEVC.DTS-HD.MA.5.1-[GROUP]"
  },
  {
    "tier": "Remux",
    "resolution": "3840x2160",
    "codec": "original",
    "hdr": true,
    "size_range": "20-80GB",
    "example_pattern": "The.Matrix.1999.2160p.BluRay.REMUX.HEVC.DTS-HD.MA.5.1-[GROUP]"
  }
]
```

## 4. Model Configuration

```python
NLU_CONFIG = {
    "model": "nemotron-3-super",
    "endpoint": os.environ.get("NLU_BASE_URL", "http://<gateway-host>:<port>/v1"),  # your OpenAI-compatible NLU gateway
    "credential_env": "NLU_API_KEY",
    "response_format": {"type": "json_object"},
    "timeout": 30,
    "max_tokens": {
        "parse": 500,
        "enumerate_game": 3000,
        "enumerate_movie": 2000
    }
}
```

## 5. Critical Rules

1. **Always use `response_format: {"type": "json_object"}`** — required for structured output
2. **System prompt must forbid thinking/commentary** — "No markdown, no commentary, no thinking. Just the JSON object."
3. **Only `nemotron-3-super` works reliably** — smaller/other models dump thinking even in JSON mode
4. **Set timeout 30s** — nemotron-3-super typically responds in 2-5s
5. **Model returns single console per enumerate call** — call multiple times or accept partial results
6. **Temperature: 0** — deterministic output for structured data

## 6. Error Handling

```python
try:
    resp = requests.post(...)
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
    log.exception("NLU failed")
    return MediaIntent(
        media_type="auto",
        title=raw_text,
        consoles=["all"],
        regions=["all"],
        format="auto",
        priority="best",
        original_text=original_text
    )
```