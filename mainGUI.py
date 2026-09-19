"""
mainGUI.py — CustomTkinter GUI for N8's Shader Cache Cleaner.

    pip install customtkinter

Run:
    python mainGUI.py

Windows only — every cache this tool touches lives at a Windows-specific
path, and Steam auto-detection goes through the Windows registry. See
shader_cache_core.py for the actual discovery/scan/clear logic; this file
is UI only, same split as media_core.py / mainGUI.py in the sibling apps.

Not yet wired up (straightforward to add later, following the same
pattern as the other apps): app icon / __version__.py, the auto-updater,
and the GitHub release checker.
"""

import os
import time
import sys
import queue
import threading
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import filedialog, messagebox

import customtkinter as ctk

import modules.shader_cache_core as core
from modules.platformModules import icon, icon_png, bundle_path, is_dev_build, is_running_from_bundle
from modules.tkModules import watermark_label, apply_emoji, animate_alpha
from __version__ import __version__, __appname__, __author__

from modules.configModule import get_setting, set_setting


def set_icon(root):
    root.iconbitmap(icon)


# icon_img = Image.open(icon_png).convert("RGBA")
# icon_img = icon_img.resize((256, 256), Image.LANCZOS)
# icon_img = icon_img.resize((64, 64), Image.LANCZOS)

# icon_ctkImage = ctk.CTkImage(
#     light_image=icon_img,
#     dark_image=icon_img,
#     size=(64, 64),
# )

APP_NAME = __appname__

ctk.set_appearance_mode(get_setting("appearance_mode", "System"))
theme_path = os.path.join(bundle_path, "theme", "N8VENTURES.json") if bundle_path else "./theme/N8VENTURES.json"
ctk.set_default_color_theme(theme_path)


STATUS_COLOR = {
    "unknown": ("gray50", "gray50"),
    "missing": ("gray50", "gray50"),
    "ok": ("#228b22", "#50fa7b"),
    "locked": ("#a52a2a", "#e05555"),
}
STATUS_LABEL = {
    "unknown": "not scanned",
    "missing": "not present",
    "ok": "ok",
    "locked": "locked",
}

PRESET_BUTTONS = [
    ("Default (no Steam)", "__DEFAULT__"),
    ("All", "__ALL__"),
    ("None", "__NONE__"),
    ("Windows", "WIN"),
    ("AMD", "AMD"),
    ("NVIDIA", "NVIDIA"),
    ("Intel", "INTEL"),
    ("Steam", "STEAM"),
]

# Vendor brand colors for the preset buttons — the three utility actions
# (Default/All/None) deliberately keep the app's own theme color instead
# of a brand color, since they aren't tied to any one vendor.
PRESET_STYLE = {
    "WIN": {"fg_color": "#0078D4", "hover_color": "#005A9E", "text_color": "white"},
    "AMD": {"fg_color": "#ED1C24", "hover_color": "#A31419", "text_color": "white"},
    "NVIDIA": {"fg_color": "#76B900", "hover_color": "#537F00", "text_color": "black"},
    "INTEL": {"fg_color": "#0071C5", "hover_color": "#00457C", "text_color": "white"},
    "STEAM": {"fg_color": "#1B2838", "hover_color": "#0B0F14", "text_color": "white"},
}


# --------------------------------------------------------------------------
# Popups
# --------------------------------------------------------------------------
class ProgressPopup(ctk.CTkToplevel):
    def __init__(self, master, total, title="Working…"):
        super().__init__(master)
        width, height = 420, 150
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - width) // 2, (sh - height) // 2
        self.title(title)
        self.geometry(f"{width}x{height}+{x}+{y - 35}")
        self.update_idletasks()
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # blocking, on purpose — mid-delete isn't cancelable
        self.grab_set()

        self.total = max(total, 1)
        self.label_status = ctk.CTkLabel(self, text=f"0 / {total}", font=("", 14, "bold"))
        self.label_status.pack(pady=(20, 6))
        self.label_detail = ctk.CTkLabel(self, text="", text_color="gray60")
        self.label_detail.pack(pady=(0, 12))
        self.progress = ctk.CTkProgressBar(self, width=340)
        self.progress.set(0)
        self.progress.pack(pady=(0, 10))

    def update_progress(self, index, detail):
        max_length = 45
        if len(detail) > max_length:
            detail = detail[: max_length - 3] + "..."
        self.label_status.configure(text=f"{index} / {self.total}")
        self.label_detail.configure(text=detail)
        self.progress.set(index / self.total)


