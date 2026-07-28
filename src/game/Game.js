import * as THREE from 'three';
import { World } from './World.js';
import { Player, Enemy, NPC } from './Entities.js';
import { InputManager, createRaycaster } from './Input.js';
import { UIManager } from './UI.js';
import { QUESTS, getXpForLevel } from './constants.js';

export class Game {
  constructor(canvas) {
    this.canvas = canvas;
    this.running = false;
    this.dt = 0;
    this.lastTime = 0;
    this.selectedClass = 'warrior';
    this.target = null;
    this.nearbyNPC = null;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
    this.camera.position.set(0, 8, 12);

    this.input = new InputManager(canvas);
    this.ui = new UIManager();
    this.world = null;
    this.player = null;
    this.enemies = [];
    this.npcs = [];
    this.cameraYaw = 0;
    this.cameraPitch = 0.3;
    this.cameraDistance = 12;

    window.addEventListener('resize', () => this.onResize());
    this._setupStartScreen();
  }

  _setupStartScreen() {
    document.querySelectorAll('.class-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.class-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        this.selectedClass = btn.dataset.class;
      });
    });

    document.getElementById('enter-world-btn').addEventListener('click', () => this.startGame());
    document.getElementById('dialog-close').addEventListener('click', () => this.ui.hideQuestDialog());
    document.getElementById('respawn-btn').addEventListener('click', () => this.respawnPlayer());

    document.querySelectorAll('.action-slot').forEach((slot, i) => {
      slot.addEventListener('click', () => {
        if (this.player) this.player.useAbility(i, this.target, this);
      });
    });
  }

  async init() {
    setTimeout(() => this.ui.hideLoading(), 2200);
  }

  startGame() {
    this.world = new World(this.scene);
    this.world.build();

    this.player = new Player(this.selectedClass, this.scene, this.world);

    this.world.spawnPoints.forEach(sp => {
      const enemy = new Enemy(sp.type, sp.x, sp.z, this.scene, this.world);
      this.enemies.push(enemy);
    });

    this.world.npcPositions.forEach(npcData => {
      const npc = new NPC(npcData.name, npcData.x, npcData.z, this.scene, this.world);
      this.npcs.push(npc);
    });

    this.ui.showHUD(this.player);
    this.ui.updateXpBar(this.player, this.getXpNeeded());
    this.ui.addQuest('wolfHunt');

    this.running = true;
    this.lastTime = performance.now();
    this.animate();
  }

  getXpNeeded() {
    return getXpForLevel(this.player.level);
  }

  onEnemyKilled(enemy) {
    if (this.target === enemy) {
      this.target = null;
      this.ui.hideTargetFrame();
    }

    this.player.gainXp(enemy.data.xp, this);

    this.ui.activeQuests.forEach(questId => {
      const quest = QUESTS[questId];
      quest.objectives.forEach((obj, i) => {
        if (obj.type === 'kill' && obj.target === enemy.type) {
          const newCount = Math.min(obj.count, obj.current + 1);
          this.ui.updateQuestProgress(questId, i, newCount);
        }
      });
    });
  }

  onPlayerDeath() {
    this.ui.showDeathScreen();
    this.ui.showCombatMessage('You have been defeated!', 'damage');
  }

  respawnPlayer() {
    this.player.respawn();
    this.ui.hideDeathScreen();
    this.ui.updatePlayerFrame(this.player);
    this.ui.showCombatMessage('You have respawned at camp.', 'heal');
  }

  selectTarget(entity) {
    if (entity && entity.alive) {
      this.target = entity;
      this.ui.updateTargetFrame(entity);
    }
  }

  cycleTarget() {
    const alive = this.enemies.filter(e => e.alive);
    if (alive.length === 0) return;
    if (!this.target || !this.target.alive) {
      this.selectTarget(alive[0]);
      return;
    }
    const idx = alive.indexOf(this.target);
    const next = alive[(idx + 1) % alive.length];
    this.selectTarget(next);
  }

  interactWithNPC() {
    if (!this.nearbyNPC) return;
    const npcQuests = [
      { id: 'wolfHunt' },
      { id: 'banditMenace' },
    ];

    this.ui.showQuestDialog(
      this.nearbyNPC,
      npcQuests,
      (questId) => this.ui.addQuest(questId),
      (questId) => {
        const rewards = this.ui.completeQuest(questId);
        if (rewards) {
          this.player.gainXp(rewards.xp, this);
          this.ui.showCombatMessage(`Quest reward: ${rewards.xp} XP, ${rewards.gold} gold`, 'xp');
        }
      }
    );
  }

  handleInput() {
    if (!this.player?.alive) return;

    const move = this.input.getMovementVector();
    if (move.x !== 0 || move.z !== 0) {
      const camAngle = this.cameraYaw;
      const fwdX = Math.sin(camAngle);
      const fwdZ = Math.cos(camAngle);
      const rightX = Math.sin(camAngle + Math.PI / 2);
      const rightZ = Math.cos(camAngle + Math.PI / 2);
      const dx = fwdX * move.z + rightX * move.x;
      const dz = fwdZ * move.z + rightZ * move.x;
      this.player.move(dx, dz, this.dt);
    }

    if (this.input.isMouseDown(2)) {
      const sensitivity = 0.003;
      this.cameraYaw -= (this.input.mouse.x - (this._lastMouseX || this.input.mouse.x)) * sensitivity;
      this._lastMouseX = this.input.mouse.x;
    } else {
      this._lastMouseX = null;
    }

    if (this.input.isMouseDown(0) && !this._clickHandled) {
      this._handleClick();
      this._clickHandled = true;
    }
    if (!this.input.isMouseDown(0)) this._clickHandled = false;

    if (this.input.isKeyDown('Tab')) {
      if (!this._tabHandled) {
        this.cycleTarget();
        this._tabHandled = true;
      }
    } else {
      this._tabHandled = false;
    }

    for (let i = 0; i < 4; i++) {
      const key = `Digit${i + 1}`;
      if (this.input.isKeyDown(key)) {
        if (!this._abilityKeys[key]) {
          this.player.useAbility(i, this.target, this);
          this._abilityKeys = this._abilityKeys || {};
          this._abilityKeys[key] = true;
        }
      } else if (this._abilityKeys) {
        this._abilityKeys[key] = false;
      }
    }

    if (this.input.isKeyDown('KeyE')) {
      if (!this._eHandled) {
        this.interactWithNPC();
        this._eHandled = true;
      }
    } else {
      this._eHandled = false;
    }

    if (this.target?.alive) {
      this.player.autoAttack(this.target, this);
    }
  }

  _handleClick() {
    const raycaster = createRaycaster(this.camera, this.input.mouse.x, this.input.mouse.y, this.canvas);
    const meshes = [];
    this.enemies.forEach(e => { if (e.alive) meshes.push(e.mesh); });
    const hits = raycaster.intersectObjects(meshes, true);

    if (hits.length > 0) {
      let obj = hits[0].object;
      while (obj && !obj.userData.enemy) obj = obj.parent;
      if (obj?.userData.enemy) {
        this.selectTarget(obj.userData.enemy);
        return;
      }
    }

    if (hits.length === 0) {
      this.target = null;
      this.ui.hideTargetFrame();
    }
  }

  updateCamera() {
    if (!this.player) return;

    const target = this.player.position;
    const x = target.x + Math.sin(this.cameraYaw) * this.cameraDistance;
    const z = target.z + Math.cos(this.cameraYaw) * this.cameraDistance;
    const y = target.y + 6 + Math.sin(this.cameraPitch) * 4;

    this.camera.position.lerp(new THREE.Vector3(x, y, z), 0.1);
    this.camera.lookAt(target.x, target.y + 1.5, target.z);
  }

  updateNPCs() {
    this.nearbyNPC = null;
    this.npcs.forEach(npc => {
      if (npc.isNear(this.player)) {
        this.nearbyNPC = npc;
        this.ui.showInteractPrompt(npc.name);
      }
    });
    if (!this.nearbyNPC) this.ui.hideInteractPrompt();
  }

  update() {
    if (!this.running || !this.player) return;

    this.handleInput();
    this.player.update(this.dt);
    this.enemies.forEach(e => e.update(this.dt, this.player, this));
    this.updateNPCs();
    this.updateCamera();
    this.ui.updateCooldowns(this.player.abilities);
    this.ui.updateMinimap(this.player, this.enemies);
  }

  animate() {
    if (!this.running) return;
    requestAnimationFrame(() => this.animate());

    const now = performance.now();
    this.dt = Math.min((now - this.lastTime) / 1000, 0.05);
    this.lastTime = now;

    this.update();
    this.renderer.render(this.scene, this.camera);
  }

  onResize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }
}
