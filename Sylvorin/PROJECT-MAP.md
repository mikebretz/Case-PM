# Sylvorin — where everything is

**Sylvorin is a separate program from Case PM (KSPM).** It has its own GitHub repo and installs to `C:\Sylvorin` on your PC.

## On your computer

```
C:\Sylvorin\                    ← Installed game (after desktop install)
├── index.html                  ← Game page
├── package.json                ← Node project config
├── src\                        ← All game code
│   ├── main.js                 ← Starts the game
│   ├── styles\main.css         ← HUD / UI styling
│   └── game\
│       ├── Game.js             ← Main loop, input, camera
│       ├── World.js            ← 3D terrain and environment
│       ├── Entities.js         ← Player, enemies, NPCs
│       ├── UI.js               ← Health bar, quests, action bar
│       ├── Input.js            ← Keyboard and mouse
│       └── constants.js        ← Classes, enemies, quests
├── desktop_launcher.py         ← Desktop window (pywebview)
├── desktop_install.py          ← Builds C:\Sylvorin installer
├── RUN-SYLVORIN-DESKTOP.bat    ← Play in desktop window
├── RUN-SYLVORIN.bat            ← Play in browser
└── INSTALL-SYLVORIN-DESKTOP.bat← Copy everything to C:\Sylvorin

Desktop shortcut:  Sylvorin  →  runs C:\Sylvorin\RUN-SYLVORIN-DESKTOP.bat
```

## GitHub repository

**https://github.com/mikebretz/Sylvorin**

Clone it anywhere (not inside Case-PM):

```bat
cd C:\Projects
git clone https://github.com/mikebretz/Sylvorin.git
cd Sylvorin
INSTALL-SYLVORIN-DESKTOP.bat
```

## vs Case PM (KSPM)

| | Case PM / KSPM | Sylvorin |
|---|----------------|----------|
| Folder | Your Case-PM repo | `C:\Sylvorin` or cloned `Sylvorin\` |
| Repo | github.com/mikebretz/Case-PM | github.com/mikebretz/Sylvorin |
| Language | Python / Flask | JavaScript / Three.js |
| Run | RUN-DESKTOP.bat | RUN-SYLVORIN-DESKTOP.bat |

No files are shared between the two programs.

## First-time setup (Windows)

1. Clone **Sylvorin** repo (or open the folder from GitHub Desktop).
2. Double-click **`INSTALL-SYLVORIN-DESKTOP.bat`** — copies to `C:\Sylvorin`, installs npm + Python deps, builds game, creates desktop shortcut.
3. Double-click the **Sylvorin** shortcut on your desktop.

## Play without installing to C:\

From the cloned repo folder:

- **`INSTALL-PACKAGES.bat`** — `npm install` once
- **`RUN-SYLVORIN.bat`** — browser at http://localhost:5173
