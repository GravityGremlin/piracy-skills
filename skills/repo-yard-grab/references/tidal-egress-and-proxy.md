# Tidal egress: `abuse_detected`, proxies, rotation

## `abuse_detected` is an IP flag, not an account problem

`tidalapi.exceptions.AuthenticationError: Authentication failed with error
'abuse_detected: User account is suspended due to abuse'` comes from the SOURCE
IP, not the subscription or the token. The account still resolves normally
through another egress. Do not re-auth, and do not kill the token — route the
lane through a proxy instead.

Corollary for ops messaging: classify this as an egress/rate signal ("retry via
proxy"), separate from real auth failures (expired/revoked refresh token).
Alert text that says "authentication failed" for this case sends the next
session down the wrong path.

Alert taxonomy — three distinct remedies, never one "download failed" bucket:

| signal | class | remedy |
|---|---|---|
| `abuse_detected`, HTTP 429 from Tidal | egress / IP flag | rotate proxy, keep the token |
| `407 Proxy Authentication Required` (surfaces as `Not connected to Tidal`) | broken proxy config | fix credentials in the lane `.env`, not the token |
| token refresh fails with `invalid_grant` / expired refresh token | auth | interactive re-login (PKCE) |
| `requested LOSSLESS but Tidal delivered MP4A/EAC3` | entitlement | FLAC-capable client pair; do NOT loosen the deny gate |

Egress and the lossy cap interact: the SAME device-flow token (`is_pkce: false`,
no PKCE login) delivered true 16-bit/44.1 FLAC when the lane egressed through a
Mullvad proxy, while the same lane from the cluster's own IP got AAC. Measure a
downloaded track with `file` before blaming the client id or plan — re-auth and
client-id swaps are the expensive, wrong first move for what is often an
egress-class cap.

## Proxy inventory

Squid HTTP proxies on your proxy host, public host `your-domain.example`:

| index | HTTP | SOCKS5 |
|---|---|---|
| 1 | 16681 | 16691 |
| 2 | 16682 | 16692 |
| 3 | 16683 | 16693 |
| 4 | 16684 | 16694 |
| 5 | 16685 | 16695 |

They rotate upstream exits twice daily (00:00 / 12:00). Basic auth is required
— user in your proxy config, password in `path-to-credentials` on
your proxy host. Squid on 16680 is the shared-direct one; the 5 above are distinct
Mullvad cities.

Wiring, in the lane's gitignored `.env` (never the repo yaml — the creds are
secrets):

```
PROXY_LIST=["","http://gw:PASS@your-domain.example:16681", ... ]
```

Two traps: `cfg_value` returns an env override as a raw string, so
`config_base.shared_settings` must JSON-parse a `[`-prefixed value or the whole
array collapses into one proxy URL; and round-robin must skip the empty `''`
(direct) entry, otherwise 1/N of jobs keep egressing from the flagged IP and the
rotation looks broken.

## Symptom of missing proxy auth

Unauthenticated requests get `407 Proxy Authentication Required`. Inside the
lane this does NOT look like a proxy error — session init fails and the job
error reads `Not connected to Tidal` (or `Session init failed`). Before
chasing the token, verify the proxy itself:

```
docker exec tidal-headless python -c "import requests;\
p='http://gw:<pw>@your-domain.example:16681';\
print(requests.get('https://ifconfig.me',proxies={'http':p,'https':p},timeout=15).text)"
```

A different IP back = the egress works; the lane's own config is the problem.

## Wiring in the lane (credentials never enter the repo)

Set the list as a JSON array in the lane's gitignored `.env`
(`tools/tidal/.env`), which is read via `env_file` in compose:

```
PROXY_LIST=["","http://gw:<pw>@your-domain.example:16681","http://gw:<pw>@your-domain.example:16682"]
```

`fleet_core.app.config_base.shared_settings` parses a JSON-array string
override; without that parse the whole JSON blob collapses to one bogus proxy
entry. The committed yaml keeps only `- ''`. Recreate the container
(`docker compose up -d <lane>`) after editing `.env` — `env_file` is read at
container create, so an image rebuild alone does not pick it up.

## Rotation behaviour

A job with sentinel `proxy_index` of `-1` / `None` / out-of-range round-robins
across the configured proxies; an explicit index is honoured verbatim. Rotation
SKIPS the `''` direct entry whenever real proxies exist — the direct egress is
exactly the IP that gets flagged, so including it leaves one job in six broken.

The lane enqueue route is `/download/enqueue` (blueprint prefix `/download`),
and it requires a `url` field — not an id:

```
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://tidal.com/browse/album/<id>","type":"album","title":"...","artist":"...","proxy_index":-1}' \
  http://IPVPLACEHOLDER:19493/download/enqueue
```

Job status has no per-id GET route; read `/download/jobs/data` and filter by id.

## Delivered quality through a proxy (measured, one album)

With the legacy device client (`is_pkce: false`, `client: "flac"`) and a
Mullvad egress, Tidal delivered genuine `FLAC audio bitstream data, 16 bit,
stereo, 44.1 kHz`. The AAC cap previously observed on the direct IP did not
reproduce. Treat the "client pair caps below lossless" theory as unproven and
the IP-class explanation as the leading one — but confirm per job from
`data.source_quality` rather than assuming either way; the deny gate stays.

## Duplicate albums look like a download failure, and are not

If the library already holds the album, beets skips the new copy and the
organizer fails the job with
`post-import verification failed: staged audio did not land (no size or DB-census match)`
(enqueued retries hit 4). The lane still reports progress ~1.0 / completed.
Check the library for the artist+album BEFORE re-downloading; a differing track
count (Tidal edition vs held edition) is one trigger, but do not stop there:
beets also skips SILENTLY when the source path is already in its incremental
`taghistory`, and it skips on the DB row alone even when that row's files are
gone from disk. Run `beet import -p <dir>` in the organizer container —
`Skipped 1 paths` without an error means history/duplicate, not bad audio. See
`references/organizer-staging-roots.md` for the triage and the fix. The staged
copy is left in `import_staging` — remove it deliberately if disk matters, and
never assume missing audio means the proxy or auth broke.
