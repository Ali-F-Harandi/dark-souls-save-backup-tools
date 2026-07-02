import sys
import os
import shutil
import winsound
import datetime
import ctypes
import ctypes.wintypes
import threading

from tkinter import Tk, Label, Button, StringVar, Frame, filedialog, ttk
from PIL import Image, ImageTk

import constant

# ---------------------------------------------------------------------------
# Base directory — works both in dev mode and inside a PyInstaller bundle.
# ---------------------------------------------------------------------------
def _get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _get_base_dir()

# ---------------------------------------------------------------------------
# Windows API — global hotkeys via RegisterHotKey (no pynput, no antivirus)
# ---------------------------------------------------------------------------
MOD_NOREPEAT = 0x4000
WM_HOTKEY    = 0x0312
VK_F1        = 0x70
VK_F2        = 0x71
HOTKEY_SAVE  = 1
HOTKEY_LOAD  = 2

user32 = ctypes.windll.user32

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
selectedSaveFile = {
    'path': os.path.join(os.environ['USERPROFILE'], constant.DARK_SOULS_I_DEFAULT_SAVE_PATH),
    'name': constant.DARK_SOULS_I_SAVE_FILE_NAME,
}
BACKUP_DIR_NAME = 'backups'

# Colors (Dark Souls theme)
BG_COLOR     = "#1a1a1a"
BG_DARK      = "#111111"
FG_COLOR     = "#c8a45c"
FG_DIM       = "#888888"
BTN_BG       = "#2a2a2a"
BTN_ACTIVE   = "#3a3a3a"
GREEN        = "#00aa00"
RED          = "#ff0000"


# ===========================================================================
#  Hotkey thread — runs its own message loop in the background
# ===========================================================================
def _hotkey_thread(root, app):
    """
    Register hotkeys in THIS thread's message queue, then pump messages.
    When WM_HOTKEY arrives, schedule the action on the tkinter main thread
    via root.after() (thread-safe).
    """
    user32.RegisterHotKey(None, HOTKEY_SAVE, MOD_NOREPEAT, VK_F1)
    user32.RegisterHotKey(None, HOTKEY_LOAD, MOD_NOREPEAT, VK_F2)

    msg = ctypes.wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
        if msg.message == WM_HOTKEY:
            if msg.wParam == HOTKEY_SAVE:
                root.after(0, app.createSaveBackup)
            elif msg.wParam == HOTKEY_LOAD:
                root.after(0, app.loadSaveBackup)


