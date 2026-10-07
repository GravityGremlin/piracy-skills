---
name: ps2-homebrew
description: Setting up and maintaining a classic fat PS2 with Open PS2 Loader (OPL), SATA HDD adapter, MX4SIO SD adapter, FMCB/FunTuna boot, and emulators. Covers the verified-current state of OPL/wOPL, exFAT vs APA HDD formatting, MX4SIO speed realities, the SD card floor plan, emulator landscape, and conversion tooling.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [PS2, OPL, MX4SIO, FMCB, emulator, retro, homebrew, exFAT]
    related_skills: [console-homebrew-staging]

---

# PS2 Homebrew (OPL / SATA HDD / MX4SIO / emulators)

Generic reference for PS2 homebrew in 2026. All paths use placeholders — replace with your actual mount points.

## Verified current state (researched 2026 against upstream sources)

- **OPL (Open PS2 Loader)** = actively developed, repo renamed from `ps2homebrew/OPL` to **`ps2homebrew/Open-PS2-Loader`**. Releases: rolling `latest` tag (e.g. OPNPS2LD-v1.2.0-Beta-2245, Aug 2026) + daily CI builds. v1.1.0 (2021-09) was the last numbered stable.
- **wOPL** (`ps2homebrew/wOPL`, "Double Unofficial OPL") = community continuation with extra features, own Discord/Mega, rolling `latest` releases. Bleeding-edge option; plain OPL Release variant is the safe pick.
- **Devices OPL reads**: USB, MX4SIO, iLink/FireWire, SMBv1, internal HDD. Formats: ISO, ZSO (compressed, ~40% smaller), USBExtreme .ul, HDLoader format on APA HDDs. ELF apps via APPS/.
- **exFAT supported since OPL v1.2.0-beta rev1880** for USB/MX4SIO/iLink (MBR) and HDD (MBR ≤2TB or GPT unlimited). Allocation unit MUST be Default. Games >4GB need no splitting on exFAT. Partial fragmentation tolerated (up to 64 fragments since rev1893); defrag = copy off/format/copy back (never run defraggers).
- **HDD**: APA+PFS (classic HDLoader format, 48-bit LBA, ≤2TB) OR plain exFAT (drop ISOs in DVD/ — no APA needed). OPL auto-creates a 128MB +OPL partition on APA drives. NBD server shares the HDD over network; `ziso.py` (python3 + lz4, bundled in OPL repo `pc/`) makes ZSO.
- **MX4SIO speed**: Memory-card (SIO2) port reads ~2–4 MB/s, 2–3× faster than USB 1.1 (~1 MB/s), below HDD (16–33) / SMB (5–11). Benchmark bar = 4x DVD drive (~4–5.3 MB/s) that games were engineered for.
- **Boot**: FMCB 1.966 classic; FunTuna = maintained fork (covers newer slims); FHDB = install to HDD, no memory card; FreeDVDBoot (slims, from DVD); MechaPwn = region-free exploits. uLaunchELF/wLaunchELF = file manager/fallback.
- **Folders OPL auto-creates** (case-sensitive): CD/ DVD/ HDD/ ART/ THM/ LNG/ CHT/ CFG/ VMC/ APPS/.
- **Compatibility lists**: OPL-CL at sx.sytes.net/oplcl/games.aspx + psx-place OPL forum threads.

## Emulator landscape (2026)

| System | Recommended | Notes |
|--------|-------------|-------|
| NES | **FCEUmm-PS2** (`ps2homebrew`, maintained Jul 2026) | Fullspeed, multitap/turbo |
| SNES + NES | **SNESticleRevive** (ReyFxck, actively developed Aug 2026) | Legendary SNESticle revived for PS2 + InfoNES core. Reads FAT16/32/exFAT on mass0:/mass1:/mc0:/hdd0:/MMCE; ROMs from ROMS/ |
| SNES fallback | SNESStation | Old, frameskip |
| Genesis | pgen | Old, Generator-based |
| NeoGeo CD | neocdps2 | Niche |
| GB/GBC/GBA/N64 | **None viable** | Set expectations, don't chase |
| PS1 | **POPStarter + POPS** (Sony's own emulator) | .VCD files in POPS/; OPL integration; USB-centric, MX4SIO support unverified |
| Bonus | quake1_ps2, SMS Media Player | Native Quake port, audio/video |

## SD card floor plan

exFAT (Default allocation unit), folders: `DVD/` `CD/` `APPS/` `SNESticle/` `ROMS/` `POPS/` + OPL auto folders. Manifest: `OPNPS2LD.ELF`, `BOOT.ELF` (wLaunchELF), FCEUmm-PS2, SNESticleRevive, optional pgen/neocdps2/SMS/POPStarter, plus ISOs/ZSO. Emulators see the card as mass0:/mass1:. Slot 2 for MX4SIO, slot 1 keeps FMCB.

## CHD → ISO → ZSO conversion pipeline

Canonical source = lossless CHD. Convert on-demand:

```bash
# CHD → ISO (PS2 is CD-format single-track MODE1)
chdman extractcd -i "game.chd" -o "game.iso"

# ISO → ZSO (ziso.py from OPL repo pc/, needs python3+lz4)
python3 ziso.py "game.iso" "game.zso"
```

Batch conversion: parallelize locally (benchmark shows local SSD beats NFS-mounted hosts). Verify each ZSO with `ziso.py -v game.zso`.

## Minerva torrent workflow

Single unified download script (region-priority USA bug fixed, ZFS+lz4 sparse-check false positive handled). List torrent contents: `btlist.py <file.torrent> [--indexed]`. Prefer local CHD library over re-downloading.

## Sources (check upstream before restating)

- OPL README: `https://raw.githubusercontent.com/ps2homebrew/Open-PS2-Loader/master/README.md` (authoritative for formats/folders/exFAT revs)
- GitHub Releases API for current tags
- psx-place forums, consolemods.org wiki (Cloudflare-gated)