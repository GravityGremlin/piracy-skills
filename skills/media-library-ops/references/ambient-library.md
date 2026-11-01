# Ambient library (your media server host)

Path: `/your-media-path/library/ambient/` (your media server host; `/your-media-path` is the NAS mount).

## Layout rule

Sorted by **mood/theme folders**, NOT by artist/year like the music libraries.
As of 2026-10 there are ~13 top-level theme dirs. A new audio source that does
not fit an existing theme becomes its own subfolder (e.g. `ASMR Historian`).

## Importing a YouTube channel's playlists

- Enumerate playlists first; the channel `/playlists` tab alone does not give
  individual playlist IDs (use `yt-dlp --flat-playlist --print id,title`).
- Download one subfolder per playlist, capped at 480p:
  `yt-dlp -f 'bestvideo[height<=480]+bestaudio' --merge-output-format mkv`
- Always pass `--download-archive <dir>/.download-archive.txt` so an interrupted
  import resumes without re-fetching; sleep 3-8s between items to stay polite.
- Large channels (~1,300+ videos) run as a `nohup` background job writing to
  `<dir>/import.log`; never stage large files in `/tmp`.

## Progress monitoring with ntfy

Tail `import.log` for `[download] Downloading playlist: <name>` lines and POST
low-priority updates:

    curl -fsS -m 15 -H 'Priority: low' -H 'Tags: memo' \
      -d "Now downloading playlist: <name>" https://ntfy.your-domain.example/cluster-alerts

`Priority: low` maps to ntfy priority 2 (silent, no buzz). Notify on playlist
start and finish; send one final completion message when the import process exits.
