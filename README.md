# Sylvorin

WoW-inspired MMORPG — **Unreal Engine 5** (primary) + web prototype (reference).

**GitHub:** https://github.com/mikebretz/Sylvorin

## Get Sylvorin on your PC (`C:\Sylvorin`)

| Step | File |
|------|------|
| Download (zip, no Git) | `DOWNLOAD-SYLVORIN-FROM-GITHUB.bat` |
| Pull updates (Git) | `PULL-FROM-GITHUB.bat` |
| **One-time publish** to Sylvorin repo | `PUBLISH-SYLVORIN-TO-GITHUB.bat` |

If https://github.com/mikebretz/Sylvorin is still empty, download uses a Case-PM backup branch automatically. Run **PUBLISH-SYLVORIN-TO-GITHUB.bat** once (sign in to GitHub) to fill the Sylvorin repo.

## Develop in UE5

```
C:\Sylvorin\Unreal\Sylvorin.uproject
```

1. Install **Unreal Engine 5.8** (or 5.4+)
2. Double-click **`OPEN-SYLVORIN-PROJECT.bat`**
3. Read **`SETUP-GAME-NOW.txt`** and **`Unreal\Docs\GETTING-STARTED.md`**

Design numbers (classes, enemies, quests): **`Unreal\Docs\DESIGN-SPEC.md`**

## Web prototype (optional)

The Three.js browser build in `src/` is a playable reference — not the main target anymore.

```bat
C:\Sylvorin\RUN-DESKTOP.bat
```
