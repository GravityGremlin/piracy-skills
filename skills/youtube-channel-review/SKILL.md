---
name: youtube-channel-review
description: "Use when judging if YouTube content is slop or human-made."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [YouTube, slop, authenticity, review]
    editorial_name: YouTube Slop Review
    editorial_description: Verdict workflow for whether a YouTube channel's content is AI-generated, plagiarized, or human-made with slop packaging.

---

# YouTube channel slop/authenticity review

User shares a channel/video and asks "slop or not?". Deliver a verdict plus evidence. Three distinct verdicts — never collapse them:

1. **Gen-AI / fabricated slop** — invented stories dressed as real events (fake true-crime/death stories), faceless narration, no sources. Same genre as the debunked "Jessica Radcliffe orca" and True Crime Case Files fakes.
2. **Human content, slop packaging** — real human-made documentaries reuploaded by farm channels with clickbait retitles and AI-rewritten descriptions. Content genuine, channel is a reupload farm.
3. **Human content, plagiarism-driven** — real person, human cadence, but scripts lift sentences verbatim from source documentaries/other videos. Not AI; distinct verdict. hbomberguy's "Plagiarism You(Tube)" (Dec 2023) covered several such channels — search for known callouts before judging yourself.

## Procedure

1. **Channel overview:**
   ```bash
   yt-dlp --flat-playlist -J '<channel>/videos' > chan.json
   # Extract: entry count, titles, durations, upload dates
   ```

2. **Cadence analysis:**
   ```bash
   # Sample upload dates across playlist
   yt-dlp --skip-download --print '%(upload_date)s %(duration)s' <video-url>
   # Test entries at index 0 / ~1/4 / ~1/2 / late
   # ~1/day for months with no gaps = farm signal
   # 2-3/week with irregular gaps = human
   ```

3. **Transcripts (sample 3-5 videos):**
   ```bash
   yt-dlp --skip-download --write-auto-sub --sub-lang en --convert-subs srt <video-url>
   # Check: repetitive phrasing, unnatural transitions, hallucinated specifics
   ```

4. **Visual/audio tells:**
   - Same stock footage across unrelated videos
   - TTS narration (elevenlabs/play.ht artifacts: breath timing, over-enunciation)
   - AI art thumbnails (Midjourney/DALL-E tells: extra fingers, garbled text, surreal composition)
   - Identical background music across channel

5. **Source tracing:**
   - For suspicious claims: search unique phrases verbatim
   - Check if footage matches known documentaries (reverse image search key frames)
   - Cross-reference with hbomberguy callout list, Coffeezilla investigations, etc.

## Evidence standard

- **Gen-AI verdict**: Requires ≥2 of: TTS narration + hallucinated specifics + no verifiable sources + stock footage recycling
- **Slop packaging verdict**: Original source found (different channel, older upload) + reupload farm patterns (clickbait retitle, SEO description, no original commentary)
- **Plagiarism verdict**: Verbatim sentence matches to source + human cadence + creator has original content elsewhere

## Output format

```
VERDICT: [Gen-AI Slop | Human + Slop Packaging | Human + Plagiarism | Human Authentic]

EVIDENCE:
- Cadence: [upload pattern]
- Transcript sample: [key findings]
- Visual/audio: [TTS/stock footage/AI art tells]
- Source trace: [matches found or none]
- Known callouts: [links if applicable]

CONFIDENCE: [High/Medium/Low] — explain if Low
```

## Red flags checklist

- [ ] Upload frequency >1/day sustained for months
- [ ] Titles: "SHOCKING", "YOU WON'T BELIEVE", "The Truth About..."
- [ ] Thumbnails: AI art tells (check hands, text, symmetry)
- [ ] Narration: zero breaths, perfect enunciation, flat affect
- [ ] Descriptions: keyword-stuffed, no personal voice, identical structure
- [ ] No community tab, no shorts, no behind-the-scenes
- [ ] Channel age <1 year with 500+ videos
- [ ] Claims unverifiable (no sources, no links, "sources in description" → empty)