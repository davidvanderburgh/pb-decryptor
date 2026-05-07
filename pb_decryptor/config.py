"""Constants and configuration for PB Asset Decryptor."""

import os
import sys

# ---------------------------------------------------------------------------
# Game database
#
# Pinball Brothers ships game updates as `.upd` files: plain gzip+tar
# archives, no encryption.  Internally each archive uses one of two layouts:
#
#   "rooted"  — paths are relative to /, like a system overlay:
#               game/<gamename>/...   etc/...   usr/...   opt/game/...
#               (Predator full installs put binaries+assets under opt/game/.)
#
#   "scoped"  — paths are scoped to ./game/<gamename>/, used for delta
#               updates that only touch a single game's files.
#
# Filename prefixes are ambiguous: `pbap*.upd` is shared by Alien (e.g.
# `pbap412.upd` = 4.1.2) and ABBA (e.g. `pbap141.upd` = 1.4.1).  We always
# verify the game by peeking at the internal paths.
# ---------------------------------------------------------------------------

#
# Clonezilla ISO support
# ----------------------
# Some games' `.upd` files are tiny code-only deltas (Alien, Queen) and don't
# contain the full asset set.  For those, the only way to recover assets is
# from a Clonezilla restore image (downloaded from the support portal).
#
# Each entry's `iso` block describes:
#   image_name  — the directory under `home/partimag/` inside the ISO
#                 (matches the `parts` / `disk` files Clonezilla writes)
#   partition   — the game partition to extract (e.g. "sda2")
#   mode        — "dd" (partclone.dd) or "ext4" (partclone.ext4)
#                 Clonezilla picks dd when invoked with `-q1`, which is the
#                 case for the PB images.
#

GAME_DB = {
    "abba": {
        "display": "ABBA",
        "internal_dir": "game/abba",          # archive substring that uniquely identifies this game
        "filename_prefixes": ["pbap"],        # ambiguous with alien; resolved by internal_dir
        "platform": "Custom C++ on FAST Pinball hardware",
        "iso": None,                          # no Clonezilla image — full assets in `pbap141.upd`
    },
    "alien": {
        "display": "Alien",
        "internal_dir": "game/alien",
        "filename_prefixes": ["pbap"],        # ambiguous with abba; resolved by internal_dir
        "platform": "Custom C++ on FAST Pinball hardware",
        "iso": {
            "image_name": "alien40",          # home/partimag/alien40/
            "partition": "sda2",              # 3.3 GB ext4 — game data
            "mode": "dd",                     # raw dd images (-q1 in clonezilla cmd)
            "filename_hints": ["alien40", "alien4"],
        },
    },
    "queen": {
        "display": "Queen",
        "internal_dir": "game/queen",
        "filename_prefixes": ["pbq"],
        "platform": "Custom C++ on FAST Pinball hardware",
        "iso": {
            # The ISO is named `clonezilla-live-queen10c-img.iso` but the
            # internal image name is `queen20d` (Queen 2.0d build).  We
            # discover the image directory at runtime, so this name is
            # informational only.
            "image_name": "queen20d",
            "partition": "sda2",              # 20.4 GB ext4 — game data
            "mode": "dd",
            "filename_hints": ["queen10", "queen20", "queen"],
        },
    },
    "predator": {
        "display": "Predator",
        "internal_dir": "opt/game",           # Predator full installs use opt/game/, not game/predator/
        "filename_prefixes": ["pbpp"],
        "platform": "Custom C++ on FAST Pinball hardware",
        "iso": None,                          # no Clonezilla image — full game in 1.0 .upd
    },
}

KNOWN_GAMES = {key: info["display"] for key, info in GAME_DB.items()}

# ---------------------------------------------------------------------------
# Pipeline phase names
# ---------------------------------------------------------------------------

EXTRACT_PHASES = [
    "Detect",
    "Extract",
    "Checksums",
    "Cleanup",
]

WRITE_PHASES = [
    "Detect",
    "Scan",
    "Repack",
    "Cleanup",
]

# ---------------------------------------------------------------------------
# Settings file location — platform-aware
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    _SETTINGS_DIR = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "pb_decryptor")
elif sys.platform == "darwin":
    _SETTINGS_DIR = os.path.join(
        os.path.expanduser("~/Library/Application Support"), "pb_decryptor")
else:
    _SETTINGS_DIR = os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
        "pb_decryptor")

SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "settings.json")

# ---------------------------------------------------------------------------
# GitHub repo (for update checker)
# ---------------------------------------------------------------------------

GITHUB_REPO = "davidvanderburgh/pb-decryptor"
