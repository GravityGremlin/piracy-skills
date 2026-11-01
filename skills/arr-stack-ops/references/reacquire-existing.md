# Re-acquiring episodes Sonarr already has

Applies to "redownload season N" / "grab a better copy of episode X" on any
Sonarr in the fleet. Files on disk are not an obstacle — they are what the
upgrade path replaces.

## 0. Find the host that owns the series

```bash
for H in $SONARR_HOSTS; do   # e.g. SONARR_HOSTS="sonarr-1 sonarr-2"
  echo "== $H"
  curl -s -m 10 -H "X-Api-Key: $KEY" "http://$H:8989/api/v3/series" \
    | python3 -c "import sys,json;[print(s['id'],s['title']) for s in json.load(sys.stdin) if 'TITLE' in s['title'].lower()]"
done
```

Both hosts read the key from `/your-app-data-path/arrs/sonarr/config.xml`
(`RK=$(grep -oP '(?<=<ApiKey>)[^<]+' /your-app-data-path/arrs/sonarr/config.xml)`, fetched on
the Sonarr host itself — over SSH if config.xml lives off-box). Ground truth
is the host whose `/api/v3/series/{id}` returns the record; searches fired
anywhere else are wasted.

## 1. Resolve season -> episode ids

```bash
curl -s -H "X-Api-Key: $KEY" "http://HOST:8989/api/v3/episode?seriesId=ID" \
  | python3 -c "
import sys,json
for e in json.load(sys.stdin):
    if e['seasonNumber']==3:
        print(e['id'], e['episodeNumber'], e['hasFile'], e.get('episodeFileId'), e['title'])
"
```

`hasFile: true` is expected and irrelevant — `EpisodeSearch` accepts these ids
all the same.

## 1.5 Check the profile allows it — the gate everything below depends on

```bash
curl -s -H "X-Api-Key: $KEY" "http://HOST:8989/api/v3/qualityprofile/QUALITYPROFILEID" \
  | python3 -c "import sys,json;p=json.load(sys.stdin);print(p['name'],'upgradeAllowed=',p['upgradeAllowed'],'cutoff=',p['cutoff']);print([(q.get('quality') or {}).get('name') for q in p['items'] if q.get('allowed')])"
```

`upgradeAllowed: false` — or a cutoff the existing files already satisfy — means
every release is rejected for an episode that has a file: `EpisodeSearch` answers
`0 reports downloaded` while `GET /api/v3/release?episodeId=` lists plenty, and a
forced `POST /api/v3/release` grab downloads and then fails at import for the same
reason. Under such a profile the only routes are (a) assign the series a profile
cloned with `upgradeAllowed: true`, run the season, then revert — never flip a
shared profile, it re-searches every series on it — or (b) delete files per
episode. Both change state the user did not ask to change: say which one you are
taking and why before firing.

## 2. Fire the search

One command for the whole season (preferred; Sonarr paces the per-episode
searches itself):

```bash
curl -s -H "X-Api-Key: $KEY" -H 'Content-Type: application/json' \
  -X POST http://HOST:8989/api/v3/command \
  -d '{"name":"EpisodeSearch","episodeIds":[ID1,ID2,...]}'
```

Returns a command resource; keep its `id` for polling. Do not retry the POST on
timeout — re-read `/api/v3/command` and reuse a still-running search instead of
stacking duplicates.

## 3. Watch and verify

- `GET /api/v3/command/{commandId}` — `status` (`started`/`completed`/`failed`)
  and `message`.
- `GET /api/v3/queue?pageSize=100&includeEpisode=true` — grabs in flight.
- `GET /api/v3/history?episodeId=<id>&sortKey=date&sortDirection=descending` —
  `grabbed`, then `downloadFolderImported`. A `downloadFailed` row means the
  release is dead; Sonarr will not retry it on its own.
- `GET /api/v3/episode?seriesId=ID` again — `episodeFileId` changed plus new
  size is the proof. Then confirm on the host path (`/storage/...` inside the
  container, `/your-media-path/...` on your arr stack host) that the file's mtime moved.

A command that reports `completed` with no new `episodeFileId` means Sonarr
searched and rejected everything — split the two causes with the release query,
not the message: no releases at all = indexer blackout (clear Prowlarr backoffs),
releases listed but nothing downloaded = profile gate (§1.5). Read the app log for
`ReleaseSearchService`/`DownloadDecisionMaker` before re-firing.

## 4. Forcing a DIFFERENT release than the one on disk

Sonarr ranks by quality profile and may pick the same release again. To force a
change, blocklist the current grab first:

1. `GET /api/v3/history?episodeId=<id>` -> the `grabbed` event's `id`.
2. `POST /api/v3/history/failed/{historyId}` — marks it failed and blocklists
   that release, so the next `EpisodeSearch` must pick something else.
3. Re-fire `EpisodeSearch` for those ids.

To override the profile's *ranking* (a deliberate downgrade, or a candidate it
ranks too low), list candidates with
`GET /api/v3/release?episodeId=<id>&includeUnknownSeriesItems=true` and grab a
specific result with `POST /api/v3/release` using that release resource. This is
what the UI's interactive search does.

## 5. When deleting really is the answer

Only these cases, and each needs the user's OK first — the app's recycle bin
may not be configured, and `DELETE /api/v3/episodefile/{id}` is immediate:

- The episode row itself is wrong (bad numbering, wrong series match) and must
  be re-imported wholesale.
- The user wants a lower quality than the profile's cutoff and accepts a manual
  grab pipeline instead.
- Disk is the source of truth and Sonarr's DB disagrees (files deleted outside
  Sonarr) — that is a `RefreshSeries`/`RescanSeries` problem, not a search one.
