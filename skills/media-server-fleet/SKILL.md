---
name: media-server-fleet
description: "Use for any media server instance, standby, or routing."
version: 1.0.0
license: MIT
author: Gravis Wellz
---

# Media Server Fleet

Multiple containers may answer to the same service name — they are often
**independent servers plus a warm standby**, not replicas. Treating them as
replicas produces wrong answers about which one is serving, what the content
dependency is, and what a failure actually costs.

## Enumerate, then disambiguate by identity not by name

Container names lie. Identity comes from the server's own public endpoint —
the `Id` field is the database identity, and it is what tells a mirrored
standby from an independent instance:

```bash
for host in host1 host2 host3; do
  printf '%-11s ' "$host"
  ssh -o ConnectTimeout=5 -o BatchMode=yes "$host" \
    'docker ps --format "{{.Names}}|{{.Image}}|{{.Ports}}" | grep -i media-server'
done
curl -s --max-time 8 http://<host>:<port>/System/Info/Public   # Id + ServerName + Version
```

## Topology patterns

| Pattern | How to detect | What it means |
|---------|---------------|---------------|
| **Primary + warm standby** | Same `Id` from `/System/Info/Public`, different hosts | DB is rsynced; standby is a mirror, not a peer. Reads the library over NFS. |
| **Independent instances** | Different `Id` | Separate servers with separate libraries. Do not assume content parity. |
| **Standby out of sync** | Same `Id` but different library mount or stale DB | Check the standby's last sync time and library path. |

## Failover procedure

1. **Stop the primary** — `docker stop <primary-container>`
2. **Promote the standby** — `docker start <standby-container>`
3. **Verify the standby is serving** — `curl http://<standby-host>:<port>/System/Info/Public`
4. **Update DNS/routing** — point the service hostname to the standby host
5. **Rebuild the primary** — when the old primary returns, it becomes the new
   standby (rsync the DB back, verify content parity)

## Library mounting

- The library should be on shared storage (NFS, CIFS, or a distributed FS) so
  both primary and standby can read it.
- Mount the library read-only on the standby if it is truly warm (no writes
  needed until promotion).
- Verify the mount is active before promoting: `docker exec <container> ls /media`

## Related skills

- `media-request-ops` — request management (Sonarr/Radarr-equivalent)
- `transcode-fleet-ops` — transcode fleet management
- `docker-fleet-audit` — fleet-level health checks
