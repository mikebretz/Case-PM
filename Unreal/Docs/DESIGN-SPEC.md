# Sylvorin Design Spec (from web prototype)

Use this when building Blueprints/C++ in UE5. Values are starting points — tune in editor.

## Zone

- **Eldergrove** — starter forest, camp with tent + inn, NPC Captain Aldric

## Player classes

### Warrior
- Health: 120 | Resource: Rage (100)
- Walk speed: ~600 uu/s (web: 6 m/s)
- Abilities:
  1. Strike — 15 dmg, melee 300 uu, no CD
  2. Heroic Strike — 35 dmg, melee, 3s CD, 15 Rage
  3. Charge — 20 dmg, gap close 800 uu, 8s CD
  4. Battle Shout — +50% damage 10s, heals 30, 15s CD

### Mage
- Health: 80 | Resource: Mana (120)
- Abilities:
  1. Fireball — 25 dmg, 1500 uu, 10 Mana
  2. Frostbolt — 18 dmg + slow, 1500 uu, 2s CD
  3. Arcane Blast — 40 dmg, 1200 uu, 5s CD, 25 Mana
  4. Heal — 50 heal, 10s CD, 30 Mana

### Hunter
- Health: 100 | Resource: Focus (100)
- Abilities:
  1. Shot — 18 dmg, 1800 uu
  2. Aimed Shot — 45 dmg, 2000 uu, 4s CD, 20 Focus
  3. Multi-Shot — 25 dmg AoE 500 uu radius, 6s CD
  4. Disengage — leap back 500 uu, 12s CD

## Enemies

| ID | Name | HP | Dmg | XP | Speed |
|----|------|-----|-----|-----|-------|
| wolf | Forest Wolf | 40 | 8 | 25 | 300 uu/s |
| bandit | Bandit | 55 | 12 | 35 | 250 uu/s |
| boar | Wild Boar | 30 | 6 | 15 | 400 uu/s |

AI: Aggro at 800 uu, leash at 2000 uu from spawn, wander when idle.

## Quests

1. **Wolf Hunt** — Kill 3 wolves. Reward: 100 XP, 10 gold. Giver: Captain Aldric.
2. **Bandit Menace** — Kill 2 bandits. Requires Wolf Hunt. Reward: 150 XP, 25 gold.

## XP per level

100, 250, 500, 800, 1200, 1700, 2300, 3000, 4000 (levels 1–10)

## UE5 mapping

| Web concept | UE5 implementation |
|-------------|-------------------|
| Player | `ASylvorinCharacter` + GAS |
| Abilities | `UGameplayAbility` + `UAbilitySystemComponent` |
| Enemies | `AActor` + `AIController` + BT |
| Quests | `UQuestSubsystem` or Data Assets |
| HUD | UMG widgets |
| Zone | Level `Eldergrove` + World Partition |
