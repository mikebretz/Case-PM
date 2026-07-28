# Sylvorin UE5 — Getting Started

Develop Sylvorin in **Unreal Engine 5** at:

```
C:\Sylvorin\Unreal\
```

The browser prototype (`src/game/`) is design reference only.

## Requirements

- **Unreal Engine 5.4+** (Epic Games Launcher)
- **Visual Studio 2022** with "Game development with C++" workload
- ~50 GB disk for engine + project

## Open the project

1. Double-click **`C:\Sylvorin\Unreal\OPEN-IN-UE5.bat`**
   OR Epic Launcher → Library → Add → browse to `C:\Sylvorin\Unreal\Sylvorin.uproject`
2. First open: allow **Rebuild** when prompted (compiles C++).
3. Press **Play** to test third-person movement (WASD, Space jump).

If your engine version differs, right-click `Sylvorin.uproject` → **Switch Unreal Engine version**.

## Recommended next steps in the editor

### 1. Add Third Person content (fastest visual start)

- **Add** → **Feature or Content Pack** → **Third Person**
- Or migrate from Epic's Third Person template project

### 2. Create Eldergrove map

- **File → New Level → Open World**
- Save as `Content/Maps/Eldergrove`
- Set in **Project Settings → Maps & Modes**

### 3. Combat — Gameplay Ability System (GAS)

The project enables the **GameplayAbilities** plugin.

- Create `AttributeSet` (Health, Rage/Mana/Focus)
- Create `GameplayAbility` subclasses for each class ability
- See `DESIGN-SPEC.md` for ability numbers from the web prototype

### 4. Classes (from web prototype)

| Class | Resource | Abilities |
|-------|----------|-----------|
| Warrior | Rage | Strike, Heroic Strike, Charge, Battle Shout |
| Mage | Mana | Fireball, Frostbolt, Arcane Blast, Heal |
| Hunter | Focus | Shot, Aimed Shot, Multi-Shot, Disengage |

### 5. Enemies & AI

- **Wolf**, **Bandit**, **Boar** — use `AIController` + Behavior Tree
- Aggro range 800 uu, leash 2000 uu (see web `Entities.js`)

### 6. Quests

- `DESIGN-SPEC.md` lists Wolf Hunt and Bandit Menace objectives
- Implement with `UQuestSubsystem` or simple Blueprint quest component

## Folder layout

```
C:\Sylvorin\
  Unreal\                    ← UE5 project (develop here)
    Sylvorin.uproject
    Source\Sylvorin\          C++ game code
    Content\                  Assets (Blueprints, maps, meshes)
    Config\
    Docs\
  src\game\                   Web prototype (reference)
```

## Multiplayer (later)

- Use **Dedicated Server** + replication on `ASylvorinCharacter`
- GAS replicates well for MMO-style combat
- Consider **Iris** replication for UE 5.4+

## Useful Epic docs

- [Third Person Template](https://docs.unrealengine.com/5.4/en-US/third-person-template-in-unreal-engine/)
- [Gameplay Ability System](https://docs.unrealengine.com/5.4/en-US/gameplay-ability-system-for-unreal-engine/)
