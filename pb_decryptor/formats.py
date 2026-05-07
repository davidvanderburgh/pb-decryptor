"""Game detection from `.upd` filenames, tar contents, and Clonezilla ISOs."""

import os
import gzip
import tarfile

from .config import GAME_DB


GZIP_MAGIC = b"\x1f\x8b"
ISO9660_MAGIC = b"CD001"   # at offset 0x8001 in any ISO 9660 image


def is_upd_file(path):
    """Cheap check: does the file look like a PB `.upd` (gzip-compressed tar)?"""
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "rb") as f:
            return f.read(2) == GZIP_MAGIC
    except OSError:
        return False


def is_iso_file(path):
    """Cheap check: does the file look like an ISO 9660 image?"""
    if not os.path.isfile(path):
        return False
    if not path.lower().endswith(".iso"):
        return False
    try:
        with open(path, "rb") as f:
            f.seek(0x8001)
            return f.read(5) == ISO9660_MAGIC
    except OSError:
        return False


def detect_iso_game(iso_path):
    """Return the game key for a Clonezilla `.iso`, or None if unknown.

    Detection is by filename hints first (most ISOs are named by their
    Clonezilla image_name, e.g. ``clonezilla-live-alien40.iso``).  If
    that fails the caller can mount the ISO and inspect ``home/partimag/``.
    """
    name = os.path.basename(iso_path).lower()
    for key, info in GAME_DB.items():
        iso = info.get("iso")
        if not iso:
            continue
        for hint in iso.get("filename_hints", []):
            if hint.lower() in name:
                return key
    return None


def detect_game(upd_path):
    """Return the game key for a `.upd` file, or None if unknown.

    Strategy: peek at internal tar paths first (authoritative — handles
    `pbap*.upd` ambiguity between Alien and ABBA).  Fall back to the
    filename prefix if peeking fails.
    """
    key = _detect_from_contents(upd_path)
    if key:
        return key
    return _detect_from_filename(upd_path)


def _detect_from_filename(upd_path):
    """Best-effort detect from filename prefix only.  Used as fallback."""
    name = os.path.basename(upd_path).lower()
    # Predator and Queen prefixes are unambiguous.
    if name.startswith("pbpp"):
        return "predator"
    if name.startswith("pbq"):
        return "queen"
    # `pbap*` is shared between Alien and ABBA — we cannot disambiguate
    # from filename alone, so return None and let the caller report it.
    return None


def _detect_from_contents(upd_path):
    """Open the tar and look for any path that uniquely identifies a game.

    Reads at most ~200 entries; bails out as soon as a match is found.
    """
    if not is_upd_file(upd_path):
        return None
    try:
        with tarfile.open(upd_path, "r:gz") as tar:
            count = 0
            for member in tar:
                count += 1
                if count > 200:
                    break
                norm = member.name.lstrip("./").replace("\\", "/")
                for key, info in GAME_DB.items():
                    needle = info["internal_dir"]
                    if norm.startswith(needle + "/") or norm == needle:
                        return key
    except (tarfile.TarError, OSError, EOFError):
        return None
    return None


def list_top_level_layout(upd_path, sample_limit=50):
    """Return a sorted list of distinct top-level path segments in *upd_path*.

    Used by the GUI to give the user a quick sanity-check view of the
    archive's structure.
    """
    seen = set()
    try:
        with tarfile.open(upd_path, "r:gz") as tar:
            for i, member in enumerate(tar):
                if i > sample_limit:
                    break
                norm = member.name.lstrip("./").replace("\\", "/")
                if not norm:
                    continue
                seen.add(norm.split("/", 1)[0])
    except (tarfile.TarError, OSError, EOFError):
        return []
    return sorted(seen)
