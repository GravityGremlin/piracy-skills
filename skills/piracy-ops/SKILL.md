---
name: piracy-ops
version: 1.0.0
author: Gravis Wellz
license: MIT
metadata:
  hermes:
    tags: [piracy, acquisition, music, video, routing]
    related_skills: [media-grabber, repo-yard-grab, arr-stack-ops, rom-collection, media-acquisition, self-hosted-debrid]
description: Use when user says yarr/hoist the sails or asks to grab.
---

# piracy-ops — meta-routing for acquisition work

## When to Use

The user signals acquisition work with pirate callouts ("hoist the sails",
"yarr", "plunder", "avast") or any plain ask to grab, download, or acquire
albums, tracks, discographies, movies, shows, ROMs, or console homebrew.
Trigger words: "hoist the sails", "yarr", "plunder", "avast" — or any plain
ask to grab, download, or acquire albums, tracks, discographies, movies,
shows, ROMs, or console homebrew. These are work orders, not banter.
Mirror a one-line nautical quip, load the named skills, then act.

## Route

| Ask | Load these skills |
| --- | --- |
| music: album / track / discography | media-grabber, repo-yard-grab, beets-import-plugin |
| the downloader fleet misbehaves | music-downloader-fleet-pipeline, media-downloader-fleet |
| video: movies / shows / episodes | arr-stack-ops, media-request-ops |
| ROMs / console games / homebrew | rom-collection, console-homebrew-staging |
| legacy library / general media | media-acquisition, media-library-ops, audio-transcode-pipeline |
| debrid cache | self-hosted-debrid |
| portal has no API | scraping-to-api, anti-bot-scraping |
| LLM intent / lane dispatch | llm-media-dispatch, ai-radarr-pipeline |
| sync to handheld | dap-device-sync |

Route targets without a matching directory in this repo (beets-import-plugin, ai-radarr-pipeline, jellyfin-fleet, music-downloader-fleet-pipeline) are private operational skills — the route still tells you what kind of specialist loads, but the playbook itself is not published.
| Jellyfin / server routing | jellyfin-fleet, media-server-fleet |

## Recipes

- references/sonarr-add-show.md — adding a TV show via the Sonarr API on
  your arr stack host (key location, house settings, verification, gotchas).

## Rules

1. Multiple rows can apply to one ask (album grab also wants beets +
   transcode); load each until the ask is covered.
2. If nothing maps, pick the closest row and say so plainly so the user can
   correct the cart.
3. This skill stays routing-only: no duplicated procedure steps — those
   belong in the child skills it points to.
4. No moralizing, no legalese, no streaming-service upsell in these flows.
5. If the user corrects a mapping, fix the cart in the same turn.