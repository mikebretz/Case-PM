# Sylvorin

**Sylvorin** is a World of Warcraft-inspired 3D MMORPG prototype built with Three.js. Explore Eldergrove, fight enemies, complete quests, and level up your champion.

## Separate from Case PM / KSPM

This is a **completely different program** from Case PM (KSPM). Its own repo, its own install folder (`C:\Sylvorin`), no shared code.

| Program | Repo | Install location |
|---------|------|------------------|
| Case PM (KSPM) | [Case-PM](https://github.com/mikebretz/Case-PM) | Your Case-PM folder |
| **Sylvorin** | [Sylvorin](https://github.com/mikebretz/Sylvorin) | **`C:\Sylvorin`** |

**See [PROJECT-MAP.md](PROJECT-MAP.md) for a full file listing.**

## Quick start (Windows)

### Desktop app (recommended)

1. Clone this repo (or open the `Sylvorin` folder).
2. Double-click **`INSTALL-DESKTOP.bat`** — installs to `C:\Sylvorin` and creates a desktop shortcut.
3. Double-click **`RUN-DESKTOP.bat`** or use the **Sylvorin** desktop shortcut.

If GitHub shows an empty repo, open **`START-HERE.txt`** or run **`PUSH-TO-GITHUB.bat`** to upload files.

### Browser only

1. Run **`INSTALL-PACKAGES.bat`**
2. Run **`RUN-SYLVORIN.bat`**
3. Open http://localhost:5173

## Controls

| Input | Action |
|-------|--------|
| WASD | Move |
| Right-click drag | Rotate camera |
| Left-click | Select enemy |
| Tab | Cycle targets |
| 1–4 | Abilities |
| E | Talk to NPC |

## Classes

- **Warrior** — melee, Rage
- **Mage** — spells, Mana
- **Hunter** — ranged, Focus

## Tech

- Three.js + Vite
- Desktop window: Python + pywebview (WebView2 on Windows)

## Project layout

```
Sylvorin/
├── index.html              Game + HUD
├── package.json            npm config
├── src/main.js             Entry point
├── src/game/               Game logic
├── desktop_launcher.py     Native window
├── desktop_install.py      C:\Sylvorin installer
├── INSTALL-DESKTOP.bat         **Install to C:\Sylvorin (run once)**
├── RUN-DESKTOP.bat             **Play in desktop window**
├── INSTALL-SYLVORIN-DESKTOP.bat  Same as INSTALL-DESKTOP.bat
├── PUSH-TO-GITHUB.bat          Upload to GitHub if repo is empty
├── START-HERE.txt              List of all batch files
└── PROJECT-MAP.md          Full file map
```

## License

MIT
