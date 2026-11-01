# Radarr: swap a wrong-language movie file

Movie (Mulaine 1998 case, 2026-10-31) came in as a hybrid mux with the wrong
audio while the tags lied (file had 2x'eng'/2x'chi' tracks, no German, and a
Mandarin *default*). Verified flow to replace it cleanly.

1. Key + movie id:
   `RK=$(grep -oP '(?<=<ApiKey>)[^<]+' /your-app-data-path/arrs/radarr/config.xml)`;
   `GET /api/v3/movie?apikey=$RK`, filter by title (`tmdbId`, `id`, current
   `movieFile.path`, existing `qualityProfileId`, `monitored`).
2. Actually probe the file, do not trust Radarr's cached `movieFile.mediaInfo`
   (it was EAC3-5.1 on a file that is 4x stereo Opus):
   `ffprobe -v error -select_streams a -show_entries
   "stream=index,codec_name,channels:stream_tags=language,title:stream_tags=language"
   -of csv "$FILE"`. The language tag itself can lie (muxers relabel tracks);
   the practical fix is to replace the file, not to fix tags.
   Note: **Tdarr post-processes library files** — it strips non-default audio
   (e.g. German) and may rewrite or relabel tracks, so the file on disk can
   diverge both from Radarr's cached mediainfo and from the release's original
   name; ffprobe on the actual file is the only truth.
3. Interactive release list: `GET /api/v3/Release?movieId=ID&apikey=...`
   (NOT movie/lookup, NOT /search/...).languages is `[{"id":1,"name":"English"}]`.
   Prefer names with explicit `English` + Disney/Netflix origin
   (e.g. `...Hungarian`);
   ignore uploader 'languages' labels — Usenet indexers stamp English on multi
   packs; the HONE DSNP 5.1 English family is a proven-good tag set.
   
4. Grab: `POST /api/v3/release` body `{'indexerId': int, 'guid': str,
   'movieId': int}`. Only one grab per attempt (it downloads via SAB; verify
   first before adding others).
5. Verify import (poll up to ~20 min): `GET /api/v3/queue?apikey=...` until the
   row is gone; then history should show `downloadFolderImported` AND a
   `movieFileDeleted` for the old file — Radarr swaps files automatically if
   upgradeAllowed. Final check is ffprobe on the new file (defaults, audio
   languages, x265/HDR).
6. Cleanup of dead queue rows: `DELETE /api/v3/queue/{id}?apikey=...&removeFromClient=false&blacklist=false`.
- The endpoint is `/api/v3/queue/{id}`, NOT `/api/v3/queue/remove/{id}` (405).
- Filter rows by exact prefix (`title.startswith('Mulan.1998.German')`) —
  matching on "German" == substring matches unrelated rows ("Solaris.2002.German")
  and can trigger premature deletions.
- `removeFromClient=false` keeps the SAB job record; `blacklist=false` won't
  prevent a rerun from grabbing the same release later.
