# Progress ntfy for long yt-dlp imports

Playlist and channel imports can run for hours. The expectation is low-priority
progress on `cluster-alerts`: one post per playlist as it starts and finishes,
plus a final summary — not silence until the end.

## Posting

```bash
curl -s -H "Title: <import> — <playlist> done" -H "Priority: low" -H "Tags: arrow_down" \
  -d "<n>/<total> videos archived in <playlist>" https://ntfy.your-domain.example/cluster-alerts
```

`Priority: low` keeps routine progress out of the alert path; never use default
or high for it.

## Monitor shape

- Run the monitor as its own process (`nohup bash monitor.sh <import-pid> &> out &`),
  not as a step inside the import script: it must be able to report the import
  dying, and it must not die with it.
- Poll every ~60s: `pgrep -f yt-dlp`, the `--download-archive` line count, and the
  file count in the playlist folder currently being written.
- Attribute progress to a playlist by diffing archive counts around it. yt-dlp
  writes an archive line only after a video completes, so the in-flight video is
  invisible — report "N archived, downloading" rather than a precise count.
- Post on playlist start, on playlist finish, and a final summary (playlists done,
  videos archived, any empty folders) when the import exits.
- If the import PID disappears, post "import stopped" with the archive count, so
  the resume point is recorded off-host.

## Pitfalls

- A foreground terminal call has a hard timeout and takes yt-dlp down mid-video.
  The archive makes the rerun cheap, but only for completed videos — launch long
  imports under `nohup` from the start.
- A playlist folder that is empty with 0 archive entries means that playlist's
  invocation died before its first completion: rerun it per playlist with the same
  archive file instead of restarting the whole job.
