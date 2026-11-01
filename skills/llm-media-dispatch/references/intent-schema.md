# MediaIntent Schema — Complete Reference

## Dataclass Definition

```python
from dataclasses import dataclass, field
from typing import Literal

MediaType = Literal["game", "music", "movie", "tv", "book", "auto"]
Format = Literal["No-Intro", "Redump", "TOSEC", "auto"]
Priority = Literal["fast", "best", "complete"]

@dataclass
class MediaIntent:
    media_type: MediaType = "auto"
    title: str = ""
    consoles: list[str] = field(default_factory=lambda: ["all"])
    regions: list[str] = field(default_factory=lambda: ["all"])
    format: Format = "auto"
    priority: Priority = "best"
    original_text: str = ""

    def to_dict(self) -> dict:
        return {
            "media_type": self.media_type,
            "title": self.title,
            "consoles": self.consoles,
            "regions": self.regions,
            "format": self.format,
            "priority": self.priority,
            "original_text": self.original_text,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MediaIntent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
```

## Field Semantics

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `media_type` | enum | `"auto"` | Target media category. `"auto"` = infer from context |
| `title` | string | `""` | Canonical media title (game name, album, movie) |
| `consoles` | string[] | `["all"]` | Target platforms. `["all"]` = every platform it exists on |
| `regions` | string[] | `["all"]` | Target regions. `["all"]` = every region |
| `format` | enum | `"auto"` | DAT standard. `"auto"` = best available |
| `priority` | enum | `"best"` | `"fast"`=first hit, `"best"`=quality, `"complete"`=all variants |
| `original_text` | string | `""` | Raw user input for debugging/audit |

## Examples

### Game: All Versions
```json
{
  "media_type": "game",
  "title": "Street Fighter Alpha 2",
  "consoles": ["all"],
  "regions": ["all"],
  "format": "No-Intro",
  "priority": "complete",
  "original_text": "get me all versions of Street Fighter Alpha 2 for every console"
}
```

### Game: Specific Console + Region
```json
{
  "media_type": "game",
  "title": "Chrono Trigger",
  "consoles": ["SNES", "PS1", "DS"],
  "regions": ["USA", "Japan"],
  "format": "No-Intro",
  "priority": "best",
  "original_text": "chrono trigger usa and japan on snes ps1 ds"
}
```

### Music: Album
```json
{
  "media_type": "music",
  "title": "Skinny Puppy - Remission",
  "consoles": ["all"],
  "regions": ["all"],
  "format": "FLAC",
  "priority": "best",
  "original_text": "skinny puppy remission flac"
}
```

### Music: Discography
```json
{
  "media_type": "music",
  "title": "Ministry",
  "consoles": ["all"],
  "regions": ["all"],
  "format": "FLAC",
  "priority": "complete",
  "original_text": "grab ministry discography flac"
}
```

### Movie: Quality-Specific
```json
{
  "media_type": "movie",
  "title": "The Matrix",
  "consoles": ["all"],
  "regions": ["all"],
  "format": "Remux",
  "priority": "best",
  "original_text": "the matrix 1999 remux 4k hdr"
}
```

### TV: Series
```json
{
  "media_type": "tv",
  "title": "The Wire",
  "consoles": ["all"],
  "regions": ["all"],
  "format": "1080p",
  "priority": "complete",
  "original_text": "the wire all seasons 1080p"
}
```

## NLU Output Contract

The LLM must output ONLY this JSON structure. No extra fields, no markdown, no commentary.

```json
{
  "media_type": "game|music|movie|tv|book|auto",
  "title": "string",
  "consoles": ["string"],
  "regions": ["string"],
  "format": "No-Intro|Redump|TOSEC|auto",
  "priority": "fast|best|complete",
  "original_text": "string"
}
```

## Validation Rules

1. `title` must not be empty
2. `consoles` = `["all"]` or list of known console names
3. `regions` = `["all"]` or list of region codes (USA, Japan, Europe, World, etc.)
4. `format` must be valid enum value
5. `priority` must be valid enum value
6. `media_type` = `"auto"` triggers inference from `title` + `consoles`

## Console Name Normalization

| Input Variants | Normalized |
|----------------|------------|
| `snes`, `super nintendo`, `super famicom` | `SNES` |
| `ps1`, `playstation`, `playstation 1` | `PS1` |
| `ps2`, `playstation 2` | `PS2` |
| `ps3`, `playstation 3` | `PS3` |
| `ps4`, `playstation 4` | `PS4` |
| `ps5`, `playstation 5` | `PS5` |
| `xbox`, `original xbox` | `Xbox` |
| `xbox360`, `xbox 360` | `Xbox360` |
| `xboxone`, `xbox one` | `XboxOne` |
| `xboxseries`, `series x`, `series s` | `XboxSeries` |
| `n64`, `nintendo 64` | `N64` |
| `gamecube`, `gc`, `gcn` | `GameCube` |
| `wii` | `Wii` |
| `wiiu`, `wii u` | `WiiU` |
| `switch` | `Switch` |
| `gb`, `gameboy` | `GameBoy` |
| `gbc`, `gameboy color` | `GBC` |
| `gba`, `gameboy advance` | `GBA` |
| `ds`, `nintendo ds` | `DS` |
| `3ds`, `nintendo 3ds` | `3DS` |
| `psp` | `PSP` |
| `vita`, `ps vita` | `Vita` |
| `saturn`, `sega saturn` | `Saturn` |
| `dreamcast`, `dc` | `Dreamcast` |
| `genesis`, `megadrive`, `mega drive` | `Genesis` |
| `arcade`, `mame`, `fbneo`, `cps2` | `Arcade` |
| `gbc`, `gameboy color` | `GBC` |
| `nds`, `nintendo ds` | `DS` |

## Region Code Normalization

| Input | Normalized |
|-------|------------|
| `us`, `usa`, `america`, `na` | `USA` |
| `jp`, `jpn`, `japan` | `Japan` |
| `eu`, `europe`, `pal`, `eur` | `Europe` |
| `world`, `intl`, `international` | `World` |
| `asia` | `Asia` |
| `korea`, `kr` | `Korea` |
| `aus`, `australia` | `Australia` |
| `bra`, `brazil` | `Brazil` |

## Format Inference by Media Type

| Media Type | Default Format | Fallback |
|------------|----------------|----------|
| `game` (cartridge) | `No-Intro` | `TOSEC` |
| `game` (disc) | `Redump` | `TOSEC` |
| `game` (arcade) | `MAME` | `FBNeo` |
| `music` | `FLAC` | `MP3` |
| `movie` | `Remux` | `1080p` |
| `tv` | `1080p` | `720p` |
| `book` | `EPUB` | `PDF` |

## Priority Behavior

| Priority | Behavior |
|----------|----------|
| `fast` | Return first successful hit; stop after first lane succeeds |
| `best` | Evaluate all healthy lanes; return highest quality result |
| `complete` | Dispatch to all healthy lanes; return all variants/regions |
