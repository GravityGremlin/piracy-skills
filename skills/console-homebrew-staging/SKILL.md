---
name: console-homebrew-staging
description: "Research, download, verify, and stage console homebrew/emulator/loader files into a clean SD-card layout (and PC-side tools). Use when a user wants to set up a modded retro console (PS2, etc.) — OPL-class loaders, emulators, FTB/exploit installers — and wants the newest builds copied into a staging folder. Covers GitHub-release asset discovery with rolling vs pinned versions, ELF verification, and archive extraction."
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [retro, emulation, homebrew, ps2, opl, sd-card, github-releases]
    related_skills: []
---

# Console homebrew staging

Fetch the latest working builds of console homebrew (loaders, emulators, boot/exploit
installers, system tools) into a clean folder that mirrors the intended SD-card layout, plus a
PC-tools area for host-side utilities. Validated on a PS2 setup (OPL/PS2-Launcher/wOPL, 2026-08).

## Session notes
- `references/ps2-homebrew.md` — PS2 deep reference: OPL/wOPL current state, exFAT vs APA, MX4SIO speeds, boot methods, emulator landscape, CHD→ISO→ZSO pipeline.

## Golden rule: verify against the LIVE project, not memory
- Homebrew scenes move fast and repos **rename/move** (OPL: `ps2homebrew/OPL` → now `ps2homebrew/Open-PS2-Loader`). Always resolve the current repo by search, don't assume a name.
- "Latest version" differs by project: **rolling** repos (OPL's `latest` tag = a build every few days) vs **pinned** (tagged releases). For rolling, grab the top/`latest` release; for pinned, grab the highest semver tag.
- Asset names vary: some projects ship raw ELF, some ship .zip/.7z with nested dirs. Verify contents before staging.

## Staging layout (mirrors SD card)
```
/staging/
├── APPS/                 # OPL apps (OPL.elf, wOPL.elf, PS2-Launcher.elf, cheat engines)
├── BOOT/                 # FMCB/FunTuna installers (ESR, uLaunchELF, FreeHDBoot)
├── CHEATS/               # OPL cheat databases (ps2rd, Action Replay Max)
├── EMULATORS/            # RetroArch cores, standalone emulators (ps2doom, ps2quake, ps2scummvm)
├── ISOS/                 # Game ISOs (optional, for testing)
├── OPL/                  # OPL config (conf_apps.cfg, CFG/, CHT/, THM/, ART/, VMC/, LNG/)
├── TOOLS/                # PC-side utilities (OrbitOPL Toolbox, CHDman, img2iso, ps2-iso-tools)
└── README.md             # Human-readable inventory + versions
```

## GitHub release asset discovery (scriptable)
```bash
# Rolling repo (OPL) — grab latest release assets
gh release list -R ps2homebrew/Open-PS2-Loader --limit 5 --json tagName,isLatest,assets

# Pinned repo (OrbitOPL Toolbox) — grab latest tagged release
gh release view -R orbitopl/OrbitOPL-Toolbox --json tagName,assets

# Authenticated (bypass 60/hr anon limit)
source /path/to/your/secrets-file   # exports GITHUB_TOKEN (from your secrets store)
gh api repos/ps2homebrew/Open-PS2-Loader/releases/latest --jq '.assets[].browser_download_url'
```

## ELF verification (before staging)
```bash
# Check it's a valid MIPS ELF for PS2
readelf -h OPL.elf | grep -E 'Machine:.*MIPS|Class:.*ELF32'
file OPL.elf  # → ELF 32-bit LSB executable, MIPS, MIPS-III version 1 (SYSV)
```

## Archive extraction (in-place, no temp dirs)
```bash
# 7z with skip-existing (-aos) — extracts in place, overwrites only missing
7z x archive.zip -o/staging/EMULATORS/ps2doom -aos
```

## Verification checklist (run before declaring staging complete)
- [ ] Every staged ELF passes `file` + `readelf` MIPS check
- [ ] OPL config dirs (CFG, CHT, THM, ART, VMC, LNG) present under OPL/
- [ ] OrbitOPL Toolbox executable runs: `./OrbitOPL-Toolbox --help`
- [ ] No duplicate/nested archives left in staging
- [ ] README.md lists every item with version/tag/date
