import * as THREE from 'three';
import { CLASS_DATA, ENEMY_TYPES } from './constants.js';

export function createCharacterMesh(color, scale = 1) {
  const group = new THREE.Group();

  const bodyGeo = new THREE.CapsuleGeometry(0.35 * scale, 0.8 * scale, 4, 8);
  const bodyMat = new THREE.MeshStandardMaterial({ color });
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  body.position.y = 0.9 * scale;
  body.castShadow = true;
  group.add(body);

  const headGeo = new THREE.SphereGeometry(0.25 * scale, 8, 8);
  const headMat = new THREE.MeshStandardMaterial({ color: '#deb887' });
  const head = new THREE.Mesh(headGeo, headMat);
  head.position.y = 1.6 * scale;
  head.castShadow = true;
  group.add(head);

  return group;
}

export function createEnemyMesh(type) {
  const data = ENEMY_TYPES[type];
  const group = new THREE.Group();
  const scale = data.scale;

  if (type === 'wolf') {
    const bodyGeo = new THREE.CapsuleGeometry(0.3 * scale, 0.6 * scale, 4, 6);
    const bodyMat = new THREE.MeshStandardMaterial({ color: data.color });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.5 * scale;
    body.rotation.z = Math.PI / 2;
    body.castShadow = true;
    group.add(body);

    const headGeo = new THREE.SphereGeometry(0.2 * scale, 6, 6);
    const head = new THREE.Mesh(headGeo, bodyMat);
    head.position.set(0.5 * scale, 0.6 * scale, 0);
    head.castShadow = true;
    group.add(head);

    const earGeo = new THREE.ConeGeometry(0.08 * scale, 0.15 * scale, 4);
    const ear1 = new THREE.Mesh(earGeo, bodyMat);
    ear1.position.set(0.55 * scale, 0.85 * scale, 0.1 * scale);
    group.add(ear1);
    const ear2 = ear1.clone();
    ear2.position.z = -0.1 * scale;
    group.add(ear2);
  } else if (type === 'boar') {
    const bodyGeo = new THREE.CapsuleGeometry(0.35 * scale, 0.5 * scale, 4, 6);
    const bodyMat = new THREE.MeshStandardMaterial({ color: data.color });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.4 * scale;
    body.rotation.z = Math.PI / 2;
    body.castShadow = true;
    group.add(body);

    const headGeo = new THREE.SphereGeometry(0.22 * scale, 6, 6);
    const head = new THREE.Mesh(headGeo, bodyMat);
    head.position.set(0.45 * scale, 0.45 * scale, 0);
    group.add(head);
  } else {
    const bodyGeo = new THREE.CapsuleGeometry(0.35 * scale, 0.8 * scale, 4, 8);
    const bodyMat = new THREE.MeshStandardMaterial({ color: data.color });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.9 * scale;
    body.castShadow = true;
    group.add(body);

    const headGeo = new THREE.SphereGeometry(0.22 * scale, 8, 8);
    const headMat = new THREE.MeshStandardMaterial({ color: '#deb887' });
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.y = 1.55 * scale;
    head.castShadow = true;
    group.add(head);

    const hoodGeo = new THREE.ConeGeometry(0.3 * scale, 0.4 * scale, 6);
    const hoodMat = new THREE.MeshStandardMaterial({ color: '#2f2f2f' });
    const hood = new THREE.Mesh(hoodGeo, hoodMat);
    hood.position.y = 1.7 * scale;
    group.add(hood);
  }

  return group;
}

export function createNPCMesh() {
  const group = new THREE.Group();
  const bodyGeo = new THREE.CapsuleGeometry(0.4, 0.9, 4, 8);
  const bodyMat = new THREE.MeshStandardMaterial({ color: '#4169e1' });
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  body.position.y = 1;
  body.castShadow = true;
  group.add(body);

  const headGeo = new THREE.SphereGeometry(0.28, 8, 8);
  const headMat = new THREE.MeshStandardMaterial({ color: '#deb887' });
  const head = new THREE.Mesh(headGeo, headMat);
  head.position.y = 1.75;
  head.castShadow = true;
  group.add(head);

  const exclamationGeo = new THREE.SphereGeometry(0.15, 8, 8);
  const exclamationMat = new THREE.MeshStandardMaterial({ color: '#ffd700', emissive: '#ffd700', emissiveIntensity: 0.5 });
  const marker = new THREE.Mesh(exclamationGeo, exclamationMat);
  marker.position.y = 2.5;
  group.add(marker);

  return group;
}

