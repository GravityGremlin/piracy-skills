---
name: docker-fleet-audit
description: "Audit Docker hosts: fleet health, crash loops, timelines."
version: 1.0.0
license: MIT
---

# Docker Fleet Audit

Use when asked to "audit the dockers", "check the logs see what's up",
diagnose containers that are down/crash-looping, or reconstruct what happened
to a Docker host (mass exits, reboots, stuck stops). Works on any Docker host,
local or remote.

## "What's due for updates" audits — the digest-semantics trap

Two-phase, fully read-only, fleet tools:
- **Inventory script** (runs ON each host, pipe it: `ssh <host> 'bash -s' < script`;
  some hosts' login shell is fish)
- **Resolver script** (runs centrally, resolves every unique ref against its
  registry's HTTP API — anonymous token flow — and emits BOTH the config
  digest and the Docker-Content-Digest of the tag GET).

Compare per image store — this is the trap, it has burned a whole fleet run:
- classic store (overlay2): image `.Id` = config digest → compare vs resolver
  config digest.
- containerd store (overlayfs + io.containerd.snapshotter): `.Id` = the digest
  requested at pull (index digest for multi-arch) → compare vs
  Docker-Content-Digest ("target"), NOT config.

Mixing the two semantics gives mass false positives. Check
`docker info | grep -iE 'storage driver|driver-type'` per host first.

More gotchas, all observed live:
- Docker Hub anonymous quota is ~100 manifest GETs/hour/IP
  (`ratelimit-remaining` headers; w=3600). Dedupe refs fleet-wide and split
  runs across hosts with distinct egress IPs.
- On Hub, a repo that is missing/private/deleted returns **401 with a valid
  token**, not 404 — treat persistent 401s as "repo gone", not "retry".
- Multi-arch images: the resolver must request the same platform
  (linux/amd64) as the host, or the digest won't match.

## Crash-loop triage

```bash
# Find crash-looping containers
docker ps -a --filter "status=exited" --format "{{.Names}}\t{{.Status}}" | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head

# Get the last 50 lines of logs from a crash-looping container
docker logs --tail 50 <container>

# Check restart count
docker inspect <container> --format "{{.RestartCount}} restarts, state: {{.State.Error}}"
```

Common crash-loop causes:
- **EACCES on mounted volumes** — UID/GID mismatch between container user and
  host directory owner. Fix: `chown -R <uid>:<gid>` on the host dir, or set
  `user: "<uid>:<gid>"` in compose.
- **Port already in use** — another container or host process holds the port.
  Fix: `ss -tlnp | grep <port>` to find the holder.
- **Config parse error** — the container starts, fails to parse config, exits.
  Fix: check the container's config file syntax before restarting.
- **OOM killed** — `docker inspect` shows `OOMKilled: true`. Fix: raise the
  memory limit or reduce the workload.

## Timeline reconstruction

```bash
# Reconstruct what happened to a host
docker events --since 24h --until 0s --filter 'event=die' --filter 'event=start' \
  --format '{{.Time}} {{.Actor.Attributes.name}} {{.Action}}' | sort

# Check for mass exits (host reboot, OOM storm)
docker ps -a --format "{{.Names}}\t{{.Status}}" | grep -c "Exited"
```

## Service existence sweep

```bash
# List all running containers with their compose project
docker ps --format "{{.Names}}\t{{.Label \"com.docker.compose.project\"}}\t{{.Label \"com.docker.compose.service\"}}"

# Find containers NOT managed by compose (standalone)
docker ps --format "{{.Names}}" | while read name; do
  project=$(docker inspect "$name" --format "{{index .Config.Labels \"com.docker.compose.project\"}}")
  [ -z "$project" ] && echo "standalone: $name"
done
```

## Related skills

- `media-server-fleet` — media server fleet management
- `transcode-fleet-ops` — transcode fleet management
- `media-downloader-fleet` — download fleet management
