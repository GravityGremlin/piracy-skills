# Set-torrent sources: single-file grabs from huge sets

## The shape

Some collections ship as ONE `.torrent` per Group × System set with thousands
of files inside (one TOSEC calculator set measured: 8,209 files / 163 MB;
console Redump sets are far bigger). Per-file search results point INTO the
set (path + magnet), so single-file grabs need SELECTIVE download in the
torrent engine. This is the counterpart to the archive.org per-game shape in
`ia-redump-sources.md` — both are fine; the wiring differs.

Verified end-to-end: 135 KB transferred from the 163 MB set (target file +
piece slack only). Full survey with measurements lives in the project repo:
`docs/rom-sources-research-2026-10.md`.

## Minerva Archive (minerva-archive.org) — worked example

- No auth, no WAF; static archive + JSON API.
- `GET /v1/api/rom/search?query=<q>` → per-file hits carrying ONLY
  `{id, full_path, magnet, so_id}` — no group/console/region fields.
  Derive: group = first path component after `./` (TOSEC/Redump/…),
  system hint = second component.
- **Probe scripts must not use the Python-urllib default UA** — minerva
  answers 403 to `Python-urllib/…`; curl / httpx-style UAs pass (the app
  lane uses httpx, so it is unaffected). Search latency measured 10–23 s
  → give the client a ≥30 s timeout.
- `GET /v1/api/rom/filters` → taxonomy: 21 groups, 839 consoles,
  293 manufacturers, 69 regions (No-Intro, Redump, TOSEC, MAME, Xbox, …).
- Delivery: `.torrent` per set, linked from the `/rom?id=<id>` page as
  `https://minerva-archive.org/assets/Minerva_Myrient_v0.3/
  Minerva_Myrient - <Group> - <System>.torrent`.
  **URL-encode the spaces** in the href before fetching — the raw href
  breaks curl/urllib.
- The magnet form ships NO trackers; prefer the set `.torrent`
  (announce-list included).

## Post-grab serving & pruning pitfalls

- qbt `/torrents/files` names are relative to **savepath** and already
  include the set's top-level dir (e.g. `Minerva_Myrient/TOSEC/…`).
  - Existence checks / prune after a selective grab: `savepath/<name>` —
    NO extra prefix. Prefixing the job's display name misses every file
    and the prune silently no-ops (all ~25 k rows kept for a 1-file grab).
  - Serving: the `savepath/<relname>` candidate is the one that resolves
    for set grabs; keep both candidates for non-set jobs.
- Mark selective jobs in metadata (`meta.selective` + chosen file
  index/path/size once priorities are set) so the completed-refresh can
  prune the files table to what is on disk and manifests don't advertise
  thousands of skipped files.
- Status flow: `selecting` (metadata wait) → `downloading` (priorities
  applied + started) → `completed`. Surface `selecting` as in-flight in
  any UI.

## File-selection UX (picking files inside a big set)

- Expose the engine's file list as `{index, name, size, priority}` and a
  select-files endpoint taking `{selected: [indexes], start: bool}`:
  - selecting everything → single priority-1 call (skip the zero pass);
  - partial → all-0 first, then selected-1 (chunked pipe-joined ids);
  - `start` stays opt-in so an added-stopped job resumes only on user say-so.
- Derive counts client-side from the file list (total, priority>0) — the
  list is the truth; don't invent separate count fields.
- This is the manual version of the selective-grab recipe: add stopped →
  inspect → select → start.

## Selective download recipe (qBittorrent Web API, qbt 5.x)

Order matters — starting before priorities are set downloads the WHOLE set
(163 MB lands in ~25 s on a good swarm):

1. Download the `.torrent` yourself and compute the v1 infohash from its
   bytes (sha1 of the bencoded `info` dict) — the job is then queryable
   before the engine resolves anything, and the add can be verified.
2. `POST /api/v2/torrents/add` multipart `torrents=@set.torrent` with
   `savepath=/cache/<category>/<slug>`, `category`, `tags`, and
   **`stopped=true`** (added paused). In qbt 5.1+ the SUCCESS body is
   JSON (`{"added_torrent_ids":[…],"failure_count":0,"success_count":1}`)
   — parse it; see the engine-quirks section in SKILL.md.
2. Poll `GET /api/v2/torrents/info` until the torrent's `size > 0`
   (metadata fetched).
3. `GET /api/v2/torrents/files?hash=<h>` → index of the file whose `name`
   ENDS WITH the search hit's `full_path` (strip a leading `./`).
4. `POST /api/v2/torrents/filePrio`: ALL files `priority=0` — ids are
   **PIPE-separated** (`0|1|2`); comma lists fail 400 "File IDs must be
   integers". Chunk ~500 ids per call for 8k-file sets. Then the target:
   `id=<idx>`, `priority=1`.
5. `POST /api/v2/torrents/start` → only the target + piece slack
   downloads.
6. File lands at `<savepath>/<set dir>/<full_path>`, owned by the engine's
   PUID — no ownership friction with cache files.

## Debugging: live-probe from INSIDE the API container

    ssh <host> 'docker exec -i <api-container> python3 -' < probe.py

Env creds are already in place, sibling services resolve by docker name
(engine = `http://qbittorrent:8080`), and secrets never enter the
transcript. qbt 5.x login returns 204 on success. Probe shape: source page
→ torrent href → fetch → add stopped → metadata poll → files → priorities
→ start → verify on disk → cleanup.

## Other ROM sources (reachability notes)

- Vimm's Lair (vimm.net): alive, plain curl OK (nginx). Sets PHPSESSID +
  `counted=1` cookies on download pages (per-day download counter) —
  rate-limit yourself. 36 systems; `/vault/?p=list&system=<System>`,
  game pages `/vault/<id>`.
- coolrom.com / edgeemu.net / planetemu.net: reachable; download-flow
  quality unassessed.
- romsfun.com: DEAD ("website has been stopped") — never wire it.