# ===========================================================================
#  Main application
# ===========================================================================
class App:
    GAMES = [
        ("Dark Souls: Remastered", constant.DARK_SOULS_I_DEFAULT_SAVE_PATH,   constant.DARK_SOULS_I_SAVE_FILE_NAME),
        ("Dark Souls II",         constant.DARK_SOULS_II_DEFAULT_SAVE_PATH,  constant.DARK_SOULS_II_SAVE_FILE_NAME),
        ("Dark Souls III",        constant.DARK_SOULS_III_DEFAULT_SAVE_PATH, constant.DARK_SOULS_III_SAVE_FILE_NAME),
        ("Elden Ring",            constant.ELDEN_RING_DEFAULT_SAVE_PATH,     constant.ELDEN_RING_SAVE_FILE_NAME),
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("Dark Souls Save Backup Tools")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # Window icon
        ico_path = os.path.join(BASE_DIR, "Dark_sign.ico")
        if os.path.isfile(ico_path):
            self.root.iconbitmap(ico_path)

        # --- Build default save paths per game ---
        self.savePaths = {}
        for i, (_, rel_path, _) in enumerate(self.GAMES):
            self.savePaths[i] = os.path.join(os.environ["USERPROFILE"], rel_path)

        # --- GUI variables ---
        self.game_var = StringVar(value=self.GAMES[0][0])
        self.path_var = StringVar(value=selectedSaveFile["path"])
        self.status_var = StringVar(value="")

        self._build_ui()
        self.game_var.trace_add("write", lambda *_: self._on_game_change())

    # ------------------------------------------------------------------
    #  Build UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        W = 340
        # ---- Logo ----
        logo_path = os.path.join(BASE_DIR, "Dark_Souls_Logo.jpg")
        if os.path.isfile(logo_path):
            img = Image.open(logo_path)
            img = img.resize((W, 151), Image.LANCZOS)
            self._logo_tk = ImageTk.PhotoImage(img)
            Label(self.root, image=self._logo_tk, bg=BG_COLOR).pack(padx=0, pady=0)

        # ---- Game selector row ----
        row1 = Frame(self.root, bg=BG_COLOR)
        row1.pack(fill="x", padx=10, pady=(10, 0))
        Label(row1, text="Select Your Game :", font=("Segoe UI", 9, "bold"),
              bg=BG_COLOR, fg=FG_COLOR).pack(side="left")
        combo = ttk.Combobox(row1, textvariable=self.game_var,
                             values=[g[0] for g in self.GAMES],
                             state="readonly", width=20)
        combo.pack(side="right")
        combo.current(0)

        # ---- Save folder path row ----
        row2 = Frame(self.root, bg=BG_COLOR)
        row2.pack(fill="x", padx=10, pady=(10, 0))
        Label(row2, text="Save Folder Path :", font=("Segoe UI", 9, "bold"),
              bg=BG_COLOR, fg=FG_COLOR).pack(side="left")
        Button(row2, text="Select Folder", font=("Segoe UI", 8),
               bg=BTN_BG, fg=FG_COLOR, activebackground=BTN_ACTIVE,
               relief="flat", cursor="hand2",
               command=self._select_path).pack(side="right")

        # ---- Path display ----
        path_entry = Frame(self.root, bg=BG_DARK, bd=1, relief="sunken")
        path_entry.pack(fill="x", padx=10, pady=(4, 0))
        Label(path_entry, textvariable=self.path_var, font=("Consolas", 8),
              bg=BG_DARK, fg=FG_DIM, anchor="w").pack(fill="x", padx=4, pady=2)

        # ---- Buttons ----
        btn_row = Frame(self.root, bg=BG_COLOR)
        btn_row.pack(fill="x", padx=10, pady=(15, 0))

        btn_style = dict(font=("Segoe UI", 10, "bold"), width=14, height=2,
                         bg=BTN_BG, fg=FG_COLOR, activebackground=BTN_ACTIVE,
                         activeforeground=FG_COLOR, relief="flat", cursor="hand2")

        Button(btn_row, text="Save  (F1)", command=self.createSaveBackup,
               **btn_style).pack(side="left", padx=(0, 5))
        Button(btn_row, text="Load  (F2)", command=self.loadSaveBackup,
               **btn_style).pack(side="right", padx=(5, 0))

        # ---- Status bar ----
        self.status_label = Label(self.root, textvariable=self.status_var,
                                  font=("Segoe UI", 9), bg=BG_COLOR, fg=GREEN,
                                  anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=(10, 8))

    # ------------------------------------------------------------------
    #  Game / path selection
    # ------------------------------------------------------------------
    def _on_game_change(self):
        name = self.game_var.get()
        for i, (gname, _, filename) in enumerate(self.GAMES):
            if gname == name:
                path = self.savePaths.get(i, self.savePaths[0])
                self._update_selected(path, filename)
                self.path_var.set(selectedSaveFile["path"])
                break

    def _select_path(self):
        directory = filedialog.askdirectory(title="Select Directory")
        if not directory:
            return
        self.path_var.set(directory)

        name = self.game_var.get()
        for i, (gname, _, filename) in enumerate(self.GAMES):
            if gname == name:
                self.savePaths[i] = directory
                self._update_selected(directory, filename)
                break

    @staticmethod
    def _update_selected(path, name):
        selectedSaveFile["path"] = path
        selectedSaveFile["name"] = name

    # ------------------------------------------------------------------
    #  Backup helpers
    # ------------------------------------------------------------------
    def _backup_dir(self):
        return os.path.join(selectedSaveFile["path"], BACKUP_DIR_NAME)

    def _latest_backup(self):
        bdir = self._backup_dir()
        if not os.path.isdir(bdir):
            return None
        backups = sorted(
            (f for f in os.listdir(bdir) if f.startswith("backup_")),
            reverse=True,
        )
        return os.path.join(bdir, backups[0]) if backups else None

    def _play_sound(self, filename):
        path = os.path.join(BASE_DIR, filename)
        if os.path.isfile(path):
            winsound.PlaySound(path, winsound.SND_FILENAME)

    def _set_status(self, text, success=True):
        self.status_label.configure(fg=GREEN if success else RED)
        self.status_var.set(f"Status: {text}")

    # ------------------------------------------------------------------
    #  Core: Create / Load backup
    # ------------------------------------------------------------------
    def createSaveBackup(self):
        try:
            source = os.path.join(selectedSaveFile["path"], selectedSaveFile["name"])
            if not os.path.isfile(source):
                self._set_status(f'Save file not found ({selectedSaveFile["name"]})', False)
                return

            bdir = self._backup_dir()
            os.makedirs(bdir, exist_ok=True)

            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_name = f"backup_{ts}_{selectedSaveFile['name']}"
            dest = os.path.join(bdir, backup_name)
            shutil.copy2(source, dest)

            # Remove oldest backups when we exceed the limit
            all_backups = sorted(
                (f for f in os.listdir(bdir) if f.startswith("backup_")),
                reverse=True,
            )
            for old in all_backups[constant.MAX_BACKUPS:]:
                os.remove(os.path.join(bdir, old))

            count = min(len(all_backups), constant.MAX_BACKUPS)
            self._set_status(f"Save backup created. ({count}/{constant.MAX_BACKUPS})")
            self._play_sound("save_Backup_Careated.wav")

        except Exception as e:
            self._set_status(f"Error: {e}", False)

    def loadSaveBackup(self):
        try:
            latest = self._latest_backup()
            if latest is None:
                self._set_status("No backup found to load.", False)
                return

            dest = os.path.join(selectedSaveFile["path"], selectedSaveFile["name"])
            shutil.copy2(latest, dest)

            self._set_status(f"Backup loaded. ({os.path.basename(latest)})")
            self._play_sound("save_Backup_Loaded.wav")

        except Exception as e:
            self._set_status(f"Error: {e}", False)


# ===========================================================================
#  Entry point
# ===========================================================================
if __name__ == "__main__":

    root = Tk()
    app = App(root)

    # Start hotkey listener in a background thread
    t = threading.Thread(target=_hotkey_thread, args=(root, app), daemon=True)
    t.start()

    root.mainloop()

    # Cleanup
    user32.UnregisterHotKey(None, HOTKEY_SAVE)
    user32.UnregisterHotKey(None, HOTKEY_LOAD)