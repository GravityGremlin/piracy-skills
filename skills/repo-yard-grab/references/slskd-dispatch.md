# slskd dispatch patterns

## Direct lane download (bypasses aggregator dedup funnel)

Query the lane directly for full P2P results:
```bash
curl -s -H "Authorization: Bearer $SLSKD...OKEN" \
  "http://IPVPLACEHOLDER:19496/search/json?q=The Rabbit Joint Zelda"
```

Dispatch through aggregator (aggregator enqueues to lane). The LAN-bound
aggregator's `/download` needs NO auth (unauthenticated by design, behind
the login-free public edge):
```bash
curl -X POST "http://IPVPLACEHOLDER:19297/download" \
  --data-urlencode "service=slskd" --data-urlencode "kind=album" \
  --data-urlencode 'url=slskd://<peer>/<@@dir\file.ext>'
```

## Grab a whole peer album: kind=album + a SEED FILE url

For `kind=album` the lane enumerates the peer's shared folder itself
(`_album_file_list`) and enqueues every sibling with its REAL size — do NOT
hand-build a file list. Seed the url with ANY one file from the album
directory (a `slskd://<user>/<@@dir\file>` row straight from a search
result); the folder is walked up past disc markers to the album dir.

A pre-release album dir works the same way: when only singles are out, peers
still share a partial `<Artist>/<Album>` folder. Seed with any one released
track from that folder and the lane enqueues whatever siblings that peer
currently shares, with real sizes — one dispatch, not one per single.

A `kind=track` dispatch through the aggregator carries NO size
(`_enqueue_payload` sends url+type only), so it enqueues at size 0 and
aborts at transfer start (see below) — for a by-URL grab always use
`kind=album`.

## `{"error":"unavailable"}` is NOT proof the dispatch failed

The aggregator returns `{"error":"unavailable"}` when ITS request to the
lane times out — but peer-folder enumeration can outlast the aggregator's
timeout while the lane still succeeds and enqueues. Verify against the job
list before re-dispatching (a blind retry duplicates the grab):

    curl -s "http://IPVPLACEHOLDER:19297/jobs/unified/json?service=slskd&limit=40"

## By-URL dispatches can enqueue with size 0 — read the abort right

Measured 2026-10-06: a URL dispatch can reach slskd without the file size;
the transfer then aborts at start:

    Transfer aborted: the remote size of 1128408 does not match expected size 0

That is NOT "file unavailable" — the peer IS sharing; the abort is OUR side.
Tell the two failure classes apart:

- `Transfer rejected: File not shared.` — peer-side rejection; try a
  different peer (multiple peers often host the same FLAC dir — compare
  `username` and `dir` in the results). Peers come and go: a peer that
  rejected earlier can succeed later.
- `... does not match expected size 0` — our enqueue lacked the size; the
  fix below works without touching the lane.

**This class is deterministic in the dispatch SHAPE, not the peer.** The peer
is sharing fine; our request carried no size, so the abort reproduces against
every username in the result list. Re-dispatching the next peer with the same
shape is a guaranteed repeat — do not walk the results one username at a time,
and do not sleep on the job hoping it recovers: a size-0 transfer sits in
`running` forever and never moves a byte. The FIRST size-0 abort is the signal
to change shape — direct enqueue with the real size, or `kind=album` from a
seed file — and re-dispatch once.

## Direct enqueue on slskd (the fix that works)

slskd's own API (`http://IPVPLACEHOLDER:5030/api/v0`, 0.26.x) accepts enqueues
WITH the size. Auth accepted requests without a key (verified once
2026-10-06) — verify, don't assume:

```bash
curl -X POST "http://IPVPLACEHOLDER:5030/api/v0/transfers/downloads/<user>" \
  -H "Content-Type: application/json" \
  -d '[{"filename": "Musique\\FLAC\\Artist\\Album\\file.flac", "size": 7900713}]'
```

- `filename` = the search result's `filename` verbatim (backslash
  separators); `size` = the search result's `size`.
