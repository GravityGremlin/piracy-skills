# Lossless sourcing from the downloader fleet

Standing rule: the audio SOURCE must be FLAC where possible; M4A/MP3 only as a
very last resort (the final opus 160k conversion does not make a lossy source
acceptable). This file covers the delivered-quality gates, how to probe what a
lane really delivers, and the entitlement re-login flow.

No paid service upgrades: the provider accounts in use are DONATED or the
user's own (Tidal). Do not propose or buy paid tiers to unlock lossless.
Active lanes: slskd (peer-sourced, gate-free) + Tidal (the user's own
Tidal account — delivered quality is set by the OAuth client pair the token
was issued under: the working lossless route is the in-container device login
with the FLAC-capable pair (`device_login.py` → approve at link.tidal.com),
NOT the PKCE login page, which is bot-walled and is not a device-flow client). Qobuz and Deezer lanes are sidelined (dead/free
donor accounts) — their notes below are historical. The delivery gates stay
the enforcement that keeps partial/lossy artifacts out of the library.

## slskd direct API — targeted re-grabs (bypassing the lane)

For repairing specific corrupt/missing files, drive slskd's own API instead of
the lane: search, pick a peer, enqueue the album dir, poll, convert locally.

- Key + base: `docker exec slskd-headless printenv SLSKD_API_KEY`, base
  `http://IPVPLACEHOLDER:5030`, header `X-API-Key`. Two containers: `slskd` (the
  daemon behind the API) and `slskd-headless` (the fleet lane).
- Search: `POST /api/v0/searches {"searchText": ..., "id": <uuid>}`, then
  `GET /api/v0/searches/<id>?includeResponses=true`; poll `state` until
  `Completed`. Popular albums settle in <75 s.
- Candidate scoring: prefer `hasFreeUploadSlot`, then `queueLength == 0`, then
  highest `uploadSpeed`; require a directory with the full tracklist
  (`n_flac >= expected tracks`). Read sample filenames — a live / compilation /
  single-version dir passes size and duration checks but is the WRONG recording;
  match the wanted track number + title in the filenames.
- Enqueue: `POST /api/v0/transfers/downloads/<url-encoded username>` with
  `[{filename, size}]` for the chosen dir; poll `GET /api/v0/transfers/downloads`
  for per-file `Completed, Succeeded`.
- **Two different storage trees — searching the wrong one reads as "the
  download never arrived":** slskd's own downloads land in
  `/storage/slskd/complete/<dir>`; lane-adopted jobs stage under
  `/storage/fleet/slskd/<group-id-hex>/` (hex = `group_id` in
  `/storage/fleet/slskd/data/lane.db`).
- Purging raw sources: lane staging dirs are transient and the library copies
  are already converted, but before deleting a group dir confirm every job of
  that group is `completed` in `lane.db` (`store.list_jobs` from
  `/your-stacks-path/fleet/tools/slskd-headless`).

## Policy keys (all default deny)

| Lane | yaml key | env override |
|---|---|---|
| Tidal | `tidal.lossy_policy` | `TIDAL_LOSSY_POLICY` |
| Qobuz (sidelined) | `qobuz.lossy_policy` | `QOBUZ_LOSSY_POLICY` |
| Deezer (sidelined) | `deezer.lossy_policy` | `DEEZER_LOSSY_POLICY` |
| slskd | no gate (peer reality); format mix logged at group finalize | — |

Deployment/liveness flips between sessions — read the lane's yaml in the prod
checkout (`/your-stacks-path/fleet/tools/<lane>/<lane>.yaml`) or probe a real job
before assuming a gate is active in prod.

## Reading what a grab actually got

- `GET {lane}/download/jobs/data` (or `/download/jobs/<id>/status`) →
  `data.source_quality` = {requested_quality, policy, lossless_tracks,
  lossy_tracks, codecs|formats}.
- Under `deny`, a lossy delivery shows as `status: error` with an entitlement
  message and a `source_quality` ledger proving what was delivered.
- Job ids purge from `/download/jobs/summary` within minutes; read status
  while the id is fresh, and delete stray test jobs when done.

## Probing what a lane truly delivers (before blaming the pipeline)