export class Player {
  constructor(className, scene, world) {
    this.className = className;
    this.classData = CLASS_DATA[className];
    this.scene = scene;
    this.world = world;

    this.health = this.classData.health;
    this.maxHealth = this.classData.health;
    this.resource = this.classData.resource;
    this.maxResource = this.classData.resource;
    this.level = 1;
    this.xp = 0;
    this.alive = true;

    this.speed = 6;
    this.rotation = 0;
    this.position = new THREE.Vector3(2, 0, 2);

    this.mesh = createCharacterMesh(this.classData.color);
    this.mesh.position.copy(this.position);
    scene.add(this.mesh);

    this.abilities = this.classData.abilities.map(a => ({ ...a, cooldownRemaining: 0 }));
    this.autoAttackTimer = 0;
    this.autoAttackSpeed = 1.5;
    this.buffTimer = 0;
    this.damageMultiplier = 1;

    this._updateHeight();
  }

  _updateHeight() {
    const y = this.world.getHeightAt(this.position.x, this.position.z);
    this.position.y = y;
    this.mesh.position.y = y;
  }

  move(dx, dz, dt) {
    if (!this.alive) return;
    if (dx === 0 && dz === 0) return;

    const angle = Math.atan2(dx, dz);
    this.rotation = angle;
    this.mesh.rotation.y = angle;

    this.position.x += dx * this.speed * dt;
    this.position.z += dz * this.speed * dt;

    const bound = 55;
    this.position.x = Math.max(-bound, Math.min(bound, this.position.x));
    this.position.z = Math.max(-bound, Math.min(bound, this.position.z));

    this._updateHeight();
    this.mesh.position.x = this.position.x;
    this.mesh.position.z = this.position.z;
  }

  turn(delta) {
    this.rotation += delta;
    this.mesh.rotation.y = this.rotation;
  }

  useAbility(index, target, game) {
    if (!this.alive || index < 0 || index >= this.abilities.length) return false;
    const ability = this.abilities[index];
    if (ability.cooldownRemaining > 0) return false;
    if (ability.resourceCost > this.resource) return false;

    if (ability.type === 'heal' || ability.type === 'buff') {
      this.resource -= ability.resourceCost;
      if (ability.heal) {
        this.health = Math.min(this.maxHealth, this.health + ability.heal);
        game.ui.showCombatMessage(`+${ability.heal} healed`, 'heal');
      }
      if (ability.type === 'buff') {
        this.buffTimer = 10;
        this.damageMultiplier = 1.5;
        game.ui.showCombatMessage('Battle Shout! +50% damage', 'info');
      }
      ability.cooldownRemaining = ability.cooldown;
      game.ui.updatePlayerFrame(this);
      return true;
    }

    if (ability.type === 'escape') {
      const backX = -Math.sin(this.rotation) * 5;
      const backZ = -Math.cos(this.rotation) * 5;
      this.position.x += backX;
      this.position.z += backZ;
      this._updateHeight();
      this.mesh.position.x = this.position.x;
      this.mesh.position.z = this.position.z;
      ability.cooldownRemaining = ability.cooldown;
      game.ui.showCombatMessage('Disengaged!', 'info');
      return true;
    }

    if (!target || !target.alive) return false;

    const dist = this.position.distanceTo(target.position);
    if (dist > ability.range) {
      game.ui.showCombatMessage('Out of range!', 'info');
      return false;
    }

    this.resource -= ability.resourceCost;
    ability.cooldownRemaining = ability.cooldown;

    if (ability.type === 'aoe') {
      game.enemies.forEach(e => {
        if (!e.alive) return;
        const d = this.position.distanceTo(e.position);
        if (d <= ability.aoeRadius) {
          const dmg = Math.floor(ability.damage * this.damageMultiplier);
          e.takeDamage(dmg, game);
        }
      });
      game.ui.showCombatMessage(`${ability.name} hits multiple targets!`, 'damage');
    } else if (ability.type === 'charge') {
      const dir = new THREE.Vector3().subVectors(target.position, this.position).normalize();
      this.position.add(dir.multiplyScalar(Math.min(dist - 1, 6)));
      this._updateHeight();
      this.mesh.position.x = this.position.x;
      this.mesh.position.z = this.position.z;
      const dmg = Math.floor(ability.damage * this.damageMultiplier);
      target.takeDamage(dmg, game);
      game.ui.showCombatMessage(`${ability.name}: ${dmg} damage`, 'damage');
    } else {
      const dmg = Math.floor(ability.damage * this.damageMultiplier);
      target.takeDamage(dmg, game);
      game.ui.showCombatMessage(`${ability.name}: ${dmg} damage`, 'damage');
      if (ability.slow) target.slowTimer = 3;
    }

    this.faceTarget(target);
    game.ui.updatePlayerFrame(this);
    game.ui.updateCooldowns(this.abilities);
    return true;
  }

