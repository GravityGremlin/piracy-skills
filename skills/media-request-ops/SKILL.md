---
name: media-request-ops
description: "Use when a media request manager breaks, loops, or needs upgrading."
version: 1.0.0
author: Gravis Wellz
license: MIT
---

# Media Request Ops

Covers media request managers (Sonarr/Radarr/Seerr/Jellyseerr-equivalents):
stack layout, failure modes, migration gotchas, and integration with media
servers.

## Stack layout

- Stack: `docker-compose.yaml`, service+container name `request-manager`,
  image `ghcr.io/example/request-manager:latest`.
- Data: `/path/to/request-manager` (bind-mounted `/app/config`).
- Port: host-only (WireGuard or LAN).
- compose must have `init: true`; image runs non-root (uid 1000). If files in
  the data dir are root-owned the app crash-loops with EACCES on logs — fix
  with `chown -R 1000:1000`.

## Failure modes

### Data dir re-created empty

Symptoms: user table 0, settings reset, app 307-loops /setup. Only re-setup
is possible. Prevention: backup the data dir before any stack change.

### Media server port mismatch

Old settings may point to the wrong media server port (e.g., 80 instead of
8096). Fix: set the correct port in the config file, restart.

### Recently Added Scan uses wrong user

The scan uses user id=1's media server user ID. If empty → 400 error. Fix:
set user id=1's media server user ID to the admin's real GUID from the media
server's `/Users?api_key=...`.

### Settings not reloading

Config file edits need a container restart to appear in the API (in-memory
settings). Restart after any config change.

## Migration gotchas (major version upgrades)

- DB migrates in place on first boot; users/media survive.
- Old settings may reference deprecated endpoints — verify all integrations
  after upgrade.
- Backup the data dir before any major version jump.

## Media server integration

- The request manager must target the **primary** media server, not a standby.
- Verify the media server's `Id` matches what the request manager expects.
- The request manager's credential must have admin privileges on the media
  server.

## Related skills

- `media-server-fleet` — media server topology and failover
- `transcode-fleet-ops` — transcode fleet management
- `docker-fleet-audit` — fleet-level health checks