- **Tidal**: request `playbackinfopostpaywall` at each `audioquality`
  (LOW/HIGH/LOSSLESS/HI_RES_LOSSLESS) and read `audioQuality`/`codecs`.
  Adjudicated 2026-09-19: the fleet account IS entitled (subscription ACTIVE,
  premiumAccess true, HI_RES, paid) — the AAC-only delivery is a CLIENT
  entitlement cap (different OAuth client ids are served different codecs;
  streamrip PR #1017). Tidalapi's bundled id = streamrip's 'dev' id
  (fX2JxdmntZWK0ixT) which is handed AAC for non-hires-master releases; the
  PR's replacement id served the SAME AAC when swapped at request time, so the
  lever is a FRESH LOGIN with a lossless-entitled client id, not a runtime
  swap. Do not read entitlement from the plural `/users/<id>/subscriptions`
  (404s; tidalapi reads it → `user.subscription = None`); the singular
  `/users/<id>/subscription` is authoritative. Measure the artifact with
  ffprobe; never generalize one track's ceiling to the account.
- **Qobuz**: the delivery ladder `[7,6,5]` silently lands on 5 (MP3 320) when
  6/7 (FLAC) are not entitled; classify by the format_id that actually
  returned a stream URL.
- **Deezer**: the gw metadata `FORMAT` field does NOT reflect delivery —
  sniff magic bytes of the decrypted file (`fLaC` vs `ID3`/`0xFFEx`).

## Deploy registry + lane liveness (measured 2026-09-19)

- `deploy/deploy.sh` only deploys what the registry allows: **Tidal is
  `enabled`**; Qobuz and Deezer are now **DISABLED** (sidelined
  2026-09-21 — free/dead donor accounts; downloads refused by design).
  deploy answers "DISABLED in the registry — refusing to deploy"; do not flip
  the registry column unprompted. (Spotify's registry entry was removed
  with the lane, 2026-09-21.)
- **slskd-headless is NOT in the deploy registry.** Its app dir is
  bind-mounted from the prod checkout, so a code change lands with
  `docker restart slskd-headless` (then check `/health`).
- After any deploy, confirm prod equals the pushed commit:
  `git -C /your-stacks-path/fleet log --oneline -1`.
- Deezer art/metadata does not need the Deezer lane: `organizer/art.py`
  fetches iTunes (1200x1200) with a public `api.deezer.com` fallback — it
  works with the download lane disabled (verified live).

## Qobuz credential playbook (Qobuz) — 2026-09-19, measured

- Credentials live in THREE places and the TOKEN FILE wins over env:
  prod `.env` (`/your-stacks-path/fleet/tools/qobuz/.env`), dev `.env`, and
  the credential store for the container's config
  `/app/.config/qobuz`). Update all three, then RECREATE the container
  (`docker compose up -d qobuz-headless` from `/your-stacks-path/fleet`) —
  a plain `docker restart` keeps the old env baked at creation.
- A valid `user_auth_token` is NOT enough for streaming: signed endpoints
  (`track/getFileUrl`) also need the app id + the DERIVED per-timezone app
  secret. The bundle's `production.api.appSecret` signs `user/get` fine but
  yields `400 Invalid Request Signature parameter (request_sig)` on
  getFileUrl. Derive like streamrip: seeds from
  `[a-z].initialSeed("<seed>",window.utimezone.<tz>)` + the capitalized
  `name:"Region/City",info:"…",extras:"…"` pairs, then
  `base64(join(seed,info,extras)[:-44])`; try each timezone's 32-char secret
  until getFileUrl answers 200 (berlin worked for app 798273057).
- Entitlement tell: fetch format 6/7 and read the RESPONSE, not the request —
  `format_id`, `mime_type`, `sample`, `restrictions`. `audio/mpeg` on a
  mainstream control album = MP3-only; `sample: true` (with
  `UserUncredentialed` / `TrackRestrictedByPurchaseCredentials`) = a free
  'Qobuz Member' account serving 30-second PREVIEWS, which must never be
  imported (the gate refuses them under every policy). Never judge from one
  indie track, and never classify by the requested format id.
- Album jobs **fail fast on account-level previews**: the first `sample: true`
  refusal aborts the album (`aborted after track 1/N — …`) instead of grinding
  through every remaining track (shipped 2026-09-21 `06afee0`; per-track lossy
  refusals under deny still continue, so partially-entitled albums keep their
  lossless tracks).
- Deezer ARL validation: test each candidate in a FRESH session (requests/
  aiohttp reuse cookies, so a second request in the same session inherits the
  first login and masks a dead ARL — measured 2026-09-19). USER_ID=0 with no
  INSCRIPTION_DATE is a dead ARL; a working free ARL shows its USER_ID +
  streaming_group 'ads'.
- Validate a pasted token with `user/get` (X-App-Id + X-User-Auth-Token):
  200 + user id = good; 401 = rejected. The lane's own `validate()` hits
  `user/login?extra=partner`, which 401s even for good token-only auth —
  do not use it as the oracle.

## Entitlement re-login (device-flow lanes)

`POST /auth/start` returns `{}` while a valid token exists — `POST /auth/logout`
FIRST, then `/auth/start` and have the user open the device URL and log in with
an entitled account. The lane stays dark until the login completes; warn the
user before logging out, and prefer not to leave it logged out over a session
boundary.

## Expected shape of a lossy-blocked fleet

With deny defaults and no entitled accounts, provider-lane dispatches fail
per-album with the entitlement message — that is policy, not outage. rygrab
`--artist` dispatches will surface one errored job per album for the same
reason. slskd is then the only practical FLAC path, and it is also the
rare-album hunting lane.

## Lane job-management quirks

- Tidal does NOT support group actions: `POST
  /download/jobs/group/<id>/<action>` answers "this lane does not support
  group job actions" — cancel/delete jobs one by one
  (`/download/jobs/<id>/cancel`, then `/delete`).
- Discography dispatches return `group_id` + `queued` count; use the group id
  to review that batch's jobs.
