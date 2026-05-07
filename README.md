# PB Asset Decryptor

[![Release](https://img.shields.io/github/v/release/davidvanderburgh/pb-decryptor?display_name=tag&sort=semver)](https://github.com/davidvanderburgh/pb-decryptor/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Build Release Installers](https://github.com/davidvanderburgh/pb-decryptor/actions/workflows/release.yml/badge.svg)](https://github.com/davidvanderburgh/pb-decryptor/actions/workflows/release.yml)

Extract and re-pack game assets from [Pinball Brothers](https://www.pinballbrothers.com/)
pinball machines.  Supports **Alien**, **ABBA**, **Queen**, and **Predator**.

> **Scope:** This tool targets *Pinball Brothers* games only (the post-2021
> production line: Alien LE 2021 / Ripley Edition 2023, ABBA, Queen, Predator).
> The original 2017 Heighway Pinball Alien — different company, different
> hardware, different file formats — is **not** supported.

## What It Does

Pinball Brothers ships game updates as `.upd` files (gzipped tar archives,
no encryption) and full system images as Clonezilla `.iso` restore images.
Inside each archive are the game's binaries (`pinprog`, `vidprog`) and
assets (`.ogg` audio, `.mp4` video, `.png` images, `.ttf` fonts).

This tool:

1. **Detects** the game from the file's name and internal paths.
2. **Extracts** the archive (or Clonezilla partition) into an editable folder.
3. **Tracks** baseline file checksums so you can find what you've modified.
4. **Re-packs** modified assets into a new `.upd` ready to write to USB and
   apply to the machine.  *(Re-pack is for `.upd` only — Clonezilla images
   are read-only here.)*

## Supported Sources

| Game | `.upd` (delta or full) | Clonezilla `.iso` (full) |
|------|------------------------|--------------------------|
| Alien | `pbap<version>.upd` (KB scale — code only) | `clonezilla-live-alien40.iso` (3.4 GB) |
| ABBA | `pbap<version>.upd` (e.g. `pbap141.upd` 2.2 GB rollup) | none |
| Queen | `pbq<version>.upd` (MB scale — code only) | `clonezilla-live-queen10c-img.iso` (10 GB) |
| Predator | `pbpp_predator_game_<ver>.upd` (e.g. `_1_0.upd` 4.8 GB full) | none |

For **Alien** and **Queen**, the regular `.upd` updates are tiny code-only
patches that don't include the game's video/audio.  To get the full asset
set you need the Clonezilla restore ISO (download links live in the
[support portal](https://pinballbrothers.freshdesk.com/) under each
game's "How-to rebuild machine" article).

> **Note:** the `pbap*.upd` filename prefix is shared between Alien and
> ABBA.  The detector peeks inside the archive to disambiguate.

## Requirements

- **Python 3.9+** with Tk support (Tk ships with the official installers).
- No third-party packages.

For `.upd` files: that's it.  Pure stdlib, all platforms.

For Clonezilla `.iso` files we need a Linux toolchain (the partition images
inside need to be extracted via `debugfs`):

| Platform | Requirement |
|----------|-------------|
| Windows  | WSL2 with `e2fsprogs` and `gzip` installed |
| Linux    | `e2fsprogs` and `gzip` (almost always already present) |
| macOS    | Untested — likely needs Homebrew `e2fsprogs` |

On Windows: `wsl --install -d Ubuntu` then `wsl -u root apt-get install -y e2fsprogs gzip`.

## Installation

### Pre-built Installers (recommended)

Grab the latest release from the [Releases page](https://github.com/davidvanderburgh/pb-decryptor/releases):

| Platform | File | Notes |
|----------|------|-------|
| Windows | `PB_Asset_Decryptor_Setup_v*.exe` | Bundles its own Python runtime |
| macOS | `PB_Asset_Decryptor_v*.dmg` | Universal binary |
| Linux | `PB_Asset_Decryptor-v*-x86_64.AppImage` | Portable, no install needed |

The Windows installer includes a "Install Prerequisites" task you can opt
into during setup — it sets up WSL2 + Ubuntu and installs `e2fsprogs` +
`gzip` inside.  These are only needed for the Clonezilla `.iso` flow; the
`.upd` flow works without them.

### Run from Source

1. Install [Python 3.10+](https://www.python.org/downloads/) with Tk.
2. Clone and run:
   ```
   git clone https://github.com/davidvanderburgh/pb-decryptor.git
   cd pb-decryptor
   python -m pb_decryptor
   ```

No third-party packages are required at runtime — the app uses only the
standard library (`tarfile`, `gzip`, `tkinter`, `urllib`, `hashlib`).
Pillow is only needed if you want to regenerate the icon
(`python generate_icon.py`).

## Quick Start

```
python -m pb_decryptor
```

or double-click `PB Asset Decryptor.pyw` (Windows) / run `launch.vbs`.

## Usage

The window has three tabs: **Extract**, **Write**, **Mod Pack**.

### Extract

1. Browse to your `.upd` *or* Clonezilla `.iso` — the game is auto-detected.
2. Choose an output folder.
3. Click **Extract**.

For `.upd` files the pipeline runs four phases:

| Phase | What happens |
|-------|-------------|
| Detect | Identifies the game by looking at internal paths |
| Extract | Decompresses and untars the `.upd` into the output folder |
| Checksums | Writes `.checksums.md5` (used later to find modifications) |
| Cleanup | Done |

For `.iso` files (Clonezilla restore images, Alien & Queen only) the
Extract phase is more involved:

1. **Mount** the ISO inside WSL/native Linux (loop mount, read-only).
2. **Locate** the partition image under `home/partimag/<image_name>/`
   (e.g. `alien40`, `queen20d`) using the Clonezilla metadata files
   (`parts`, `blkdev.list`, `sda-pt.parted`).
3. **Decompress** the partition.  PB uses Clonezilla's `-q1` mode which
   stores `dd | gzip` (no partclone wrapping despite the `.dd-ptcl-img`
   extension), so a straight `gunzip` on the concatenated `.aa`/`.ab`/
   `.ac` segments yields a raw ext4 image.
4. **Extract files** from the raw ext4 image via `debugfs rdump`.

The result is a full filesystem dump of the game partition (~7,500 files
for Alien, more for Queen).  The PB game files live under `game/<gamename>/`
inside the output, exactly matching the layout you'd see in a `.upd`.

### Editing Assets

Edit any file in place inside the output folder using your tool of choice:

| Type | Tools |
|------|-------|
| Audio (`.ogg`) | Audacity, ffmpeg |
| Video (`.mp4`) | ffmpeg, Kdenlive |
| Images (`.png`) | Photoshop, GIMP |
| Fonts (`.ttf`) | FontForge |

The Write pipeline detects modifications by comparing file MD5s against
`.checksums.md5`.

### Write

After editing, re-pack into a new `.upd`:

1. Browse to the **original `.upd`** (the source-of-truth for the archive
   layout — modes, owners, directory entries are copied from it).
2. Browse to the **modified assets folder** created by Extract.
3. Choose an **output folder** — the new `.upd` will use the same filename
   as the original.
4. Click **Build .upd**.

Phases:

| Phase | What happens |
|-------|-------------|
| Detect | Confirms which game the original `.upd` is for |
| Scan | Compares file MD5s against `.checksums.md5` to find modifications |
| Repack | Streams every member of the original tar through to a new tar, swapping in modified files |
| Cleanup | Done |

### Apply Delta (optional)

Pinball Brothers sometimes ships a small delta `.upd` on top of an older
rollup (e.g. ABBA's `pbap145.upd` is a 5 MB delta on top of the 2.2 GB
`pbap141.upd` rollup).  If you want to ship a single `.upd` containing
**rollup + latest delta + your mods**:

1. Extract the rollup `.upd` (e.g. `pbap141.upd`) on the **Extract** tab.
2. On the **Write** tab, click **Apply Delta...** and pick the delta
   `.upd`.  Files in the delta overwrite or get added on top of your
   assets folder.  Baseline checksums are intentionally left untouched
   so the delta's changes show up as "modifications" when you Build.
3. Edit any assets you'd like.
4. Click **Build .upd** — the output contains rollup + delta + mods in
   one file.

### Mod Pack

Share modifications without sharing the full extracted game.

- **Export** — produces a zip of just the files that differ from baseline.
- **Import** — extracts a mod pack zip into your assets folder so you can
  use the Write tab to rebuild.

## Installing on the Machine

1. Copy the output `.upd` file to a USB drive formatted **FAT32**.
2. With the machine running, insert the USB drive.
3. From the coin door menu, select **GAME UPDATE** and press ENTER.
4. The machine reboots automatically when the update finishes.

## The `.upd` File Format

```
<game>.upd
└── gzip compression
    └── tar archive
        ├── game/<gamename>/pinprog       (custom C++ pinball logic engine)
        ├── game/<gamename>/vidprog       (custom C++ video/display server)
        ├── game/<gamename>/media/...     (audio, video, images)
        ├── game/<gamename>/audio/...
        ├── etc/...                       (system overlay — Alien only)
        └── usr/bin/...                   (system overlay — Alien only)
```

Predator full installs use `opt/game/...` instead of `game/predator/...`.

There is no encryption, no signing, and no checksum that the machine
validates against the archive — it's a straight overlay onto the running
filesystem.

## Architecture

```
pb_decryptor/
├── __init__.py        # Version
├── __main__.py        # python -m pb_decryptor
├── app.py             # Application controller — wires GUI ↔ pipeline via queue
├── gui.py             # Tkinter GUI: Extract, Write, Mod Pack tabs
├── pipeline.py        # ExtractPipeline + WritePipeline + IsoExtractPipeline + apply_delta()
├── formats.py         # Game detection (filename + tar path peek + ISO hints)
├── clonezilla.py      # Clonezilla ISO extraction (mount → gunzip → debugfs)
├── executor.py        # WSL/Mac/Native runner for Linux tools (Clonezilla only)
├── config.py          # Game DB, phase names, settings paths
└── updater.py         # GitHub release update checker
```

The `.upd` flow is pure stdlib — `tarfile` + `gzip`, no shelling out.
The `.iso` flow needs a small Linux toolchain (`debugfs`, `gunzip`),
invoked through the platform-aware executor.

## Building

### Windows installer

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php) and Python with Tk:

```powershell
cd installer
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

`build.ps1` downloads the matching Python embeddable distribution, copies
tkinter from the local Python install, and compiles the Inno Setup
installer into `installer/Output/`.

### macOS DMG

```bash
brew install create-dmg
bash installer/build_macos.sh
```

### Linux AppImage

```bash
bash installer/build_linux.sh
```

(needs `appimagetool` on PATH — install from
[AppImage releases](https://github.com/AppImage/appimagetool/releases))

## Releasing

Version lives in [`pb_decryptor/__init__.py`](pb_decryptor/__init__.py).

```bash
# Bump __version__, commit, then:
git tag v$(python -c "import pb_decryptor; print(pb_decryptor.__version__)")
git push origin --tags
```

Pushing a `v*` tag triggers
[`.github/workflows/release.yml`](.github/workflows/release.yml), which
builds Windows, macOS, and Linux installers in parallel and attaches
them to a new GitHub Release.

## License

MIT.  See [LICENSE](LICENSE).
