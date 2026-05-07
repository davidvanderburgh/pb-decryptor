"""Application controller — wires the GUI to the pipelines via a queue."""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from . import __version__
from .config import (SETTINGS_FILE, KNOWN_GAMES, GAME_DB,
                     EXTRACT_PHASES, WRITE_PHASES)
from .formats import detect_game, detect_iso_game
from .gui import MainWindow
from .pipeline import (ExtractPipeline, IsoExtractPipeline, WritePipeline,
                       apply_delta, export_mod_pack, import_mod_pack)
from .updater import check_for_update


# ---------------------------------------------------------------------------
# Thread-safe message types
# ---------------------------------------------------------------------------

class LogMsg:
    def __init__(self, text, level="info"):
        self.text = text
        self.level = level

class LinkMsg:
    def __init__(self, text, url):
        self.text = text
        self.url = url

class PhaseMsg:
    def __init__(self, index):
        self.index = index

class ProgressMsg:
    def __init__(self, current, total, desc=""):
        self.current = current
        self.total = total
        self.desc = desc

class DoneMsg:
    def __init__(self, success, summary):
        self.success = success
        self.summary = summary


# ---------------------------------------------------------------------------
# App controller
# ---------------------------------------------------------------------------

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.msg_queue = queue.Queue()
        self.pipeline = None
        self._active_mode = "extract"

        saved_theme = None
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved_theme = json.load(f).get("theme")
        except Exception:
            pass

        self.window = MainWindow(
            self.root,
            on_extract=self._start_extract,
            on_extract_cancel=self._cancel,
            on_write=self._start_write,
            on_write_cancel=self._cancel,
            on_apply_delta=self._start_apply_delta,
            on_export=self._start_export,
            on_import=self._start_import,
            on_theme_change=self._on_theme_change,
            initial_theme=saved_theme,
        )

        self._load_settings()
        self._poll_queue()

        self.root.title(f"PB Asset Decryptor v{__version__}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.root.after(1500, self._check_for_update)

    def run(self):
        self.root.mainloop()

    def _on_close(self):
        self._save_settings()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Queue polling — bridge background threads to the Tk main loop.
    # ------------------------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if isinstance(msg, LogMsg):
                    self.window.append_log(msg.text, msg.level)
                elif isinstance(msg, LinkMsg):
                    self.window.append_log_link(msg.text, msg.url)
                elif isinstance(msg, PhaseMsg):
                    self.window.set_phase(msg.index, mode=self._active_mode)
                    phases = self._phases_for_mode()
                    if msg.index < len(phases):
                        self.window.set_status(f"{phases[msg.index]}...")
                elif isinstance(msg, ProgressMsg):
                    self.window.set_progress(
                        msg.current, msg.total, msg.desc, mode=self._active_mode)
                elif isinstance(msg, DoneMsg):
                    self._on_done(msg.success, msg.summary)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _phases_for_mode(self):
        return WRITE_PHASES if self._active_mode == "write" else EXTRACT_PHASES

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------

    def _start_extract(self):
        in_path = self.window.extract_input_var.get().strip()
        output_path = self.window.extract_output_var.get().strip()

        if not in_path:
            messagebox.showwarning("Missing Input",
                "Please select a .upd or .iso file.")
            return
        if not os.path.isfile(in_path):
            messagebox.showerror("File Not Found", f"File not found:\n{in_path}")
            return
        if not output_path:
            messagebox.showwarning("Missing Input",
                "Please select an output folder.")
            return

        if os.path.isdir(output_path) and os.listdir(output_path):
            if not messagebox.askyesno(
                "Output Folder Not Empty",
                "The output folder already contains files.\n\n"
                "Extracting will overwrite existing files.\n\nContinue?",
            ):
                return

        self._save_settings()

        is_iso = in_path.lower().endswith(".iso")

        # Only the .upd flow has a corresponding Write step, so only
        # auto-populate the Write tab in that case.
        if not is_iso:
            self.window.write_upd_var.set(in_path)
            self.window.write_assets_var.set(output_path)

        self._active_mode = "extract"
        self.window.set_running(True, mode="extract")
        self.window.reset_steps(mode="extract")

        log_cb = lambda t, l="info": self.msg_queue.put(LogMsg(t, l))
        phase_cb = lambda i: self.msg_queue.put(PhaseMsg(i))
        progress_cb = lambda c, t, d="": self.msg_queue.put(ProgressMsg(c, t, d))
        done_cb = lambda s, m: self.msg_queue.put(DoneMsg(s, m))

        if is_iso:
            from .executor import create_executor
            executor = create_executor()
            self.pipeline = IsoExtractPipeline(
                in_path, output_path, executor,
                log_cb, phase_cb, progress_cb, done_cb,
            )
        else:
            self.pipeline = ExtractPipeline(
                in_path, output_path,
                log_cb, phase_cb, progress_cb, done_cb,
            )
        threading.Thread(target=self.pipeline.run, daemon=True).start()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def _start_write(self):
        original_upd = self.window.write_upd_var.get().strip()
        assets_dir = self.window.write_assets_var.get().strip()
        output_dir = self.window.write_output_var.get().strip()

        if not original_upd:
            messagebox.showwarning("Missing Input",
                "Please select the original .upd file.")
            return
        if not os.path.isfile(original_upd):
            messagebox.showerror("File Not Found",
                f"Original .upd not found:\n{original_upd}")
            return
        if not assets_dir:
            messagebox.showwarning("Missing Input",
                "Please select the modified assets folder.")
            return
        if not os.path.isdir(assets_dir):
            messagebox.showerror("Invalid Folder",
                f"Folder not found:\n{assets_dir}")
            return
        if not output_dir:
            messagebox.showwarning("Missing Input",
                "Please select an output folder.")
            return

        # Output filename: same name as the original .upd, but in the
        # chosen output dir.  If the user pointed output at a file path
        # ending in `.upd`, accept it directly.
        upd_name = os.path.basename(original_upd)
        if output_dir.lower().endswith(".upd"):
            output_upd = output_dir
        else:
            output_upd = os.path.join(output_dir, upd_name)

        if os.path.abspath(output_upd) == os.path.abspath(original_upd):
            messagebox.showerror("Same File",
                "Output path would overwrite the original .upd file.\n\n"
                "Choose a different output folder.")
            return

        self._save_settings()

        self._active_mode = "write"
        self.window.set_running(True, mode="write")
        self.window.reset_steps(mode="write")

        log_cb = lambda t, l="info": self.msg_queue.put(LogMsg(t, l))
        phase_cb = lambda i: self.msg_queue.put(PhaseMsg(i))
        progress_cb = lambda c, t, d="": self.msg_queue.put(ProgressMsg(c, t, d))
        done_cb = lambda s, m: self.msg_queue.put(DoneMsg(s, m))

        self.pipeline = WritePipeline(
            original_upd, assets_dir, output_upd,
            log_cb, phase_cb, progress_cb, done_cb,
        )
        threading.Thread(target=self.pipeline.run, daemon=True).start()

    # ------------------------------------------------------------------
    # Apply delta (overlay a delta .upd onto an extracted assets folder)
    # ------------------------------------------------------------------

    def _start_apply_delta(self):
        assets_dir = self.window.write_assets_var.get().strip()
        if not assets_dir or not os.path.isdir(assets_dir):
            messagebox.showwarning(
                "Missing Assets Folder",
                "Pick the extracted assets folder on the Write tab first.")
            return

        delta_path = filedialog.askopenfilename(
            title="Select delta .upd to apply on top",
            filetypes=[("PB update files", "*.upd"), ("All files", "*.*")],
        )
        if not delta_path:
            return

        if not messagebox.askyesno(
            "Apply Delta",
            f"Overlay\n  {os.path.basename(delta_path)}\n"
            f"on top of\n  {assets_dir}\n\n"
            f"Files in the delta will overwrite matching files in the "
            f"folder, and new files will be added.  Baseline checksums "
            f"will be regenerated so the merged state becomes the new "
            f"unmodified baseline.\n\nContinue?"
        ):
            return

        self.window.append_log(
            f"Applying delta: {os.path.basename(delta_path)}", "info")

        def _run():
            try:
                overwritten, added, _total = apply_delta(
                    assets_dir, delta_path,
                    log_cb=lambda t, l="info": self.msg_queue.put(LogMsg(t, l)),
                    progress_cb=lambda c, t, d="": self.msg_queue.put(
                        ProgressMsg(c, t, d)),
                )
                summary = (f"Delta applied:\n\n"
                           f"  {added} new file(s)\n"
                           f"  {overwritten} overwritten\n\n"
                           f"The delta's changes are now on disk.  Edit any "
                           f"assets you'd like, then click Build .upd on the "
                           f"Write tab — the output will contain rollup + "
                           f"delta + your mods in a single file.")
                self.root.after(0, lambda: messagebox.showinfo(
                    "Delta Applied", summary))
            except Exception as e:
                self.msg_queue.put(LogMsg(f"Apply delta failed: {e}", "error"))
                self.root.after(0, lambda: messagebox.showerror(
                    "Apply Delta Failed", str(e)))

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # Mod pack
    # ------------------------------------------------------------------

    def _start_export(self):
        assets_dir = self.window.write_assets_var.get().strip()
        if not assets_dir or not os.path.isdir(assets_dir):
            messagebox.showwarning("Missing Input",
                "Select an assets folder on the Write tab first.")
            return
        if not os.path.isfile(os.path.join(assets_dir, ".checksums.md5")):
            messagebox.showerror("No Baseline Checksums",
                "No .checksums.md5 found.  Extract first.")
            return

        zip_path = filedialog.asksaveasfilename(
            title="Save Mod Pack As",
            defaultextension=".zip",
            initialfile="pb_mod_pack.zip",
            filetypes=[("Zip files", "*.zip"), ("All files", "*.*")],
        )
        if not zip_path:
            return

        self.window.append_log("Exporting mod pack...", "info")

        def _run():
            try:
                n, path = export_mod_pack(
                    assets_dir, zip_path,
                    log_cb=lambda t, l="info": self.msg_queue.put(LogMsg(t, l)),
                    progress_cb=lambda c, t, d="": self.msg_queue.put(
                        ProgressMsg(c, t, d)),
                )
                self.msg_queue.put(LogMsg(
                    f"Mod pack: {n} file(s) → {path}", "success"))
                self.root.after(0, lambda: messagebox.showinfo(
                    "Export Complete",
                    f"Mod pack saved to:\n{path}\n\n"
                    f"Contains {n} modified file(s)."))
            except Exception as e:
                self.msg_queue.put(LogMsg(f"Export failed: {e}", "error"))
                self.root.after(0, lambda: messagebox.showerror(
                    "Export Failed", str(e)))

        threading.Thread(target=_run, daemon=True).start()

    def _start_import(self):
        assets_dir = self.window.write_assets_var.get().strip()
        if not assets_dir or not os.path.isdir(assets_dir):
            messagebox.showwarning("Missing Input",
                "Select an assets folder on the Write tab first.")
            return

        zip_path = filedialog.askopenfilename(
            title="Select Mod Pack ZIP",
            filetypes=[("Zip files", "*.zip"), ("All files", "*.*")],
        )
        if not zip_path:
            return

        if not messagebox.askyesno(
            "Import Mod Pack",
            f"Extract mod pack into:\n  {assets_dir}\n\n"
            f"Existing files with the same names will be overwritten.\n\nContinue?",
        ):
            return

        self.window.append_log("Importing mod pack...", "info")

        def _run():
            try:
                n = import_mod_pack(
                    zip_path, assets_dir,
                    log_cb=lambda t, l="info": self.msg_queue.put(LogMsg(t, l)),
                    progress_cb=lambda c, t, d="": self.msg_queue.put(
                        ProgressMsg(c, t, d)),
                )
                self.msg_queue.put(LogMsg(
                    f"Mod pack imported: {n} file(s).", "success"))
                self.root.after(0, lambda: messagebox.showinfo(
                    "Import Complete",
                    f"Imported {n} file(s).\n\n"
                    f"Use the Write tab to rebuild the .upd."))
            except Exception as e:
                self.msg_queue.put(LogMsg(f"Import failed: {e}", "error"))
                self.root.after(0, lambda: messagebox.showerror(
                    "Import Failed", str(e)))

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # Cancel / Done
    # ------------------------------------------------------------------

    def _cancel(self):
        if self.pipeline:
            self.window.append_log("Cancelling...", "error")
            self.pipeline.cancel()

    def _on_done(self, success, summary):
        is_extract = self._active_mode == "extract"
        self.window.set_running(False, mode=self._active_mode)
        if success:
            self.window.set_status("Complete!")
            title = "Extract Complete" if is_extract else "Write Complete"
            messagebox.showinfo(title, summary)
        else:
            self.window.set_status("Failed")
            title = "Extract Failed" if is_extract else "Write Failed"
            messagebox.showerror(title, summary)

    # ------------------------------------------------------------------
    # Update check
    # ------------------------------------------------------------------

    def _check_for_update(self):
        def _run():
            result = check_for_update(__version__)
            if result:
                version, url, notes = result
                self.msg_queue.put(LogMsg(f"Update available: v{version}", "info"))
                if notes:
                    for line in notes.splitlines():
                        line = line.strip()
                        if line:
                            self.msg_queue.put(LogMsg(f"  {line}", "info"))
                self.msg_queue.put(LinkMsg(f"Download v{version}", url))
        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE, "r") as f:
                s = json.load(f)
            self.window.extract_input_var.set(s.get("extract_input", ""))
            self.window.extract_output_var.set(s.get("extract_output", ""))
            self.window.write_upd_var.set(s.get("write_upd", ""))
            self.window.write_assets_var.set(s.get("write_assets", ""))
            self.window.write_output_var.set(s.get("write_output", ""))
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass

    def _save_settings(self):
        s = {
            "extract_input":  self.window.extract_input_var.get().strip(),
            "extract_output": self.window.extract_output_var.get().strip(),
            "write_upd":      self.window.write_upd_var.get().strip(),
            "write_assets":   self.window.write_assets_var.get().strip(),
            "write_output":   self.window.write_output_var.get().strip(),
            "theme":          self.window._current_theme,
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(s, f, indent=2)
        except OSError:
            pass

    def _on_theme_change(self, _theme):
        self._save_settings()