  faceTarget(target) {
    const dx = target.position.x - this.position.x;
    const dz = target.position.z - this.position.z;
    this.rotation = Math.atan2(dx, dz);
    this.mesh.rotation.y = this.rotation;
  }

  autoAttack(target, game) {
    if (!target || !target.alive) return;
    const dist = this.position.distanceTo(target.position);
    const range = this.className === 'hunter' ? 15 : 3;
    if (dist > range) return;

    this.autoAttackTimer -= game.dt;
    if (this.autoAttackTimer > 0) return;
    this.autoAttackTimer = this.autoAttackSpeed;

    const baseDmg = this.className === 'warrior' ? 10 : this.className === 'mage' ? 8 : 12;
    const dmg = Math.floor(baseDmg * this.damageMultiplier);
    target.takeDamage(dmg, game);
    this.faceTarget(target);
    game.ui.showCombatMessage(`Auto-attack: ${dmg}`, 'damage');

    if (this.className === 'warrior') {
      this.resource = Math.min(this.maxResource, this.resource + 5);
      game.ui.updatePlayerFrame(this);
    }
  }

  takeDamage(amount) {
    if (!this.alive) return;
    this.health -= amount;
    if (this.health <= 0) {
      this.health = 0;
      this.alive = false;
    }
  }

  gainXp(amount, game) {
    this.xp += amount;
    game.ui.showCombatMessage(`+${amount} XP`, 'xp');
    const needed = game.getXpNeeded();
    while (this.xp >= needed && this.level < 10) {
      this.xp -= needed;
      this.level++;
      this.maxHealth += 15;
      this.health = this.maxHealth;
      this.maxResource += 10;
      this.resource = this.maxResource;
      game.ui.showCombatMessage(`Level Up! Now level ${this.level}`, 'xp');
    }
    game.ui.updatePlayerFrame(this);
    game.ui.updateXpBar(this, game.getXpNeeded());
  }

  respawn() {
    this.alive = true;
    this.health = this.maxHealth;
    this.resource = this.maxResource;
    this.position.set(2, 0, 2);
    this._updateHeight();
    this.mesh.position.copy(this.position);
  }

  update(dt) {
    if (this.buffTimer > 0) {
      this.buffTimer -= dt;
      if (this.buffTimer <= 0) this.damageMultiplier = 1;
    }

    this.abilities.forEach(a => {
      if (a.cooldownRemaining > 0) a.cooldownRemaining = Math.max(0, a.cooldownRemaining - dt);
    });

    if (this.className === 'warrior' && this.alive) {
      this.resource = Math.max(0, this.resource - 2 * dt);
    } else if (this.className !== 'warrior' && this.alive) {
      this.resource = Math.min(this.maxResource, this.resource + 5 * dt);
    }
  }
}

