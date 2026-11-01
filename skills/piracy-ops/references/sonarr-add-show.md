# Sonarr add-show recipe (your arr stack host, verified 2026-10-31)

Working procedure for adding a TV show to the library on your arr stack host (no ssh needed
on your arr stack host; from another host, ssh your-user@your arr stack host first).

1. Key: `grep -o '<ApiKey>[^<]*' path-to-credentials` (local files,
   no sudo needed).
2. Check not already added: GET /api/v3/series and filter by title.
3. Lookup: GET /api/v3/series/lookup?term= and pick the right tvdbId.
4. POST /api/v3/series with the lookup result plus:
   - qualityProfileId: 1 (Standard — house convention, every recent show uses it)
   - rootFolderPath: /storage/library/shows
   - monitored: true, seasons: all monitored EXCEPT season 0 (specials) —
     matches how the rest of the library is configured
   - addOptions: {"monitor":"all","searchForMissingEpisodes":true}
   Sonarr v3 derives path from rootFolderPath + title (year) — defaults to the
   same folder-naming convention the existing library uses, so a pre-existing
   on-disk folder (even an unmapped one) is reused automatically.
5. Verify after ~45s: GET /api/v3/series/<id> — statistics should show
   episodeFileCount == episodeCount (pre-existing files import on add), and
   the queue shows the search grabbing any real gaps.

Gotchas:
- `sleep 45` in the SAME terminal call as the verification fetch, not a separate
  one — the queue scan is not instant.
- Season 0 specials are excluded from the importable set: totalEpisodeCount >
  episodeCount by the specials count, that is expected, not a failure.
- mem0 may be locked (another Qdrant client); park procedures in this skill
  instead of mem0_add.
