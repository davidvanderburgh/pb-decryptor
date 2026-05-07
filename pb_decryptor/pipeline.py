"""Extract and Write pipelines for PB Asset Decryptor.

Pinball Brothers `.upd` files are plain gzip+tar archives — no encryption,
no embedded asset bundles.  Both pipelines are pure Python (stdlib only).
"""

import gzip
import hashlib
import io
import os
import shutil
import tarfile
import threading
import time
import zipfile

from .config import GAME_DB, EXTRACT_PHASES, WRITE_PHASES
from .formats import detect_game, detect_iso_game


CHECKSUMS_FILE = ".checksums.md5"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PipelineError(Exception):
    def __init__(self, phase, message):
        self.phase = phase
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Base pipeline
# ---------------------------------------------------------------------------

class _BasePipeline:
    def __init__(self, log_cb, phase_cb, progress_cb, done_cb):
        self._log = log_cb
        self._phase_cb = phase_cb
        self._progress = progress_cb
        self._done = done_cb
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _check_cancel(self):
        if self._cancelled:
            raise PipelineError("Cancelled", "Operation cancelled by user.")

    def _set_phase(self, index):
        self._phase_cb(index)

    def run(self):
        try:
            self._run()
        except PipelineError as e:
            self._done(False, e.message)
        except Exception as e:
            self._done(False, f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# Checksums (used to detect modified files for the Write pipeline)
# ---------------------------------------------------------------------------

def _md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _generate_checksums(folder, log_cb=None, progress_cb=None):
    """Walk *folder* and write `.checksums.md5`.  Returns file count.

    Symlinks and any files that can't be opened (broken symlink targets,
    permission errors, OneDrive placeholders) are skipped with a warning
    rather than aborting — Clonezilla extracts ship symlinks like
    ``/bin → usr/bin`` whose absolute targets don't resolve on the host.
    """
    files = []
    for dirpath, _, filenames in os.walk(folder):
        for fn in filenames:
            if fn.startswith("."):
                continue
            abs_path = os.path.join(dirpath, fn)
            if os.path.islink(abs_path):
                continue
            rel_path = os.path.relpath(abs_path, folder).replace("\\", "/")
            files.append((rel_path, abs_path))

    out_path = os.path.join(folder, CHECKSUMS_FILE)
    skipped = 0
    written = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for i, (rel_path, abs_path) in enumerate(files):
            try:
                md5 = _md5_file(abs_path)
            except OSError as e:
                # Broken symlink target, locked file, or OneDrive placeholder.
                skipped += 1
                if log_cb and skipped <= 5:
                    log_cb(f"  Skipping (cannot read): {rel_path} — {e}", "info")
                elif log_cb and skipped == 6:
                    log_cb("  ... further unreadable files will be skipped silently.",
                           "info")
                continue
            out.write(f"{rel_path}\t{md5}\n")
            written += 1
            if progress_cb:
                progress_cb(i + 1, len(files), rel_path)

    if log_cb:
        if skipped:
            log_cb(f"Checksums written for {written} file(s); skipped {skipped} "
                   f"unreadable.", "success")
        else:
            log_cb(f"Checksums written for {written} file(s).", "success")
    return written


def _read_checksums(folder):
    """Read `.checksums.md5` from *folder*.  Returns {rel_path: md5}."""
    path = os.path.join(folder, CHECKSUMS_FILE)
    baseline = {}
    if not os.path.isfile(path):
        return baseline
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if "\t" in line:
                rel, md5 = line.rsplit("\t", 1)
                baseline[rel] = md5
    return baseline


# ---------------------------------------------------------------------------
# Mod pack export / import
# ---------------------------------------------------------------------------

def export_mod_pack(assets_folder, zip_path, log_cb=None, progress_cb=None):
    """Zip only files that differ from the baseline checksums.

    Returns (count, zip_path).
    """
    baseline = _read_checksums(assets_folder)
    if not baseline:
        raise FileNotFoundError(
            f"No {CHECKSUMS_FILE} found in {assets_folder}. Extract first.")

    changed = []
    for rel, orig_md5 in baseline.items():
        abs_path = os.path.join(assets_folder, rel)
        if not os.path.isfile(abs_path):
            continue
        if _md5_file(abs_path) != orig_md5:
            changed.append(rel)

    if not changed:
        raise ValueError("No modified files found. Modify some files first.")

    if log_cb:
        log_cb(f"Packing {len(changed)} modified file(s)...", "info")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, rel in enumerate(changed):
            zf.write(os.path.join(assets_folder, rel), rel)
            if progress_cb:
                progress_cb(i + 1, len(changed), rel)

    return len(changed), zip_path


def import_mod_pack(zip_path, assets_folder, log_cb=None, progress_cb=None):
    """Extract a mod-pack zip into *assets_folder*.  Returns file count."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if log_cb:
            log_cb(f"Importing {len(names)} file(s)...", "info")
        for i, name in enumerate(names):
            zf.extract(name, assets_folder)
            if progress_cb:
                progress_cb(i + 1, len(names), name)
    return len(names)


# ---------------------------------------------------------------------------
# Extract pipeline
# ---------------------------------------------------------------------------

class ExtractPipeline(_BasePipeline):
    """Decompress + untar a `.upd` file into the output directory."""

    def __init__(self, upd_path, output_dir,
                 log_cb, phase_cb, progress_cb, done_cb):
        super().__init__(log_cb, phase_cb, progress_cb, done_cb)
        self.upd_path = upd_path
        self.output_dir = output_dir

    def _run(self):
        # Phase 0 — Detect
        self._set_phase(0)
        self._log("Detecting game...", "info")
        game_key = detect_game(self.upd_path)
        if game_key is None:
            raise PipelineError("Detect",
                f"Cannot identify game from: {os.path.basename(self.upd_path)}\n\n"
                f"The file does not match any known PB game layout.\n"
                f"Expected internal paths under one of: "
                f"{', '.join(info['internal_dir'] for info in GAME_DB.values())}.")
        info = GAME_DB[game_key]
        self._log(f"Game detected: {info['display']}", "success")
        self._check_cancel()

        os.makedirs(self.output_dir, exist_ok=True)

        # Phase 1 — Extract
        self._set_phase(1)
        self._log("Extracting archive...", "info")

        try:
            with tarfile.open(self.upd_path, "r:gz") as tar:
                members = tar.getmembers()
                total = len(members)
                self._log(f"  {total} entries found.", "info")
                for i, m in enumerate(members):
                    self._check_cancel()
                    # Defense in depth: reject tar entries with absolute paths
                    # or `..` components that could escape the output dir.
                    safe = _safe_member(m, self.output_dir)
                    if safe is None:
                        self._log(f"  Skipping unsafe entry: {m.name}", "error")
                        continue
                    tar.extract(safe, self.output_dir, set_attrs=True)
                    if i % 25 == 0 or i == total - 1:
                        self._progress(i + 1, total, safe.name)
        except (tarfile.TarError, EOFError) as e:
            raise PipelineError("Extract", _truncation_hint(self.upd_path, e))
        except OSError as e:
            # gzip raises plain OSError on a truncated stream — catch that too.
            msg = str(e)
            if "Compressed file ended" in msg or "unexpected end" in msg.lower():
                raise PipelineError("Extract",
                    _truncation_hint(self.upd_path, e))
            raise PipelineError("Extract", f"Filesystem error: {e}")

        self._log("Archive extracted.", "success")
        self._check_cancel()

        # Phase 2 — Checksums
        self._set_phase(2)
        self._log("Generating baseline checksums...", "info")
        n = _generate_checksums(
            self.output_dir,
            log_cb=self._log,
            progress_cb=self._progress,
        )

        # Phase 3 — Cleanup
        self._set_phase(3)
        self._log("Done.", "success")
        self._done(True,
            f"{info['display']} extracted successfully.\n\n"
            f"Output: {self.output_dir}\n"
            f"Files:  {n}")


def _safe_member(member, dest_dir):
    """Return *member* (possibly with name normalized) if it's safe to extract.

    Rejects absolute paths, drive letters, and `..` traversal.  Returns
    None for unsafe entries.
    """
    name = member.name
    if not name:
        return None
    # Disallow absolute paths and drive letters.
    if name.startswith("/") or name.startswith("\\"):
        return None
    if len(name) > 1 and name[1] == ":":  # Windows-style C:\foo
        return None
    # Disallow `..` traversal anywhere in the path.
    parts = name.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        return None
    return member


# ---------------------------------------------------------------------------
# Write pipeline
# ---------------------------------------------------------------------------

class WritePipeline(_BasePipeline):
    """Re-pack assets into a new `.upd`, preserving the original layout.

    The original `.upd` is the source of truth for the archive structure
    (member order, modes, owners, mtimes, directory entries).  For each
    member, the pipeline checks if the corresponding asset on disk has
    been modified — if so, the new content is swapped in; otherwise the
    original bytes are passed through.
    """

    def __init__(self, original_upd, assets_dir, output_upd,
                 log_cb, phase_cb, progress_cb, done_cb):
        super().__init__(log_cb, phase_cb, progress_cb, done_cb)
        self.original_upd = original_upd
        self.assets_dir = assets_dir
        self.output_upd = output_upd

    def _run(self):
        # Phase 0 — Detect
        self._set_phase(0)
        self._log("Detecting game...", "info")
        game_key = detect_game(self.original_upd)
        if game_key is None:
            raise PipelineError("Detect",
                f"Cannot identify game from: "
                f"{os.path.basename(self.original_upd)}.")
        info = GAME_DB[game_key]
        self._log(f"Game: {info['display']}", "success")
        self._check_cancel()

        if not os.path.isdir(self.assets_dir):
            raise PipelineError("Detect",
                f"Assets folder not found: {self.assets_dir}")

        # Phase 1 — Scan for changes
        self._set_phase(1)
        self._log("Scanning for modified files...", "info")
        baseline = _read_checksums(self.assets_dir)
        if not baseline:
            raise PipelineError("Scan",
                f"No baseline checksums found in:\n  {self.assets_dir}\n\n"
                f"Run the Extract tab first to create them.")

        changed = {}      # {archive_rel_path: filesystem_abs_path}
        for rel, orig_md5 in baseline.items():
            abs_path = os.path.join(self.assets_dir, rel)
            if not os.path.isfile(abs_path):
                continue
            if _md5_file(abs_path) != orig_md5:
                changed[rel] = abs_path

        if changed:
            self._log(f"  {len(changed)} modified file(s):", "info")
            for rel in sorted(changed)[:25]:
                self._log(f"    {rel}", "info")
            if len(changed) > 25:
                self._log(f"    ... and {len(changed) - 25} more", "info")
        else:
            self._log("  No modified files found.", "info")
            self._log("  The output `.upd` will be a byte-for-byte rebuild of "
                      "the original (useful as a smoke test).", "info")

        self._check_cancel()

        # Phase 2 — Repack
        self._set_phase(2)
        self._log(f"Building {os.path.basename(self.output_upd)}...", "info")
        try:
            os.makedirs(os.path.dirname(self.output_upd) or ".", exist_ok=True)
            self._repack(changed)
        except (tarfile.TarError, OSError) as e:
            raise PipelineError("Repack", f"Repack failed: {e}")

        self._check_cancel()

        # Phase 3 — Cleanup
        self._set_phase(3)
        size = os.path.getsize(self.output_upd)
        self._log(f"  Output size: {_format_size(size)}", "info")
        self._log("Done.", "success")

        msg = (f"{info['display']} update file built successfully.\n\n"
               f"Output: {self.output_upd}\n"
               f"Modified files: {len(changed)}\n\n"
               f"Copy to a FAT32 USB drive and insert it into the machine "
               f"to install.")
        self._done(True, msg)

    # ------------------------------------------------------------------
    # Repack helper
    # ------------------------------------------------------------------

    def _repack(self, changed):
        """Stream every member of the original tar through to a new tar,
        substituting modified file contents along the way.

        After streaming the original members, also append any files
        present in the assets folder that aren't in the original tar
        (delta-added files, or files the user dropped in by hand).  The
        new entries inherit owner/mode from the most similar parent
        directory entry in the original tar, falling back to sane
        defaults (root:root, 0644 for files, 0755 for executables).
        """
        with tarfile.open(self.original_upd, "r:gz") as src:
            members = src.getmembers()
            total = len(members)

            # Build a normalized set of paths that already exist in the
            # original tar so we can detect "extra" files later.
            orig_paths = {self._norm_member_name(m.name) for m in members}
            # Collect a path-prefix used in the original (e.g. "./" vs "")
            # so new files we synthesize match the same convention.
            sample_name = members[0].name if members else ""
            name_prefix = "./" if sample_name.startswith("./") else ""

            with tarfile.open(self.output_upd, "w:gz",
                              format=tarfile.GNU_FORMAT) as dst:
                for i, m in enumerate(members):
                    self._check_cancel()

                    rel = self._norm_member_name(m.name)
                    rel_alt = m.name.replace("\\", "/")

                    if m.isfile() and (rel in changed or rel_alt in changed):
                        new_path = changed.get(rel) or changed.get(rel_alt)
                        new_size = os.path.getsize(new_path)
                        new_m = tarfile.TarInfo(name=m.name)
                        new_m.size = new_size
                        new_m.mtime = int(os.path.getmtime(new_path))
                        new_m.mode = m.mode
                        new_m.uid = m.uid
                        new_m.gid = m.gid
                        new_m.uname = m.uname
                        new_m.gname = m.gname
                        new_m.type = m.type
                        with open(new_path, "rb") as f:
                            dst.addfile(new_m, f)
                    elif m.isfile():
                        f = src.extractfile(m)
                        if f is None:
                            dst.addfile(m)
                        else:
                            dst.addfile(m, f)
                    else:
                        dst.addfile(m)

                    if i % 25 == 0 or i == total - 1:
                        self._progress(i + 1, total, m.name)

                # ── Append "extra" files not in the original tar ─────
                # These come from a delta merge (`apply_delta`) or hand-drops.
                extras = self._find_extra_files(orig_paths)
                if extras:
                    self._log(f"  {len(extras)} new file(s) on disk not in "
                              f"the original — appending to output.", "info")
                    for j, (rel, abs_path) in enumerate(extras):
                        self._check_cancel()
                        member_name = name_prefix + rel
                        new_m = tarfile.TarInfo(name=member_name)
                        new_m.size = os.path.getsize(abs_path)
                        new_m.mtime = int(os.path.getmtime(abs_path))
                        # Files inherit 0755 if executable bit set on host,
                        # else 0644.  On Windows the executable bit isn't
                        # meaningful, so we default to 0755 for known game
                        # binaries (pinprog/vidprog) and 0644 otherwise.
                        new_m.mode = self._guess_mode(abs_path, rel)
                        new_m.uid = 0
                        new_m.gid = 0
                        new_m.uname = ""
                        new_m.gname = ""
                        new_m.type = tarfile.REGTYPE
                        with open(abs_path, "rb") as f:
                            dst.addfile(new_m, f)
                        if j % 25 == 0 or j == len(extras) - 1:
                            self._progress(j + 1, len(extras),
                                           f"appending: {rel}")

    @staticmethod
    def _norm_member_name(name):
        return name.lstrip("./").replace("\\", "/")

    def _find_extra_files(self, original_paths):
        """Return [(rel, abs)] for files in self.assets_dir whose normalized
        path isn't already in *original_paths*.  Skips dotfiles and the
        baseline checksum file."""
        extras = []
        for dirpath, _, filenames in os.walk(self.assets_dir):
            for fn in filenames:
                if fn.startswith("."):
                    continue
                abs_path = os.path.join(dirpath, fn)
                if os.path.islink(abs_path):
                    continue
                rel = (os.path.relpath(abs_path, self.assets_dir)
                       .replace("\\", "/"))
                if rel in original_paths:
                    continue
                extras.append((rel, abs_path))
        extras.sort()
        return extras

    @staticmethod
    def _guess_mode(abs_path, rel):
        """Pick a reasonable Unix mode for a new tar member when we don't
        have an authoritative source."""
        basename = os.path.basename(rel).lower()
        if basename in {"pinprog", "vidprog"} or basename.endswith(".sh"):
            return 0o755
        try:
            if os.access(abs_path, os.X_OK):
                return 0o755
        except OSError:
            pass
        return 0o644


def apply_delta(assets_folder, delta_upd_path,
                log_cb=None, progress_cb=None):
    """Untar a delta `.upd` on top of an extracted assets folder.

    Lets a modder chain a small post-rollup delta (e.g. ABBA 1.4.5 over
    1.4.1) onto an existing extract so the *next* Write produces a single
    `.upd` containing rollup + delta + mods.

    Files in the delta that match existing paths overwrite them; files
    that don't already exist are added.

    The baseline `.checksums.md5` is left **unchanged** intentionally:
    it represents the original rollup's content, which is what Write
    uses as a passthrough source.  Files overwritten by the delta will
    therefore show up as "modified relative to baseline" in the next
    Write run, and their on-disk (delta) content gets swapped into the
    output.  Newly-added delta files don't appear in the baseline either,
    so Write's `_find_extra_files` pass picks them up and appends them.

    Returns ``(overwritten_count, added_count, total_in_delta)``.
    """
    if not os.path.isdir(assets_folder):
        raise ValueError(f"Assets folder does not exist: {assets_folder}")
    if not os.path.isfile(delta_upd_path):
        raise ValueError(f"Delta file not found: {delta_upd_path}")

    if log_cb:
        log_cb(f"Applying delta: {os.path.basename(delta_upd_path)}", "info")

    overwritten = 0
    added = 0
    total = 0

    with tarfile.open(delta_upd_path, "r:gz") as tar:
        members = tar.getmembers()
        total = len(members)
        if log_cb:
            log_cb(f"  {total} entries in delta.", "info")
        for i, m in enumerate(members):
            safe = _safe_member(m, assets_folder)
            if safe is None:
                if log_cb:
                    log_cb(f"  Skipping unsafe entry: {m.name}", "error")
                continue
            target = os.path.join(assets_folder, safe.name)
            existed = os.path.lexists(target)
            tar.extract(safe, assets_folder, set_attrs=True)
            if safe.isfile():
                if existed:
                    overwritten += 1
                else:
                    added += 1
            if progress_cb and (i % 25 == 0 or i == total - 1):
                progress_cb(i + 1, total, safe.name)

    if log_cb:
        log_cb(f"Delta applied: {added} new file(s), "
               f"{overwritten} overwritten.", "success")
        log_cb("Baseline checksums left untouched — the delta's changes will "
               "be detected as modifications and included in the next "
               "Build .upd output.", "info")

    return overwritten, added, total


def _truncation_hint(upd_path, original_exc):
    """Build a user-facing error message for a likely-truncated `.upd` file."""
    try:
        size = os.path.getsize(upd_path)
    except OSError:
        size = -1
    name = os.path.basename(upd_path)
    return (
        f"The `.upd` file appears to be truncated or corrupt:\n"
        f"  {name}  ({size:,} bytes on disk)\n\n"
        f"This is usually a partial download.  Try re-downloading the file "
        f"directly from Pinball Brothers' support portal — for example:\n"
        f"  https://www.pinballbrothers.com/games/<game>/updates/<filename>.upd\n\n"
        f"Original error: {original_exc}"
    )


def _format_size(nbytes):
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 ** 2:
        return f"{nbytes / 1024:.1f} KiB"
    if nbytes < 1024 ** 3:
        return f"{nbytes / 1024**2:.1f} MiB"
    return f"{nbytes / 1024**3:.2f} GiB"


# ---------------------------------------------------------------------------
# Clonezilla ISO extract pipeline
# ---------------------------------------------------------------------------

class IsoExtractPipeline(_BasePipeline):
    """Extract game files from a Pinball Brothers Clonezilla ISO.

    Same 4-phase contract as :class:`ExtractPipeline` (Detect / Extract /
    Checksums / Cleanup).  The Extract phase covers mounting, restoring
    via partclone.dd, and dumping files via debugfs — sub-progress is
    streamed through the description string in the progress callback.
    """

    def __init__(self, iso_path, output_dir, executor,
                 log_cb, phase_cb, progress_cb, done_cb):
        super().__init__(log_cb, phase_cb, progress_cb, done_cb)
        self.iso_path = iso_path
        self.output_dir = output_dir
        self.executor = executor

    def _run(self):
        from . import clonezilla
        from .executor import CommandError as _CmdError

        # Phase 0 — Detect
        self._set_phase(0)
        self._log("Detecting game from ISO filename...", "info")
        game_key = detect_iso_game(self.iso_path)
        if game_key is None:
            raise PipelineError("Detect",
                f"Cannot identify game from ISO: "
                f"{os.path.basename(self.iso_path)}\n\n"
                f"Recognised filename hints: alien40, queen.")
        info = GAME_DB[game_key]
        self._log(f"Game detected: {info['display']}", "success")
        self._check_cancel()

        prereq = clonezilla.check_prerequisites(self.executor)
        missing = [(n, m) for n, ok, m in prereq if not ok]
        if missing:
            lines = "\n".join(f"  {n}: {m}" for n, m in missing)
            raise PipelineError("Detect",
                f"Missing prerequisites:\n{lines}\n\n"
                f"On Windows, install in WSL with:\n"
                f"  wsl -u root apt-get install -y e2fsprogs gzip")

        os.makedirs(self.output_dir, exist_ok=True)

        # Phase 1 — Extract
        self._set_phase(1)
        try:
            clonezilla.extract(
                self.iso_path, self.output_dir, self.executor,
                game_key=game_key,
                log_cb=self._log,
                progress_cb=self._progress,
            )
        except RuntimeError as e:
            raise PipelineError("Extract", str(e))
        except _CmdError as e:
            raise PipelineError("Extract", f"Executor error: {e}")

        self._check_cancel()

        # Phase 2 — Checksums
        self._set_phase(2)
        self._log("Generating baseline checksums...", "info")
        n = _generate_checksums(
            self.output_dir, log_cb=self._log, progress_cb=self._progress)

        # Phase 3 — Cleanup
        self._set_phase(3)
        self._log("Done.", "success")
        self._done(True,
            f"{info['display']} extracted from Clonezilla ISO.\n\n"
            f"Output: {self.output_dir}\n"
            f"Files:  {n}\n\n"
            f"This is a full filesystem dump from the game partition; the "
            f"PB game files live under `opt/game/` or `game/<gamename>/` "
            f"inside the output folder.")