class ManageSteamPathsPopup(ctk.CTkToplevel):
    def __init__(self, master, on_change):
        super().__init__(master)
        self.on_change = on_change
        width, height = 480, 360
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - width) // 2, (sh - height) // 2
        self.title("Manage Custom Steam Paths")
        self.geometry(f"{width}x{height}+{x}+{y - 35}")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(
            self,
            text="Extra Steam library 'shadercache' folders, for libraries the\n"
            "automatic scan didn't find (e.g. an unusual drive setup).",
            justify="left",
            text_color="gray60",
            wraplength=440,
        ).pack(anchor="w", padx=16, pady=(16, 8))

        self.list_frame = ctk.CTkScrollableFrame(self, height=180)
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=16, pady=(0, 16))
        self.entry = ctk.CTkEntry(add_row, placeholder_text=r"D:\SteamLibrary\steamapps\shadercache")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(add_row, text="Browse…", width=80, command=self._browse).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="Add", width=70, command=self._add).pack(side="left")

        self._refresh()

    def _refresh(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        paths = core.load_custom_steam_paths()
        if not paths:
            ctk.CTkLabel(self.list_frame, text="No custom paths added.", text_color="gray50").pack(anchor="w", pady=4)
        for p in paths:
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=p, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(
                row,
                text="Remove",
                width=70,
                fg_color="#8b2e2e",
                hover_color="#6e2424",
                command=lambda p=p: self._remove(p),
            ).pack(side="right")

    def _browse(self):
        # filedialog opens above the popup fine on its own — no extra
        # topmost/grab handling needed, CTkToplevel's grab_set() already
        # covers it.
        chosen = filedialog.askdirectory(parent=self, title="Select a Steam shadercache folder", mustexist=True)
        if chosen:
            self.entry.delete(0, "end")
            self.entry.insert(0, chosen)

    def _add(self):
        path = self.entry.get().strip()
        if not path:
            return
        core.add_custom_steam_path(path)
        self.entry.delete(0, "end")
        self._refresh()
        self.on_change()

    def _remove(self, path):
        core.remove_custom_steam_path(path)
        self._refresh()
        self.on_change()


# --------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        width, height = 620, 780
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (sw - width) // 2, (sh - height) // 2
        self.title(APP_NAME)
        self.geometry(f"{width}x{height}+{x}+{y - 35}")
        self.minsize(520, 600)
        self.update_idletasks()

        self.entries = []
        self.row_widgets = {}  # id(entry) -> {"size": label, "status": label}
        self.check_vars = {}  # id(entry) -> BooleanVar

        self._build_ui()
        self._reload_entries()
        self.after(100, self.deiconify)

    # ---- UI construction ---------------------------------------------------
    def _build_ui(self):
        self.theme_toggle_btn = ctk.CTkButton(
            self,
            text="",
            width=32,
            height=32,
            corner_radius=6,
            command=self._toggle_appearance,
        )
        apply_emoji(
            self.theme_toggle_btn,
            emoji_char="☀️" if ctk.get_appearance_mode() == "Dark" else "🌑",
            px=15,
        )
        self.theme_toggle_btn.place(relx=1.0, x=-14, y=14, anchor="ne")

        ctk.CTkLabel(self, text=APP_NAME, font=("", 20, "bold")).pack(pady=(18, 4))
        ctk.CTkLabel(
            self,
            text="Clear stale GPU shader caches to fix stutter, glitches, or\ninstability after a driver update.",
            text_color="gray60",
            font=("", 12),
            justify="center",
        ).pack(pady=(0, 10))

        self.admin_row = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        self.admin_row.pack(fill="x", padx=20, pady=(0, 10))
        self.admin_label = ctk.CTkLabel(self.admin_row, text="", font=("", 11))
        self.admin_label.pack(side="left")
        self.admin_btn = ctk.CTkButton(
            self.admin_row, text="Restart as Administrator", width=180, command=self._restart_as_admin
        )
        self._refresh_admin_row()

        # --- Presets — just change checkbox selection, don't clear anything
        # by themselves. Keeps "select" and "delete" as two explicit steps.
        # 3 per row via grid, not one packed row — 8 buttons in a single
        # row only fit at full width, forcing a resize to see the tail end.
        preset_container = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        preset_container.pack(fill="x", padx=20, pady=(0, 8))
        ctk.CTkLabel(preset_container, text="Select:", font=("", 11), text_color="gray55").pack(
            anchor="w", pady=(0, 4)
        )

        preset_grid = ctk.CTkFrame(preset_container, fg_color="transparent", border_width=0)
        preset_grid.pack(fill="x")
        for col in range(3):
            preset_grid.grid_columnconfigure(col, weight=1)
        for i, (label, vendor) in enumerate(PRESET_BUTTONS):
            row, col = divmod(i, 3)
            ctk.CTkButton(
                preset_grid,
                text=label,
                height=26,
                font=("", 11),
                command=lambda v=vendor: self._apply_preset(v),
                **PRESET_STYLE.get(vendor, {}),
            ).grid(row=row, column=col, padx=4, pady=4, sticky="ew")

        # --- Cache list ---
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="Detected caches")
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 6))

        # --- Untracked folders warning (populated after a scan) ---
        self.untracked_frame = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        # not packed until there's something to show — see _refresh_untracked

        self._steam_paths_btn = ctk.CTkButton(
            self,
            text="Manage Custom Steam Paths…",
            width=220,
            height=26,
            font=("", 11),
            command=self._open_manage_steam_paths,
        )
        self._steam_paths_btn.pack(anchor="w", padx=20, pady=(0, 10))
        # --- Actions ---
        action_row = ctk.CTkFrame(self, fg_color="transparent", border_width=0)
        action_row.pack(fill="x", padx=20, pady=(0, 6))
        self.scan_btn = ctk.CTkButton(action_row, text="Scan", height=38, command=self._start_scan)
        self.scan_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.clear_btn = ctk.CTkButton(
            action_row,
            text="Clear Selected",
            height=38,
            font=("", 13, "bold"),
            fg_color="#8b2e2e",
            hover_color="#6e2424",
            command=self._start_clear,
        )
        self.clear_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.status_label = ctk.CTkLabel(self, text="Selected: 0 items", text_color="gray55", font=("", 11))
        self.status_label.pack(pady=(0, 6))

        ctk.CTkLabel(self, text="by N8VENTURES", text_color="gray", font=("", 10)).pack(side="bottom", pady=6)

    def _refresh_admin_row(self):
        if core.is_admin():
            self.admin_label.configure(
                text="Running as Administrator — every cache can be cleared.",
                text_color=("#228b22", "#50fa7b"),
            )
            self.admin_btn.pack_forget()
        else:
            self.admin_label.configure(
                text="Not running as Administrator — some caches may stay locked.",
                text_color=("#a52a2a", "#e05555"),
            )
            self.admin_btn.pack(side="right")

    def _restart_as_admin(self):
        if messagebox.askyesno(
            "Restart as Administrator",
            "This will close the app and reopen it elevated. Continue?",
        ):
            self.destroy()
            core.relaunch_as_admin()

    def _flush_pending_redraws(self, max_wait_ms=250):
        """Pumps the real Tcl event queue (not just idle/geometry tasks)
        until it's actually empty, instead of guessing a fixed number of
        passes. CTk chains some of its per-widget redraw work across
        several after(0, ...) hops rather than finishing it inside one
        synchronous call, so a fixed count of update() calls can
        undercount on a slower machine — that leftover tail is what was
        showing up as widgets catching up one at a time after deiconify
        (the domino effect). `after info` (Tcl) returns every currently
        scheduled after-callback in this interpreter, so checking it
        after each pump tells us definitively when there's nothing left
        queued, rather than hoping N passes was enough. Bounded by
        max_wait_ms so a stray recurring after() (e.g. a scan's poll
        loop) can't hang the toggle indefinitely.
        """
        deadline = time.monotonic() + (max_wait_ms / 1000)
        while time.monotonic() < deadline:
            self.update()
            if not self.tk.call("after", "info"):
                break

    def _toggle_appearance(self):
        new_mode = "Light" if ctk.get_appearance_mode() == "Dark" else "Dark"

        def _swap_and_reveal():
            # Withdraw rather than just staying at alpha=0 — set_appearance_mode
            # below has to restyle every live widget, and that's the actual
            # source of the pause. With the window merely transparent-but-
            # mapped, the OS keeps compositing it the whole time and the
            # stall bleeds into the reveal. Fully withdrawing (same trick
            # __init__ already uses during startup) means there's nothing on
            # screen to composite while the restyle runs.
            self.withdraw()
            ctk.set_appearance_mode(new_mode)
            set_setting("appearance_mode", new_mode)
            apply_emoji(
                self.theme_toggle_btn,
                emoji_char="☀️" if new_mode == "Dark" else "🌑",
                px=15,
            )
            self._flush_pending_redraws()
            self.attributes("-alpha", 0.0)
            self.deiconify()
            animate_alpha(self, 1.0, duration_ms=250)

        animate_alpha(self, 0.0, duration_ms=150, on_complete=_swap_and_reveal)

    # ---- Cache list rendering ------------------------------------------------
    def _reload_entries(self):
        self.entries = core.build_cache_list()
        for widget in self.list_frame.winfo_children():
            widget.destroy()
        self.row_widgets = {}
        self.check_vars = {}

        for vendor in core.VENDORS:
            vendor_entries = [e for e in self.entries if e.vendor == vendor]
            if not vendor_entries:
                continue
            ctk.CTkLabel(
                self.list_frame,
                text=core.VENDOR_LABELS[vendor],
                font=("", 12, "bold"),
                text_color="gray50",
            ).pack(anchor="w", pady=(8, 2))
            for entry in vendor_entries:
                self._add_row(entry)
        self._update_status_label()

    def _add_row(self, entry):
        row = ctk.CTkFrame(self.list_frame, fg_color="transparent", border_width=0)
        row.pack(fill="x", pady=2)

        var = tk.BooleanVar(value=False)
        self.check_vars[id(entry)] = var
        ctk.CTkCheckBox(row, text=entry.name, variable=var, command=self._update_status_label).pack(side="left")

        size_label = ctk.CTkLabel(row, text="—", width=70, text_color="gray55", font=("", 11))
        size_label.pack(side="right", padx=(6, 0))
        status_label = ctk.CTkLabel(row, text=STATUS_LABEL["unknown"], width=80, font=("", 11))
        status_label.pack(side="right")

        self.row_widgets[id(entry)] = {"size": size_label, "status": status_label}

    def _set_row_status(self, entry):
        widgets = self.row_widgets.get(id(entry))
        if not widgets:
            return
        widgets["status"].configure(
            text=STATUS_LABEL.get(entry.status, entry.status),
            text_color=STATUS_COLOR.get(entry.status, ("gray50", "gray50")),
        )
        if entry.size_bytes is not None:
            widgets["size"].configure(text=core.human_size(entry.size_bytes) if entry.size_bytes else "—")

    # ---- Untracked-folder audit ------------------------------------------------
    def _refresh_untracked(self):
        for widget in self.untracked_frame.winfo_children():
            widget.destroy()
        found = core.find_untracked_siblings(self.entries)
        if not found:
            self.untracked_frame.pack_forget()
            return

        ctk.CTkLabel(
            self.untracked_frame,
            text=f"⚠ {len(found)} untracked folder(s) found next to known caches — not cleared by this tool:",
            text_color=("#a56b00", "#e0a838"),
            font=("", 11, "bold"),
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(4, 2))

        # Fixed-height scrollable body — a long list here used to push the
        # window taller with no way back short of a manual resize, since
        # this frame sits below the (already-scrollable) cache list rather
        # than inside it. Capped so it scrolls internally instead.
        body = ctk.CTkScrollableFrame(self.untracked_frame, height=110, fg_color="transparent")
        body.pack(fill="x", expand=False, pady=(0, 4))

        for item in found:
            size_txt = core.human_size(core.folder_size(item.path))
            ctk.CTkLabel(
                body,
                text=f"{item.path}  ({size_txt})",
                text_color="gray55",
                font=("", 10),
                anchor="w",
            ).pack(anchor="w", fill="x")
            core.log_event(f"[UNTRACKED] {item.path} ({size_txt}) - not managed by this app")
        self.untracked_frame.pack(fill="x", padx=20, pady=(0, 10), before=self._steam_paths_btn)

    # ---- Presets ---------------------------------------------------------------
    def _apply_preset(self, vendor):
        for entry in self.entries:
            var = self.check_vars.get(id(entry))
            if var is None:
                continue
            if vendor == "__ALL__":
                var.set(True)
            elif vendor == "__NONE__":
                var.set(False)
            elif vendor == "__DEFAULT__":
                var.set(entry.vendor != "STEAM")
            else:
                var.set(entry.vendor == vendor)
        self._update_status_label()

    def _update_status_label(self):
        selected = [e for e in self.entries if self.check_vars.get(id(e)) and self.check_vars[id(e)].get()]
        known_sizes = [e.size_bytes for e in selected if e.size_bytes is not None]
        if selected and len(known_sizes) == len(selected):
            self.status_label.configure(text=f"Selected: {len(selected)} items — {core.human_size(sum(known_sizes))}")
        elif selected:
            self.status_label.configure(text=f"Selected: {len(selected)} items — scan to see size")
        else:
            self.status_label.configure(text="Selected: 0 items")

    # ---- Steam paths popup ----------------------------------------------------
    def _open_manage_steam_paths(self):
        ManageSteamPathsPopup(self, on_change=self._reload_entries)

    # ---- Scan --------------------------------------------------------------
    def _start_scan(self):
        self.scan_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        popup = ProgressPopup(self, len(self.entries), title="Scanning…")
        q = queue.Queue()

        def worker():
            core.scan_all(self.entries, on_each=lambda e: q.put(("progress", e)))
            q.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_scan_queue(q, popup, 0)

    def _poll_scan_queue(self, q, popup, index):
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "progress":
                    index += 1
                    popup.update_progress(index, payload.name)
                    self._set_row_status(payload)
                elif kind == "done":
                    popup.destroy()
                    self.scan_btn.configure(state="normal")
                    self.clear_btn.configure(state="normal")
                    self._update_status_label()
                    self._refresh_untracked()
                    core.log_event(f"Scan complete - {len(self.entries)} caches checked")
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll_scan_queue, q, popup, index)

    # ---- Clear -------------------------------------------------------------
    def _start_clear(self):
        selected = [e for e in self.entries if self.check_vars.get(id(e)) and self.check_vars[id(e)].get()]
        if not selected:
            messagebox.showinfo(APP_NAME, "Nothing selected — pick a preset or check some caches first.")
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Clear {len(selected)} selected cache folder(s)? Contents will be deleted and the folders "
            "recreated empty. Anything still in use by a driver is skipped, not force-closed.",
        ):
            return

        self.scan_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        popup = ProgressPopup(self, len(selected), title="Clearing…")
        q = queue.Queue()

        def worker():
            total = core.clear_all(selected, on_each=lambda e, freed: q.put(("progress", e, freed)))
            q.put(("done", total))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_clear_queue(q, popup, 0)

    def _poll_clear_queue(self, q, popup, index):
        try:
            while True:
                msg = q.get_nowait()
                if msg[0] == "progress":
                    _, entry, _freed = msg
                    index += 1
                    popup.update_progress(index, entry.name)
                    self._set_row_status(entry)
                elif msg[0] == "done":
                    total = msg[1]
                    popup.destroy()
                    self.scan_btn.configure(state="normal")
                    self.clear_btn.configure(state="normal")
                    self._update_status_label()
                    self._refresh_untracked()
                    core.log_event(f"Clear complete - freed {core.human_size(total)}")
                    messagebox.showinfo(APP_NAME, f"Done — freed {core.human_size(total)}.")
                    return
        except queue.Empty:
            pass
        self.after(80, self._poll_clear_queue, q, popup, index)


def main():
    if sys.platform != "win32":
        import tkinter.messagebox as mb

        mb.showerror(
            APP_NAME,
            f"{APP_NAME} only supports Windows — every cache it manages lives at a "
            "Windows-specific path that doesn't exist on this platform.",
        )
        return
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()