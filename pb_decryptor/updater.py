"""Auto-update checker for PB Asset Decryptor.

Checks the GitHub releases API for newer versions on startup.
Uses only the standard library.  All errors are silently swallowed.
"""

import json
import urllib.request

from .config import GITHUB_REPO

RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
REQUEST_TIMEOUT = 5


def _parse_version(version_str):
    v = version_str.strip().lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return ()


def check_for_update(current_version):
    """Return (latest_version, download_url, notes) if newer, else None."""
    try:
        req = urllib.request.Request(
            RELEASES_URL,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PB-Asset-Decryptor-UpdateCheck",
            },
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())

        tag = data.get("tag_name", "")
        html_url = data.get("html_url", "")
        if not tag or not html_url:
            return None

        latest = _parse_version(tag)
        current = _parse_version(current_version)
        if latest and current and latest > current:
            return (tag.lstrip("v"), html_url, data.get("body", "") or "")
    except Exception:
        pass

    return None
