# Dark Souls Save Backup Tools

A lightweight save backup & restore tool for Dark Souls and Elden Ring — with global hotkeys so you never have to alt-tab out of the game.

## Supported Games

| Game | Save File |
|------|-----------|
| Dark Souls: Remastered | `DRAKS0005.sl2` |
| Dark Souls II | `DS2SOFS0000.sl2` |
| Dark Souls III | `DS30000.sl2` |
| Elden Ring | `ER0000.sl2` |

## Features

- **Global hotkeys (F1 / F2)** — backup and restore without leaving the game
- **No antivirus false positives** — uses the official Windows `RegisterHotKey` API instead of `pynput`
- **Timestamped backups** — each backup is saved with date & time, up to 10 backups per game with auto-cleanup
- **Audio feedback** — hear a sound on success without looking at the screen
- **Portable** — all paths are relative, works on any machine out of the box

## Installation

### Pre-built `.exe` (recommended)

Download the latest `.exe` from the [Releases](../../releases) page and run it. No Python needed.

### From source

```bash
pip install -r requirements.txt
python main.pyw
```

## Usage

1. Run the application
2. Select your game from the dropdown
3. The save path is auto-detected (click **Select Folder** if it differs)
4. Press **F1** to create a backup
5. Press **F2** to restore the latest backup

Backups are stored in a `backups/` folder next to the save file.

## Automated Build & Release (CI/CD)

This project includes a GitHub Actions workflow. When you push a new tag (e.g. `v2.0.0`), it will:

1. Build the project on Windows
2. Package everything into a single `.exe`
3. Publish it as a GitHub Release

```bash
git tag v2.0.0
git push origin v2.0.0
```

## Tech Stack

- Python 3.11+
- tkinter + Pillow (lightweight GUI — no Qt dependency)
- PyInstaller (for `.exe` builds)
- Windows API (`RegisterHotKey` / `WM_HOTKEY`) — no `pynput`

## License

MIT