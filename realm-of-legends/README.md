# Realm of Legends

A **World of Warcraft-inspired** 3D MMORPG prototype built with Three.js. Explore Eldergrove, fight enemies, complete quests, and level up your champion.

![Realm of Legends](https://img.shields.io/badge/Three.js-0.170-blue) ![Vite](https://img.shields.io/badge/Vite-6.0-purple)

## Features

- **Third-person 3D world** — Procedural terrain, trees, rocks, and a starter camp in Eldergrove
- **Three playable classes** — Warrior, Mage, and Hunter with unique abilities and resources
- **Combat system** — Target selection, auto-attack, 4 abilities per class, cooldowns, and damage feedback
- **Enemy AI** — Wolves, bandits, and boars with aggro, leash, and wander behavior
- **Quest system** — Accept quests from NPCs, track progress, and earn XP rewards
- **MMO-style UI** — Player/target frames, action bar, quest tracker, minimap, XP bar, combat log
- **Death & respawn** — Release spirit back at camp when defeated

## Quick Start

```bash
cd realm-of-legends
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

## Controls

| Key / Input | Action |
|-------------|--------|
| **WASD** | Move |
| **Right-click + drag** | Rotate camera |
| **Left-click** | Select enemy target |
| **Tab** | Cycle nearby targets |
| **1–4** | Use abilities |
| **E** | Talk to NPC (when near) |

## Classes

| Class | Resource | Role |
|-------|----------|------|
| **Warrior** | Rage | Melee — Strike, Heroic Strike, Charge, Battle Shout |
| **Mage** | Mana | Ranged caster — Fireball, Frostbolt, Arcane Blast, Heal |
| **Hunter** | Focus | Ranged — Shot, Aimed Shot, Multi-Shot, Disengage |

## Quests

1. **Wolf Hunt** — Kill 3 Forest Wolves (auto-started)
2. **Bandit Menace** — Kill 2 Bandits (requires Wolf Hunt completion)

Talk to **Captain Aldric** at the camp to accept and turn in quests.

## Project Structure

```
realm-of-legends/
├── index.html          # Game shell + HUD markup
├── src/
│   ├── main.js         # Entry point
│   ├── styles/main.css # UI styling
│   └── game/
│       ├── Game.js     # Main game loop & state
│       ├── World.js    # Terrain & environment
│       ├── Entities.js # Player, enemies, NPCs
│       ├── UI.js       # HUD manager
│       ├── Input.js    # Keyboard/mouse input
│       └── constants.js# Classes, enemies, quests
├── package.json
└── vite.config.js
```

## Roadmap Ideas

- Multiplayer networking
- More zones and dungeons
- Inventory and equipment
- Talent trees and specializations
- More classes and races
- Sound and music
- Particle effects for abilities

## Tech Stack

- [Three.js](https://threejs.org/) — 3D rendering
- [Vite](https://vitejs.dev/) — Dev server and bundler

## License

MIT
