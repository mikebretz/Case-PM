import * as THREE from 'three';

export const CLASS_DATA = {
  warrior: {
    name: 'Warrior',
    health: 120,
    resource: 100,
    resourceName: 'Rage',
    color: '#cd853f',
    abilities: [
      { name: 'Strike', damage: 15, cooldown: 0, resourceCost: 0, range: 3, type: 'melee' },
      { name: 'Heroic Strike', damage: 35, cooldown: 3, resourceCost: 15, range: 3, type: 'melee' },
      { name: 'Charge', damage: 20, cooldown: 8, resourceCost: 0, range: 8, type: 'charge' },
      { name: 'Battle Shout', damage: 0, cooldown: 15, resourceCost: 0, range: 0, type: 'buff', heal: 30 },
    ],
  },
  mage: {
    name: 'Mage',
    health: 80,
    resource: 120,
    resourceName: 'Mana',
    color: '#87ceeb',
    abilities: [
      { name: 'Fireball', damage: 25, cooldown: 0, resourceCost: 10, range: 15, type: 'ranged' },
      { name: 'Frostbolt', damage: 18, cooldown: 2, resourceCost: 8, range: 15, type: 'ranged', slow: true },
      { name: 'Arcane Blast', damage: 40, cooldown: 5, resourceCost: 25, range: 12, type: 'ranged' },
      { name: 'Heal', damage: 0, cooldown: 10, resourceCost: 30, range: 0, type: 'heal', heal: 50 },
    ],
  },
  hunter: {
    name: 'Hunter',
    health: 100,
    resource: 100,
    resourceName: 'Focus',
    color: '#90ee90',
    abilities: [
      { name: 'Shot', damage: 18, cooldown: 0, resourceCost: 0, range: 18, type: 'ranged' },
      { name: 'Aimed Shot', damage: 45, cooldown: 4, resourceCost: 20, range: 20, type: 'ranged' },
      { name: 'Multi-Shot', damage: 25, cooldown: 6, resourceCost: 25, range: 12, type: 'aoe', aoeRadius: 5 },
      { name: 'Disengage', damage: 0, cooldown: 12, resourceCost: 0, range: 0, type: 'escape' },
    ],
  },
};

export const ENEMY_TYPES = {
  wolf: {
    name: 'Forest Wolf',
    health: 40,
    damage: 8,
    xp: 25,
    attackSpeed: 2,
    speed: 3,
    color: '#696969',
    scale: 0.8,
  },
  bandit: {
    name: 'Bandit',
    health: 55,
    damage: 12,
    xp: 35,
    attackSpeed: 1.8,
    speed: 2.5,
    color: '#8b4513',
    scale: 1,
  },
  boar: {
    name: 'Wild Boar',
    health: 30,
    damage: 6,
    xp: 15,
    attackSpeed: 2.5,
    speed: 4,
    color: '#a0522d',
    scale: 0.7,
  },
};

export const QUESTS = {
  wolfHunt: {
    id: 'wolfHunt',
    title: 'Wolf Hunt',
    description: 'The wolves of Eldergrove have become aggressive. Thin their numbers.',
    objectives: [{ type: 'kill', target: 'wolf', count: 3, current: 0 }],
    rewards: { xp: 100, gold: 10 },
    giver: 'Captain Aldric',
  },
  banditMenace: {
    id: 'banditMenace',
    title: 'Bandit Menace',
    description: 'Bandits have been harassing travelers on the forest road. Deal with them.',
    objectives: [{ type: 'kill', target: 'bandit', count: 2, current: 0 }],
    rewards: { xp: 150, gold: 25 },
    giver: 'Captain Aldric',
    requires: 'wolfHunt',
  },
};

export const XP_PER_LEVEL = [0, 100, 250, 500, 800, 1200, 1700, 2300, 3000, 4000];

export function getXpForLevel(level) {
  return XP_PER_LEVEL[level] || level * 500;
}
