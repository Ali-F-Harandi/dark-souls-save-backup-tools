import sys
import os
import shutil
import winsound
import datetime
import ctypes
import ctypes.wintypes

from PyQt5 import uic, QtWidgets
from PyQt5.QtWidgets import QPushButton, QWidget, QApplication, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt

import constant

# ---------------------------------------------------------------------------
# Base directory — works both in dev mode and inside a PyInstaller bundle.
# PyInstaller --onefile extracts resources to sys._MEIPASS at runtime.
# ---------------------------------------------------------------------------
def _get_base_dir():
    """Return the directory that contains bundled resources (ui, sounds, images)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _get_base_dir()

# ---------------------------------------------------------------------------
# Windows API constants & handle  (used for global hotkeys)
# RegisterHotKey is the OFFICIAL Windows API for apps that need hotkeys.
# Antivirus whitelists it because it does NOT hook keyboard input
# (unlike SetWindowsHookEx which pynput uses — that's what triggers detection).
# ---------------------------------------------------------------------------
MOD_NOREPEAT = 0x4000
WM_HOTKEY    = 0x0312
VK_F1        = 0x70
VK_F2        = 0x71
HOTKEY_SAVE  = 1
HOTKEY_LOAD  = 2

user32 = ctypes.windll.user32

# ---------------------------------------------------------------------------
# Global selected-save state
# ---------------------------------------------------------------------------
selectedSaveFile = {
    'path': os.path.join(os.environ['USERPROFILE'], constant.DARK_SOULS_I_DEFAULT_SAVE_PATH),
    'name': constant.DARK_SOULS_I_SAVE_FILE_NAME,
}

BACKUP_DIR_NAME = 'backups'


# ===========================================================================
#  Native-event filter — catches WM_HOTKEY without pynput
# ===========================================================================
class HotkeyFilter(QtWidgets.QAbstractNativeEventFilter):
    """
    Intercepts WM_HOTKEY messages from the Windows message loop.
    Because we use RegisterHotKey (not SetWindowsHookEx), this will NOT
    be flagged by Windows Defender or any other antivirus.
    """

    def __init__(self, app_window):
        super().__init__()
        self.app_window = app_window

    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                if msg.wParam == HOTKEY_SAVE:
                    self.app_window.createSaveBackup(from_hotkey=True)
                elif msg.wParam == HOTKEY_LOAD:
                    self.app_window.loadSaveBackup(from_hotkey=True)
                return True, 0
        return False, 0


# ===========================================================================
#  Main application window
# ===========================================================================
class AppDemo(QWidget):

    # Game list: (display_name, relative_path_key, save_file_name)
    GAMES = [
        ("Dark Souls: Remastered", constant.DARK_SOULS_I_DEFAULT_SAVE_PATH,   constant.DARK_SOULS_I_SAVE_FILE_NAME),
        ("Dark Souls II",         constant.DARK_SOULS_II_DEFAULT_SAVE_PATH,  constant.DARK_SOULS_II_SAVE_FILE_NAME),
        ("Dark Souls III",        constant.DARK_SOULS_III_DEFAULT_SAVE_PATH, constant.DARK_SOULS_III_SAVE_FILE_NAME),
        ("Elden Ring",            constant.ELDEN_RING_DEFAULT_SAVE_PATH,     constant.ELDEN_RING_SAVE_FILE_NAME),
    ]

    # ------------------------------------------------------------------
    def __init__(self):
        super().__init__()

        # Load UI from the SAME directory as the script (portable!)
        ui_path = os.path.join(BASE_DIR, "main.ui")
        uic.loadUi(ui_path, self)

        # Build a lookup of index -> full default save path
        self.savePaths = {}
        for i, (_, rel_path, _) in enumerate(self.GAMES):
            self.savePaths[i] = os.path.join(os.environ["USERPROFILE"], rel_path)

        # Wire up signals
        self.comboBox.currentIndexChanged.connect(self.selectGame)
        self.selectSaveFolderButton.clicked.connect(self.selectPath)
        self.saveButton.clicked.connect(lambda: self.createSaveBackup(from_hotkey=False))
        self.loadButton.clicked.connect(lambda: self.loadSaveBackup(from_hotkey=False))

        # Show the default path
        self.SaveFolderPath.setText(selectedSaveFile["path"])

    # ------------------------------------------------------------------
    #  Game / path selection
    # ------------------------------------------------------------------
    def selectGame(self):
        index = self.comboBox.currentIndex()
        if 0 <= index < len(self.GAMES):
            _, _, filename = self.GAMES[index]
            path = self.savePaths.get(index, self.savePaths[0])
            self._updateSelectedSaveFile(path, filename)
            self.SaveFolderPath.setText(selectedSaveFile["path"])

    def selectPath(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if not directory:
            return

        self.SaveFolderPath.setText(directory)
        index = self.comboBox.currentIndex()

        if 0 <= index < len(self.GAMES):
            _, _, filename = self.GAMES[index]
            self.savePaths[index] = directory
            self._updateSelectedSaveFile(directory, filename)

    @staticmethod
    def _updateSelectedSaveFile(path, name):
        selectedSaveFile["path"] = path
        selectedSaveFile["name"] = name

    # ------------------------------------------------------------------
    #  Backup helpers
    # ------------------------------------------------------------------
    def _backupDir(self):
        return os.path.join(selectedSaveFile["path"], BACKUP_DIR_NAME)

    def _latestBackupPath(self):
        """Return the full path of the most recent backup, or None."""
        bdir = self._backupDir()
        if not os.path.isdir(bdir):
            return None
        backups = sorted(
            (f for f in os.listdir(bdir) if f.startswith("backup_")),
            reverse=True,
        )
        return os.path.join(bdir, backups[0]) if backups else None

    def _playSound(self, filename):
        """Play a .wav sound if the file exists next to the script."""
        path = os.path.join(BASE_DIR, filename)
        if os.path.isfile(path):
            winsound.PlaySound(path, winsound.SND_FILENAME)

    def _setStatus(self, text, success=True):
        color = "#00aa00" if success else "#ff0000"
        self.labelStatus.setText(
            f'<html><head/><body><p>Status: '
            f'<span style="color:{color};">{text}</span>'
            f'</p></body></html>'
        )

    # ------------------------------------------------------------------
    #  Core: Create / Load backup
    # ------------------------------------------------------------------
    def createSaveBackup(self, from_hotkey=False):
        try:
            source = os.path.join(selectedSaveFile["path"], selectedSaveFile["name"])

            if not os.path.isfile(source):
                self._setStatus(f'Save file not found ({selectedSaveFile["name"]})', success=False)
                return

            # Create backup directory if needed
            bdir = self._backupDir()
            os.makedirs(bdir, exist_ok=True)

            # Timestamped filename: backup_2024-01-15_14-30-00_DRAKS0005.sl2
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
            self._setStatus(f"Save backup created. ({count}/{constant.MAX_BACKUPS})")
            self._playSound("save_Backup_Careated.wav")

        except Exception as e:
            self._setStatus(f"Error: {e}", success=False)

    def loadSaveBackup(self, from_hotkey=False):
        try:
            latest = self._latestBackupPath()
            if latest is None:
                self._setStatus("No backup found to load.", success=False)
                return

            dest = os.path.join(selectedSaveFile["path"], selectedSaveFile["name"])
            shutil.copy2(latest, dest)

            self._setStatus(f"Backup loaded. ({os.path.basename(latest)})")
            self._playSound("save_Backup_Loaded.wav")

        except Exception as e:
            self._setStatus(f"Error: {e}", success=False)


# ===========================================================================
#  Entry point
# ===========================================================================
if __name__ == "__main__":

    app = QApplication(sys.argv)

    demo = AppDemo()
    demo.show()

    # --- Register global hotkeys via Windows API (NOT pynput!) ---
    hotkey_filter = HotkeyFilter(demo)
    app.installNativeEventFilter(hotkey_filter)

    if not user32.RegisterHotKey(None, HOTKEY_SAVE, MOD_NOREPEAT, VK_F1):
        print("Warning: Could not register F1 hotkey (may already be in use).")
    if not user32.RegisterHotKey(None, HOTKEY_LOAD, MOD_NOREPEAT, VK_F2):
        print("Warning: Could not register F2 hotkey (may already be in use).")

    exit_code = app.exec()

    # Clean up hotkey registrations before exit
    user32.UnregisterHotKey(None, HOTKEY_SAVE)
    user32.UnregisterHotKey(None, HOTKEY_LOAD)

    sys.exit(exit_code)