# Torrent / download client support (aria2, qBittorrent, Transmission)

The skills in this suite support three torrent/download engines. Every engine
does the same five jobs: accept an upload (`.rpc API`, `*.torrent file`, disc
`file` for magnet), report status, respect a `download_dir` (or container-mapped
save-path), control `paused`/`stopped` adds, and remove with or without data.
Swap engines by pointing these env vars at your engine of choice:

```bash
export TORRENT_ENGINE="aria2"        # aria2 | qbittorrent | transmission

export ARIA2_RPC="http://aria2-host:6800/jsonrpc"
export ARIA2_SECRET="<rpc-secret>"

export QBT_URL="http://qbittorrent-host:8080"
export QBT_USER="<user>"
export QBT_PASS="<pass>"

export TRANSMISSION_URL="http://transmission-host:9091/transmission/rpc"
export TRANSMISSION_USER="<user>"
export TRANSMISSION_PASS="<pass>"
```

## Which skill expects which engine

| Skill | Engine role |
|---|---|
| `self-hosted-debrid` | qBittorrent is the documented engine (5.x quirks probed live). Transmission swap is drop-in: same `torrent-add` shape. |
| `rom-collection` | aria2c binaries for DAT-verified set downloads (magnet/http/torrent). |
| `llm-media-dispatch` | aria2c as the headless addition step; RPC daemon mode covers remote adds. |
| `arr-stack-ops`/`media-request-ops` | Usenet path uses SABnzbd categories; torrent-based arr download clients (qBittorrent or Transmission) need a `music`/`movies` category staging root you do not delete. |
| `repo-yard-grab` | Downloader lanes carry their own HTTP APIs (Flask apps); a torrent client is not part of the music path. |

## aria2 (canonical CLI, optional JSON-RPC daemon)

CLI one-off (what most skills assume):

```bash
export TORRENT_ROOT="/your-media-path/incoming"
aria2c --seed-time=0 --dir="$TORRENT_ROOT" "<magnet or torrent or http url>"
```

Daemon mode (remote adds; set a secret or anyone who reaches the port can use
your disk):

```bash
aria2c --enable-rpc --rpc-secret="$ARIA2_SECRET" --rpc-listen-port=6800
curl -s "$ARIA2_RPC" \
  -d '{"jsonrpc":"2.0","id":"1","method":"aria2.addUri",
       "params":["token:'$ARIA2_SECRET'", ["<magnet>"]]}'
```

Gotchas:
- `aria2.addTorrent` takes the torrent bytes base64-encoded; magnets go through
  `aria2.addUri` with a single-element URIs array.
- Every method call carries the secret as its FIRST parameter: `"token:<secret>"`.
- JSON-RPC does not accept floats; pass string values for options.
- Do not surface port 6800 publicly: set `--rpc-secret`, keep it internal or
  reverse-proxy with TLS (`--rpc-secure`).

## qBittorrent (WebUI API v2 — the debrid engine)

```bash
# login (5.x returns 204 NO CONTENT on success - accept 204 as success)
curl -s -i "$QBT_URL/api/v2/auth/login" \
  -d "username=$QBT_USER&password=$QBT_PASS" \
  -c cookies.txt
# add magnets/urls/torrents
curl -s -b cookies.txt "$QBT_URL/api/v2/torrents/add" \
  -F "urls=<magnet or torrent url>" \
  -F "paused=true"
# status
curl -s -b cookies.txt "$QBT_URL/api/v2/torrents/info" | jq '.[0]'
```

Gotchas (5.x — all live-probed in the debrid skill):
- `torrents/pause` and `torrents/resume` were **renamed** to
  `torrents/stop` / `torrents/start` — the old endpoint names return 404
  "Endpoint does not exist".
- `auth/login` returns **204 No Content** on success; treating 204 as failure
  makes health checks report the engine as down when it is fine.
- Save-path alignment: if your API layer hands qBittorrent an absolute save
  path, the qBittorrent container must mount the same tree at the same path.
- qBittorrent's first-boot temp password rotates; pre-seed `qBittorrent.conf`
  with a WebUI auth-subnet whitelist so scripts can log in with env creds
  instead of scraping a temporary password.

## Transmission (drop-in RPC alternative)

```bash
# the whole protocol is one POST endpoint with a session handshake
read SID <<< $(curl -s -i "$TRANSMISSION_URL" \
  -u "$TRANSMISSION_USER:$TRANSMISSION_PASS" \
  --data '{"method":"session-get"}' \
  | grep -i X-Transmission-Session-Id | tr -d "\r" | awk '{print $2}')
curl -s "$TRANSMISSION_URL" \
  -u "$TRANSMISSION_USER:$TRANSMISSION_PASS" \
  -H "X-Transmission-Session-Id: $SID" \
  --data '{"method":"torrent-add",
           "arguments":{"filename":"<magnet or torrent url>","paused":false}}'
```

Gotchas:
- The CSRF handshake returns HTTP **409** with the real
  `X-Transmission-Session-Id` in the response headers; take it and replay the
  same request. This is success, not error — do not `|| exit 1` on it.
- Pass magnets via `filename`; pass local `.torrent` files via base64-encoded
  `metainfo`.
- Duplicates arrive as `torrent_duplicate` with HTTP-level `result: "success"`
  — decide on the object shape, not the result string.
- Auth is plain HTTP basic auth; keep it reverse-proxied with TLS.

## Usenet (SABnzbd) vs torrenters

For the arr/organizer path (SABnzbd usenet downloads feeding the beets import
pipeline) the equivalent client knob is the category -> staging root: set the
`music` category's download dir to the import pipeline's staging root via
SAB's own API (never hand-edit its `.ini`), so nothing outside the allowlisted
staging root happens even when the grab completes while the watcher is down.
`media-request-ops` ties the request intake to the same staging root.
