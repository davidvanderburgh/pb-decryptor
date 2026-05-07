"""Main window GUI for PB Asset Decryptor.

Three tabs: Extract, Write, Mod Pack.
"""

import os
import sys
import time
import tkinter as tk
from tkinter import ttk, filedialog
import webbrowser

from .config import KNOWN_GAMES, EXTRACT_PHASES, WRITE_PHASES
from .formats import detect_game, detect_iso_game


def _platform_font():
    if sys.platform == "win32":
        return "Segoe UI", "Consolas"
    elif sys.platform == "darwin":
        return "SF Pro Text", "Menlo"
    return "sans-serif", "monospace"


_SANS_FONT, _MONO_FONT = _platform_font()

_THEMES = {
    "dark": {
        "bg": "#2d2d2d", "fg": "#cccccc", "field_bg": "#1e1e1e",
        "select_bg": "#264f78", "accent": "#569cd6", "success": "#6a9955",
        "error": "#f44747", "timestamp": "#808080", "gray": "#808080",
        "trough": "#404040", "border": "#555555", "button": "#404040",
        "tab_selected": "#1e1e1e", "link": "#3794ff",
    },
    "light": {
        "bg": "#f5f5f5", "fg": "#1e1e1e", "field_bg": "#ffffff",
        "select_bg": "#0078d7", "accent": "#0066cc", "success": "#2e7d32",
        "error": "#c62828", "timestamp": "#757575", "gray": "#888888",
        "trough": "#d0d0d0", "border": "#bbbbbb", "button": "#e0e0e0",
        "tab_selected": "#ffffff", "link": "#0066cc",
    },
}


