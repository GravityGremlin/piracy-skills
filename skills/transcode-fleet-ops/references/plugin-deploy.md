# Transcode plugin development and deploy runbook

## Repo and chain

- Source of truth: a git repo for custom plugins (e.g.,
  `~/Projects/Transcode/Plugins/` or a self-hosted forge).
- Naming: `Tdarr_Plugin_<author>_<name>.js`; numbered customs are the flow
  stack (00–06, then audio, then video).
- Deploy = copy changed files to
  `<data-dir>/server/Tdarr/Plugins/Local/` + `docker restart tdarr-server`.
  Server repacks `nodePlugins.Zip` at startup and on the hourly cycle; nodes
  download automatically.
- Post-deploy checks: server log "Zipping plugins folder"; node log
  "Downloading plugins from server" + version-match line.
- Backups: `cp` to `<data-dir>/plugin-backups-YYYYMMDD/` — NEVER inside
  `Local/` (READ ERROR spam in plugin list). Rollback = copy back + restart
  server.

## Common incident classes

### 1. Downmix budget stacking → size-gate veto loop

An audio downmix plugin budgets growth per worker cycle vs the staged file; a
fresh budget in a later cycle allows too much cumulative growth → size-gate
upperBound veto → revert → re-fail every scan.

**Symptom**: Files that were fine suddenly start failing with "New file size
not within limits" at 110–120% of original. Multiple files affected
simultaneously.

**Fix**: Budget cumulative vs `otherArguments.originalLibraryFile.file_size` —
the exact reference the size gate compares against.

### 2. Remux re-encode bloat

Container remux plugins with unlimited CRF can blow up small files (e.g.,
695 MB AVI → 1481 MB = +212%).

**Symptom**: Specific container types (AVI, MPG, XviD) fail with size-gate
vetoes. Output is larger than input despite "compression".

**Fix**: Cap `-maxrate` at ~1.05× source video bitrate (stream `bit_rate`,
not container bitrate). Compare against the size-gate numbers to find which
step grew the file.

### 3. Homoglyphs in log text

Plugin/log text contains non-ASCII look-alikes inside words, breaking regexes.

**Fix**: Anchor on ASCII substrings; extract numbers from raw bytes (see
report-parsing.md).

### 4. Plugin not executing

A plugin is wired into the flow but never runs (0 executions ever).

**Check**: Plugin ID matches the flow config; plugin file is in `Local/` not
just in the repo; server has repacked `nodePlugins.Zip` since the plugin was
added.

## Testing a plugin change

1. Make the change in the repo.
2. Copy to `Local/`.
3. Restart the server.
4. Check the server log for "Zipping plugins folder".
5. Check a node log for "Downloading plugins from server".
6. Force a library scan and verify the plugin executes on a test file.
7. Check the job report for the expected verdict.
8. If the plugin breaks, roll back from the backup and restart.
