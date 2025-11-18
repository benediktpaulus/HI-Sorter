# HI-Sorter
🚀 HI-Sorter: Blazing-fast photo triage, powered by your intelligence, not AI. 100% local, no cloud.

What it does
- Lets you rapidly sort photos into a year-based folder tree (Parent/YYYY/...).
- Designed for fast manual triage: keyboard-first, local-only, no AI.

How the sorting structure looks
```
ParentFolder/
├─ 2024/
│  ├─ Holiday/
│  └─ Family/
└─ 2025/
   └─ Events/
```

Why it's fast
- Preloads the next images so the UI is instant when you move to the next photo.
- Single-keystroke moves (1–9 and Numpad 1–9) and clickable folder buttons keep you on the keyboard.
- LRU-based hotkey assignment means commonly used folders stay on easy keys.
- Everything runs locally (no uploads), so moves are filesystem operations and are quick.

Quick usage
- Start the app (`main.exe`) or run `python main.py` if running from source.
- Choose an Unsorted folder (source) and a Parent folder (destination library).
- The app shows the current image. Press 1–9 (or click a folder) to move it into the mapped destination.
- Press Delete (Entf) to send an image to the session trash (safe, undoable). Use "Undo Last Move" to restore.
- Destination folders are auto-grouped by year (EXIF DateTimeOriginal, fallback to file modification time).
- Use the theme toggle in the header to switch between light and dark modes at any time.

Where session trash is stored
- Deleted files go to a `trash` folder inside your chosen Parent folder (i.e. `{Parent}\trash`). Restores handle name conflicts by appending "(restored)".

Developer quickstart

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python main.py
```

Files to inspect
- App entry: `main.py`
- HTTP routes / static serving: `server.py`
- JS-exposed API + session logic: `api.py`
- Filesystem and EXIF helpers: `logic.py`
- UI: `templates/index.html` and `static/script.js`, `static/style.css`

Packaging note
- This project has been packaged with PyInstaller in the past. Example command:
  `pyinstaller --onefile --windowed --add-data "templates;templates" --add-data "static;static" main.py`

Closing
- The app is local-only and built for fast manual sorting. It is actively developed and may contain rough edges.

Contributing
Contributions are welcome — small fixes, feature ideas, and bug reports all help.

How to contribute
1. Fork the repository and create a feature branch for your changes.
2. Run and test your changes locally (see Developer quickstart above).
3. Open a pull request with a brief description of the problem and your solution.

Found a bug or want to request a feature?
- Open an issue with reproduction steps and expected behavior. If you can, fix it :D 
