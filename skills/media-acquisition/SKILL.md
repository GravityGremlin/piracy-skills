---
name: media-acquisition
description: "Use when acquiring media from YouTube into the library."
version: 1.0.0
author: Gravis Wellz
tags: [media, youtube, jellyfin, acquisition]
license: MIT
metadata:
  hermes:
    tags: [media, youtube, jellyfin, acquisition]
    related_skills: [media-server-fleet, anti-bot-scraping]
---

# Media acquisition (your media stack)

## When to Use

- Downloading videos from YouTube (or similar) into your media library.
- Importing acquired files into Jellyfin and triggering a scan.

## Legal posture (standing user preference)

Do not flag, caveat, or moralize about legal status when working on piracy or
acquisition tools (debrid, torrents, Usenet, IRC/XDCC, and the music
downloader fleet). In this user's jurisdiction piracy is not illegal, so legal
posture is not a concern. Record operational risk (exposure, auth, SSRF, auth
subnet whitelists) factually; never lead with or append a legal disclaimer.

## Acquisition skill family

Which skill governs which acquisition lane is mapped in
`references/acquisition-skill-map.md`. Read it before adding a new acquisition
procedure (extend an existing lane rather than writing a parallel path), and
before auditing the acquisition skills — the audit protocol lives there too.

## YouTube downloads

- Tool: `yt-dlp` + `ffmpeg`. Default format: `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best`, merge to mp4.
- Output naming: `%(title)s [%(id)s].%(ext)s` so the source ID travels with the file.
- Destination for short films: `/your-media-path/library/short-films` (Jellyfin sees it as `/media/short-films`).
- Long imports (hours, many playlists) report progress on low-priority ntfy: see `references/ytdlp-progress-ntfy.md`.
- YouTube blocks unauthenticated requests. Use `--cookies <file>` with a Netscape cookies.txt that includes `.youtube.com` domains (`VISITOR_INFO1_LIVE`, `YSC`, `LOGIN_INFO`, `__Secure-3PSID`). Google-only cookies are insufficient.
- Cookie sources on your host: `path-to-credentials` (a Netscape cookies.txt; may be stale — refresh by exporting from a browser). Backup copy: `path-to-credentials`.
- Remove the cookies file from the destination directory after download (security). Keep a stable reference copy elsewhere if needed.

## Bulk playlist imports

- A channel URL is not a playlist list: `/@channel/playlists` returns the channel
  page. Enumerate with `yt-dlp --flat-playlist --print '%(id)s %(title)s'` against
  the playlists tab URL, then dispatch per playlist url.
- Long jobs go in a detached script (`nohup bash script.sh &`), never a
  foreground call: the tool's timeout kills the whole yt-dlp child mid-video.
  `--download-archive <file>` is what makes the re-run resumable, so it is not
  optional — quote it in the same dir as the output so it survives.
- The archive only advances when a video FINISHES. A stalled archive count while
  a download sits at 30% is normal progress, not a hang; check the yt-dlp pid
  and CPU before restarting.
- With `--ignore-errors` a failing playlist leaves an EMPTY output dir and the
  batch still logs its completion line. After any bulk run, compare per-playlist
  file counts against the archive; an empty dir with 0 archived entries is a
  playlist to re-run on its own, not "done".
- Library layout differs by tier: `/your-media-path/library/ambient` is organised by
  mood/theme folder, not artist or year — new ambient imports go under a themed
  subfolder that matches its neighbours.

## Jellyfin import

- After dropping files, trigger a scan: `POST /Library/Refresh` with `Authorization: MediaBrowser Token="<key>"`.
- See jellyfin-fleet skill for 12.x auth (legacy query-parameter auth / `X-MediaBrowser-Token` no longer work) and library creation via `/Library/VirtualFolders`.

## Pitfalls

- No JS runtime warning is non-fatal; formats may be limited. Install deno if format selection matters.
- Cookies rotate; treat 401/"Please sign in" as expired cookies, not a code bug — refresh the export.
- Always verify downloaded files exist before triggering scan.