class MainWindow:
    """Single-window Tk GUI with Extract, Write, and Mod Pack tabs."""

    def __init__(self, root,
                 on_extract, on_extract_cancel,
                 on_write, on_write_cancel,
                 on_export, on_import,
                 on_apply_delta=None,
                 on_theme_change=None, initial_theme=None):
        self.root = root
        self._on_extract = on_extract
        self._on_extract_cancel = on_extract_cancel
        self._on_write = on_write
        self._on_write_cancel = on_write_cancel
        self._on_apply_delta = on_apply_delta
        self._on_export = on_export
        self._on_import = on_import
        self._on_theme_change = on_theme_change

        root.geometry("760x780")
        root.minsize(680, 560)

        # Window icon
        if sys.platform == "win32":
            ico = os.path.join(os.path.dirname(__file__), "icon.ico")
            if os.path.isfile(ico):
                try:
                    root.iconbitmap(ico)
                except tk.TclError:
                    pass
        else:
            png = os.path.join(os.path.dirname(__file__), "icon.png")
            if os.path.isfile(png):
                try:
                    icon_img = tk.PhotoImage(file=png)
                    root.iconphoto(True, icon_img)
                    self._icon_img = icon_img
                except tk.TclError:
                    pass

        self._start_time = None
        self._timer_id = None
        self._current_theme = initial_theme or self._detect_system_theme()

        # Tk vars
        self.extract_input_var = tk.StringVar()
        self.extract_output_var = tk.StringVar()
        self.write_upd_var = tk.StringVar()
        self.write_assets_var = tk.StringVar()
        self.write_output_var = tk.StringVar()

        self._build_ui()
        self._init_phase_steps()
        self._apply_theme(self._current_theme)

        # Update detection badges + warnings on input changes
        self.extract_input_var.trace_add("write", self._update_extract_badge)
        self.extract_output_var.trace_add("write", self._check_extract_warn)
        self.write_upd_var.trace_add("write", self._update_write_badge)
        self.write_upd_var.trace_add("write",
            lambda *_: self._update_write_filename())
        self.write_output_var.trace_add("write",
            lambda *_: self._update_write_filename())

    @staticmethod
    def _detect_system_theme():
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return "light" if value else "dark"
            except Exception:
                return "light"
        elif sys.platform == "darwin":
            try:
                import subprocess as sp
                r = sp.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                           capture_output=True, text=True, timeout=5)
                return "dark" if "Dark" in r.stdout else "light"
            except Exception:
                return "light"
        return "light"

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = self.root

        # Top bar
        top = ttk.Frame(root)
        top.pack(fill=tk.X, padx=10, pady=(8, 0))
        ttk.Label(top, text="PB Asset Decryptor",
                  font=(_SANS_FONT, 13, "bold")).pack(side=tk.LEFT)
        self._theme_btn = ttk.Button(top, text="", width=3,
                                     command=self._toggle_theme)
        self._theme_btn.pack(side=tk.RIGHT)

        # Tabs
        self._notebook = ttk.Notebook(root)
        self._notebook.pack(fill=tk.X, expand=False, padx=10, pady=(8, 0))

        self._tab_extract = ttk.Frame(self._notebook)
        self._tab_write = ttk.Frame(self._notebook)
        self._tab_modpack = ttk.Frame(self._notebook)

        self._notebook.add(self._tab_extract, text="  Extract  ")
        self._notebook.add(self._tab_write, text="  Write  ")
        self._notebook.add(self._tab_modpack, text="  Mod Pack  ")

        self._build_extract_tab()
        self._build_write_tab()
        self._build_modpack_tab()

        # Phase indicators + progress bar
        status_frame = ttk.Frame(root)
        status_frame.pack(fill=tk.X, padx=10, pady=(4, 0))

        self._extract_phases_frame = ttk.Frame(status_frame)
        self._extract_phases_frame.pack(fill=tk.X)
        self._write_phases_frame = ttk.Frame(status_frame)

        self._progress_bar = ttk.Progressbar(status_frame, mode="determinate",
                                             maximum=100)
        self._progress_bar.pack(fill=tk.X, pady=(4, 2))

        status_row = ttk.Frame(status_frame)
        status_row.pack(fill=tk.X)
        self._status_label = ttk.Label(status_row, text="Ready",
                                       font=(_SANS_FONT, 9))
        self._status_label.pack(side=tk.LEFT)
        self._elapsed_label = ttk.Label(status_row, text="",
                                        font=(_SANS_FONT, 9))
        self._elapsed_label.pack(side=tk.RIGHT)

        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Log
        log_frame = ttk.LabelFrame(root, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 8))

        self._log_text = tk.Text(log_frame, wrap=tk.WORD,
                                 font=(_MONO_FONT, 9),
                                 state=tk.DISABLED, height=12)
        log_scroll = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.pack(fill=tk.BOTH, expand=True)

    def _build_extract_tab(self):
        f = self._tab_extract
        pad = {"padx": 10, "pady": 4}

        ttk.Label(f,
                  text="Extract a PB game `.upd` file or a Clonezilla `.iso` "
                  "(Alien / Queen).",
                  font=(_SANS_FONT, 9, "italic")).pack(anchor=tk.W, **pad)

        row = ttk.Frame(f); row.pack(fill=tk.X, **pad)
        ttk.Label(row, text=".upd / .iso:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.extract_input_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse...",
                   command=self._browse_extract_input).pack(
            side=tk.LEFT, padx=(4, 0))

        self._extract_badge = ttk.Label(f, text="",
                                        font=(_SANS_FONT, 9, "italic"))
        self._extract_badge.pack(anchor=tk.W, padx=24, pady=(0, 2))

        row2 = ttk.Frame(f); row2.pack(fill=tk.X, **pad)
        ttk.Label(row2, text="Output Folder:", width=14, anchor=tk.W).pack(
            side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.extract_output_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row2, text="Browse...",
                   command=self._browse_extract_output).pack(
            side=tk.LEFT, padx=(4, 0))

        self._extract_warn = ttk.Label(f, text="", foreground="#f44747",
                                       font=(_SANS_FONT, 9))
        self._extract_warn.pack(anchor=tk.W, padx=24)

        btn_row = ttk.Frame(f); btn_row.pack(fill=tk.X, padx=10, pady=(8, 4))
        self._extract_btn = ttk.Button(btn_row, text="Extract",
                                       command=self._on_extract)
        self._extract_btn.pack(side=tk.LEFT)
        self._extract_cancel_btn = ttk.Button(btn_row, text="Cancel",
                                              command=self._on_extract_cancel,
                                              state=tk.DISABLED)
        self._extract_cancel_btn.pack(side=tk.LEFT, padx=(6, 0))

    def _build_write_tab(self):
        f = self._tab_write
        pad = {"padx": 10, "pady": 4}

        ttk.Label(f,
                  text="Re-pack modified assets into a `.upd` file for USB install.",
                  font=(_SANS_FONT, 9, "italic")).pack(anchor=tk.W, **pad)

        row_upd = ttk.Frame(f); row_upd.pack(fill=tk.X, **pad)
        ttk.Label(row_upd, text="Original .upd:", width=16, anchor=tk.W).pack(
            side=tk.LEFT)
        ttk.Entry(row_upd, textvariable=self.write_upd_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_upd, text="Browse...",
                   command=self._browse_write_upd).pack(side=tk.LEFT, padx=(4, 0))

        self._write_badge = ttk.Label(f, text="",
                                      font=(_SANS_FONT, 9, "italic"))
        self._write_badge.pack(anchor=tk.W, padx=26, pady=(0, 2))

        row = ttk.Frame(f); row.pack(fill=tk.X, **pad)
        ttk.Label(row, text="Modified Assets:", width=16, anchor=tk.W).pack(
            side=tk.LEFT)
        ttk.Entry(row, textvariable=self.write_assets_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse...",
                   command=self._browse_write_assets).pack(
            side=tk.LEFT, padx=(4, 0))

        row2 = ttk.Frame(f); row2.pack(fill=tk.X, **pad)
        ttk.Label(row2, text="Output Folder:", width=16, anchor=tk.W).pack(
            side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.write_output_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row2, text="Browse...",
                   command=self._browse_write_output).pack(
            side=tk.LEFT, padx=(4, 0))

        self._write_filename_lbl = ttk.Label(f, text="",
                                             font=(_SANS_FONT, 9, "italic"))
        self._write_filename_lbl.pack(anchor=tk.W, padx=26)

        btn_row = ttk.Frame(f); btn_row.pack(fill=tk.X, padx=10, pady=(8, 4))
        self._write_btn = ttk.Button(btn_row, text="Build .upd",
                                     command=self._on_write)
        self._write_btn.pack(side=tk.LEFT)
        self._write_cancel_btn = ttk.Button(btn_row, text="Cancel",
                                            command=self._on_write_cancel,
                                            state=tk.DISABLED)
        self._write_cancel_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Apply-delta — chains a small post-rollup delta (e.g. ABBA 1.4.5)
        # onto the extracted rollup so the final Build .upd produces a
        # single file containing rollup + delta + mods.
        delta_frame = ttk.LabelFrame(f, text="Optional: Apply Delta on Top")
        delta_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        ttk.Label(
            delta_frame,
            text="Already at the latest rollup but want to layer a smaller "
            "delta update on top before modifying?  Click Apply Delta and "
            "pick the delta `.upd`.  Files in the delta overwrite or get "
            "added on top of your assets folder.  Baseline checksums refresh "
            "so the merged state becomes the new unmodified baseline.",
            font=(_SANS_FONT, 9), justify=tk.LEFT, wraplength=600,
        ).pack(anchor=tk.W, padx=8, pady=(4, 2))
        ttk.Button(delta_frame, text="Apply Delta...",
                   command=self._on_apply_delta).pack(
            anchor=tk.W, padx=8, pady=(2, 6))

        note_frame = ttk.LabelFrame(f, text="How to Install")
        note_frame.pack(fill=tk.X, padx=10, pady=(8, 4))
        note = ("1. Copy the output .upd file to a USB drive formatted FAT32.\n"
                "2. With the machine running, insert the USB drive.\n"
                "3. From the coin door menu, select GAME UPDATE and press ENTER.\n"
                "4. The machine reboots automatically when the update finishes.")
        ttk.Label(note_frame, text=note, font=(_SANS_FONT, 9),
                  justify=tk.LEFT, wraplength=600).pack(anchor=tk.W, padx=8, pady=6)

    def _build_modpack_tab(self):
        f = self._tab_modpack
        pad = {"padx": 10, "pady": 6}

        ttk.Label(f,
                  text="Share or apply mod packs — zips containing only your "
                  "modified files.",
                  font=(_SANS_FONT, 9, "italic")).pack(anchor=tk.W, **pad)

        row = ttk.Frame(f); row.pack(fill=tk.X, padx=10, pady=4)
        ttk.Label(row, text="Mod Folder:", width=12, anchor=tk.W).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.write_assets_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse...",
                   command=self._browse_write_assets).pack(
            side=tk.LEFT, padx=(4, 0))
        ttk.Label(f, text="(shared with the Write tab's Modified Assets path)",
                  font=(_SANS_FONT, 8, "italic")).pack(anchor=tk.W, padx=24)

        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=8)

        export_frame = ttk.LabelFrame(f, text="Export Mod Pack")
        export_frame.pack(fill=tk.X, padx=10, pady=4)
        ttk.Label(export_frame,
                  text="Create a zip of only your modified files to share.",
                  font=(_SANS_FONT, 9)).pack(anchor=tk.W, padx=8, pady=(4, 2))
        ttk.Button(export_frame, text="Export Mod Pack...",
                   command=self._on_export).pack(anchor=tk.W, padx=8, pady=(2, 6))

        import_frame = ttk.LabelFrame(f, text="Import Mod Pack")
        import_frame.pack(fill=tk.X, padx=10, pady=4)
        ttk.Label(import_frame,
                  text="Apply a mod pack zip from another user.",
                  font=(_SANS_FONT, 9)).pack(anchor=tk.W, padx=8, pady=(4, 2))
        ttk.Button(import_frame, text="Import Mod Pack...",
                   command=self._on_import).pack(anchor=tk.W, padx=8, pady=(2, 6))

    def _build_phase_steps(self, parent, phases, mode):
        labels = []
        for name in phases:
            lbl = ttk.Label(parent, text=f"○ {name}", font=(_SANS_FONT, 8))
            lbl.pack(side=tk.LEFT, padx=(0, 12))
            labels.append(lbl)
        if mode == "extract":
            self._extract_phase_labels = labels
        else:
            self._write_phase_labels = labels

    def _init_phase_steps(self):
        self._build_phase_steps(self._extract_phases_frame, EXTRACT_PHASES,
                                "extract")
        self._build_phase_steps(self._write_phases_frame, WRITE_PHASES, "write")

    def _on_tab_changed(self, _event=None):
        idx = self._notebook.index(self._notebook.select())
        if idx == 1:  # Write tab
            self._extract_phases_frame.pack_forget()
            self._write_phases_frame.pack(fill=tk.X, before=self._progress_bar)
        else:
            self._write_phases_frame.pack_forget()
            self._extract_phases_frame.pack(fill=tk.X, before=self._progress_bar)

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_extract_input(self):
        path = filedialog.askopenfilename(
            title="Select .upd or Clonezilla .iso",
            filetypes=[
                ("PB game files", "*.upd *.iso"),
                ("PB update files", "*.upd"),
                ("Clonezilla images", "*.iso"),
                ("All files", "*.*"),
            ])
        if path:
            self.extract_input_var.set(path)

    def _browse_extract_output(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.extract_output_var.set(path)

    def _browse_write_upd(self):
        path = filedialog.askopenfilename(
            title="Select original .upd file",
            filetypes=[("PB update files", "*.upd"), ("All files", "*.*")])
        if path:
            self.write_upd_var.set(path)

    def _browse_write_assets(self):
        path = filedialog.askdirectory(
            title="Select modified assets folder")
        if path:
            self.write_assets_var.set(path)

    def _browse_write_output(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.write_output_var.set(path)

    # ------------------------------------------------------------------
    # Dynamic UI state
    # ------------------------------------------------------------------

    def _update_extract_badge(self, *_):
        self._set_badge(self._extract_badge, self.extract_input_var.get())

    def _update_write_badge(self, *_):
        self._set_badge(self._write_badge, self.write_upd_var.get())

    def _set_badge(self, label, path):
        path = (path or "").strip()
        if not path:
            label.configure(text="")
            return
        if not os.path.isfile(path):
            label.configure(text="")
            return
        if path.lower().endswith(".iso"):
            key = detect_iso_game(path)
            if key:
                label.configure(text=f"Game detected: {KNOWN_GAMES[key]} (Clonezilla ISO)")
            else:
                label.configure(text="Unknown ISO (not a recognised PB Clonezilla image)")
            return
        key = detect_game(path)
        if key:
            label.configure(text=f"Game detected: {KNOWN_GAMES[key]}")
        else:
            label.configure(text="Unknown game (not a recognised PB .upd file)")

    def _check_extract_warn(self, *_):
        path = self.extract_output_var.get().strip()
        if path and os.path.isdir(path) and os.listdir(path):
            self._extract_warn.configure(
                text="Output folder is not empty — files may be overwritten.")
        else:
            self._extract_warn.configure(text="")

    def _update_write_filename(self):
        upd = self.write_upd_var.get().strip()
        out = self.write_output_var.get().strip()
        name = os.path.basename(upd) if upd else ""
        if name and out:
            full = out if out.lower().endswith(".upd") else os.path.join(out, name)
            self._write_filename_lbl.configure(text=f"Output: {full}")
        elif name:
            self._write_filename_lbl.configure(text=f"Filename: {name}")
        else:
            self._write_filename_lbl.configure(text="")

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------

    def append_log(self, text, level="info"):
        ts = time.strftime("%H:%M:%S")
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"[{ts}] ", "ts")
        self._log_text.insert(tk.END, text + "\n", level)
        self._log_text.configure(state=tk.DISABLED)
        self._log_text.see(tk.END)

    def append_log_link(self, text, url):
        ts = time.strftime("%H:%M:%S")
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"[{ts}] ", "ts")
        tag = f"link_{id(url)}"
        self._log_text.tag_configure(
            tag, foreground=_THEMES[self._current_theme]["link"], underline=True)
        self._log_text.tag_bind(tag, "<Button-1>",
                                lambda e, u=url: webbrowser.open(u))
        self._log_text.tag_bind(tag, "<Enter>",
                                lambda e: self._log_text.configure(cursor="hand2"))
        self._log_text.tag_bind(tag, "<Leave>",
                                lambda e: self._log_text.configure(cursor=""))
        self._log_text.insert(tk.END, text + "\n", tag)
        self._log_text.configure(state=tk.DISABLED)
        self._log_text.see(tk.END)

    # ------------------------------------------------------------------
    # Phases / progress
    # ------------------------------------------------------------------

    def set_phase(self, index, mode="extract"):
        labels = (self._extract_phase_labels if mode == "extract"
                  else self._write_phase_labels)
        c = _THEMES[self._current_theme]
        for i, lbl in enumerate(labels):
            text = lbl.cget("text") or ""
            name = text.lstrip("○● ").strip()
            if i < index:
                lbl.configure(text=f"● {name}", foreground=c["success"])
            elif i == index:
                lbl.configure(text=f"● {name}", foreground=c["accent"])
            else:
                lbl.configure(text=f"○ {name}", foreground=c["gray"])

    def reset_steps(self, mode="extract"):
        phases = EXTRACT_PHASES if mode == "extract" else WRITE_PHASES
        labels = (self._extract_phase_labels if mode == "extract"
                  else self._write_phase_labels)
        c = _THEMES[self._current_theme]
        for lbl, name in zip(labels, phases):
            lbl.configure(text=f"○ {name}", foreground=c["gray"])
        self._progress_bar["value"] = 0

    def set_progress(self, current, total, desc="", mode="extract"):
        if total > 0:
            self._progress_bar.stop()
            self._progress_bar.configure(mode="determinate")
            self._progress_bar["value"] = int(100 * current / total)
        else:
            self._progress_bar.configure(mode="indeterminate")
            self._progress_bar.start(12)
        if desc:
            self.set_status(desc)

    def set_status(self, text):
        self._status_label.configure(text=text)

    # ------------------------------------------------------------------
    # Running state
    # ------------------------------------------------------------------

    def set_running(self, running, mode="extract"):
        if running:
            self._extract_btn.configure(state=tk.DISABLED)
            self._extract_cancel_btn.configure(state=tk.NORMAL)
            self._write_btn.configure(state=tk.DISABLED)
            self._write_cancel_btn.configure(state=tk.NORMAL)
            self._start_time = time.time()
            self._tick_timer()
        else:
            self._extract_btn.configure(state=tk.NORMAL)
            self._extract_cancel_btn.configure(state=tk.DISABLED)
            self._write_btn.configure(state=tk.NORMAL)
            self._write_cancel_btn.configure(state=tk.DISABLED)
            self._progress_bar.stop()
            self._progress_bar.configure(mode="determinate")
            if self._timer_id:
                self.root.after_cancel(self._timer_id)
                self._timer_id = None
            self._elapsed_label.configure(text="")

    def _tick_timer(self):
        if self._start_time is not None:
            elapsed = int(time.time() - self._start_time)
            m, s = divmod(elapsed, 60)
            self._elapsed_label.configure(text=f"{m:02d}:{s:02d}")
        self._timer_id = self.root.after(1000, self._tick_timer)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _toggle_theme(self):
        new = "light" if self._current_theme == "dark" else "dark"
        self._apply_theme(new)
        if self._on_theme_change:
            self._on_theme_change(new)

    def _apply_theme(self, theme):
        c = _THEMES[theme]
        self._current_theme = theme

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=c["bg"], foreground=c["fg"],
                        fieldbackground=c["field_bg"], bordercolor=c["border"],
                        troughcolor=c["trough"], selectbackground=c["select_bg"],
                        selectforeground="#ffffff", insertcolor=c["fg"])
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        style.configure("TLabelframe", background=c["bg"], foreground=c["fg"])
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
        style.configure("TButton", background=c["button"], foreground=c["fg"])
        style.map("TButton",
                  background=[("active", c["accent"]), ("pressed", c["accent"])],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])
        style.configure("TEntry", fieldbackground=c["field_bg"], foreground=c["fg"])
        style.configure("TNotebook", background=c["bg"], bordercolor=c["border"])
        style.configure("TNotebook.Tab", background=c["button"], foreground=c["fg"],
                        padding=(10, 4))
        style.map("TNotebook.Tab",
                  background=[("selected", c["tab_selected"]),
                              ("active", c["accent"])],
                  foreground=[("selected", c["fg"]), ("active", "#ffffff")])
        style.configure("Horizontal.TProgressbar",
                        troughcolor=c["trough"], background=c["accent"])
        style.configure("TSeparator", background=c["border"])

        self.root.configure(background=c["bg"])
        self._log_text.configure(
            background=c["field_bg"], foreground=c["fg"],
            insertbackground=c["fg"], selectbackground=c["select_bg"])
        self._log_text.tag_configure("info", foreground=c["fg"])
        self._log_text.tag_configure("success", foreground=c["success"])
        self._log_text.tag_configure("error", foreground=c["error"])
        self._log_text.tag_configure("ts", foreground=c["timestamp"])
        self._log_text.tag_configure("link", foreground=c["link"])

        if theme == "dark":
            self._theme_btn.configure(text="☀", style="Sun.TButton")
        else:
            self._theme_btn.configure(text="☽", style="Moon.TButton")
        icon_style = {"background": c["bg"], "borderwidth": 0, "relief": "flat"}
        style.configure("Sun.TButton", font=(_SANS_FONT, 14), padding=(4, 0),
                        foreground="#e6a817", **icon_style)
        style.map("Sun.TButton", background=[("active", c["button"])])
        style.configure("Moon.TButton", font=(_SANS_FONT, 14), padding=(4, 0),
                        foreground="#7b9fd4", **icon_style)
        style.map("Moon.TButton", background=[("active", c["button"])])

        # Windows title bar dark mode
        if sys.platform == "win32":
            try:
                import ctypes
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                value = ctypes.c_int(1 if theme == "dark" else 0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.windll.user32.GetForegroundWindow(),
                    DWMWA_USE_IMMERSIVE_DARK_MODE,
                    ctypes.byref(value),
                    ctypes.sizeof(value))
            except Exception:
                pass