- 201 => read states: `Requested` / `Queued, Remotely` = accepted (the
  latter means the peer's own queue took us — the strong signal).
  500 `User <u> appears to be offline` = try later or another peer.
- Watch: `GET /api/v0/transfers/downloads` filtering `rabbit`/`zelda`-style
  substrings; `Completed, Succeeded` + real byte counts = done.
- **Bound the watch.** A healthy transfer shows a growing byte count between
  checks. A job whose progress does not move across two checks a couple of
  minutes apart is stalled — report the job id and the abort text and move on
  to a different shape or peer. Repeated sleep-and-poll on one job burns the
  session and still ends in the same abort.
- Files land under `/your-media-path/slskd/complete/<remote dir tail>/...` (the
  slskd container's download dir; it is also a share dir).
- **Landed downloads are cleaned after import** — the job's dirs remain but go
  empty (measured: masters gone within hours of a successful import). If you
  may need the raw file again (forensics, archiving, a second import), copy it
  out of the complete dir the moment it lands, not "later".

## Manual import of a rescued track (organizer)

The organizer runs as **uid 1000** and its dedupe checks the MUSIC TREE.
Recipe for single-track rescues:

1. Stage a 1-file dir under a staging root (/storage/fleet on the
   container = /your-media-path/fleet on the host; same device:inode). The top
   level is 0777; lane subdirs vary (slskd/ is 0775 root-only, others 0777).
   **`chmod 777` the staging dir** — the organizer must be able to UNLINK
   the staged file or the move fails halfway ("Permission denied while
   moving ... to /music/..."), leaving a stray library copy and a DB row
   that points at the staging path; a retry then marks the job
   `already_in_library` off that stray.
2. Enqueue:
   ```bash
   curl -X POST "http://IPVPLACEHOLDER:19298/enqueue" \
     -H "Authorization: Bearer $ORGANIZER_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"source_path": "/storage/fleet/<stagedir>", "target_artist": "...",
          "target_album": "...", "priority": 1, "source_kind": "slskd"}'
   ```
   `source_path` must resolve under a staging/queue root and be a
   DIRECTORY. `source_kind=slskd` routes through the gated MusicBrainz
   beets config (near-perfect match or skip -> quarantine; never an as-is
   import of untrusted tags).
3. Watch: `docker exec organizer grep <jobid> /app/data/audit.jsonl`.
   Terminal reasons: `gated_import_landed` (passed the landing proof — verify
   on disk; the proof is heuristic and a false positive deletes the staging),
   `already_in_library` / `already_in_library_gated` (tree dedupe SKIP — nothing
   was imported; see redo below), `quarantined` (gate failed). A `done` row is
   not evidence the album reached `/your-media-path/library/music-library`
   (references/verifying-downloads.md).
4. The same cycle runs library enrichment: non-opus files convert to opus
   160k in place (`-map_metadata 0`, then art embeds), so expect
   `<artist>/<album>/NN - Title.opus` + `cover.jpg` within the same run.

### Redo after a bad landing

`already_in_library` matches the MUSIC TREE (and beets state), not the
staging dir. To redo: remove the landed file(s) from
`/your-media-path/library/music-library` AS UID 1000 (`docker exec -i organizer
python3 -` — the ssh user cannot write /music) and delete the beets row
(`docker exec organizer python3 -c "import sqlite3; con =
sqlite3.connect('/app/.config/beets/library.db'); con.execute('delete from
items where id=<id>'); con.commit()"`), then re-stage and re-enqueue. If the staged file was consumed,
get a fresh copy first — the complete dir is cleaned after import, so the
original master may already be gone; re-dispatch the download (direct-enqueue
section above) when no copy survives anywhere.

## Common error: "Transfer rejected: File not shared"
Peer is online but not actively sharing the file. Try a different peer from the search results. Multiple peers often host the same FLAC directory — check `username` and `dir` fields.

## Headless tokens — fetch live, never hardcode

Token VALUES must not appear in skill files or docs: skills sync into the
the knowledge repo repo, and it must stay secret-free (cluster rule). Fetch at use:

- SLSKD lane token: the slskd-headless container env on your host
  (`docker inspect slskd-headless` / its compose env).
- Aggregator/Organizer token: the fleet's `.env` on your host
  (`docker exec organizer printenv`, or the fleet's `.env`).

## rygrab.py limitation
Current rygrab.py only accepts `--platform {qobuz,tidal,deezer}`. For slskd, dispatch via aggregator API directly as shown above, then monitor via lane API.