export class Enemy {
  constructor(type, x, z, scene, world) {
    this.type = type;
    this.data = ENEMY_TYPES[type];
    this.scene = scene;
    this.world = world;

    this.health = this.data.health;
    this.maxHealth = this.data.health;
    this.alive = true;
    this.attackTimer = 0;
    this.slowTimer = 0;
    this.leashOrigin = new THREE.Vector3(x, 0, z);
    this.aggressive = false;
    this.aggroRange = 8;
    this.leashRange = 20;

    this.position = new THREE.Vector3(x, 0, z);
    this.mesh = createEnemyMesh(type);
    this._updateHeight();
    this.mesh.position.copy(this.position);
    scene.add(this.mesh);

    this.mesh.userData.enemy = this;
    this.mesh.traverse(child => { child.userData.enemy = this; });
  }

  _updateHeight() {
    const y = this.world.getHeightAt(this.position.x, this.position.z);
    this.position.y = y;
    this.mesh.position.y = y;
  }

  takeDamage(amount, game) {
    if (!this.alive) return;
    this.health -= amount;
    this.aggressive = true;

    this.mesh.traverse(child => {
      if (child.material) {
        child.material.emissive = new THREE.Color('#ff0000');
        child.material.emissiveIntensity = 0.5;
        setTimeout(() => {
          if (child.material) child.material.emissiveIntensity = 0;
        }, 100);
      }
    });

    if (this.health <= 0) {
      this.health = 0;
      this.die(game);
    }

    if (game.target === this) game.ui.updateTargetFrame(this);
  }

  die(game) {
    this.alive = false;
    this.scene.remove(this.mesh);
    game.onEnemyKilled(this);
    game.ui.showCombatMessage(`${this.data.name} slain! +${this.data.xp} XP`, 'xp');
  }

  update(dt, player, game) {
    if (!this.alive) return;

    const distToPlayer = this.position.distanceTo(player.position);
    const distToLeash = this.position.distanceTo(this.leashOrigin);

    if (distToPlayer <= this.aggroRange) this.aggressive = true;

    if (this.aggressive && player.alive) {
      if (distToLeash > this.leashRange) {
        this.aggressive = false;
        this.health = this.maxHealth;
        this.position.copy(this.leashOrigin);
        this._updateHeight();
        this.mesh.position.copy(this.position);
        return;
      }

      const speed = this.slowTimer > 0 ? this.data.speed * 0.5 : this.data.speed;
      if (this.slowTimer > 0) this.slowTimer -= dt;

      const dir = new THREE.Vector3().subVectors(player.position, this.position).normalize();
      const attackRange = 2;

      if (distToPlayer > attackRange) {
        this.position.x += dir.x * speed * dt;
        this.position.z += dir.z * speed * dt;
        this._updateHeight();
        this.mesh.position.x = this.position.x;
        this.mesh.position.z = this.position.z;
        this.mesh.rotation.y = Math.atan2(dir.x, dir.z);
      } else {
        this.attackTimer -= dt;
        if (this.attackTimer <= 0) {
          this.attackTimer = this.data.attackSpeed;
          player.takeDamage(this.data.damage);
          game.ui.updatePlayerFrame(player);
          game.ui.showCombatMessage(`${this.data.name} hits you for ${this.data.damage}`, 'damage');
          if (!player.alive) game.onPlayerDeath();
        }
      }
    } else if (!this.aggressive) {
      const wanderDist = this.position.distanceTo(this.leashOrigin);
      if (wanderDist > 3) {
        const dir = new THREE.Vector3().subVectors(this.leashOrigin, this.position).normalize();
        this.position.x += dir.x * 1 * dt;
        this.position.z += dir.z * 1 * dt;
        this._updateHeight();
        this.mesh.position.copy(this.position);
      }
    }
  }
}

export class NPC {
  constructor(name, x, z, scene, world) {
    this.name = name;
    this.position = new THREE.Vector3(x, 0, z);
    this.world = world;
    this.mesh = createNPCMesh();
    const y = world.getHeightAt(x, z);
    this.position.y = y;
    this.mesh.position.set(x, y, z);
    scene.add(this.mesh);
    this.mesh.userData.npc = this;
    this.mesh.traverse(child => { child.userData.npc = this; });
  }

  isNear(player, range = 4) {
    return this.position.distanceTo(player.position) <= range;
  }
}
