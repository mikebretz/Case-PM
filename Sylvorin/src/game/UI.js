import { QUESTS } from './constants.js';

export class UIManager {
  constructor() {
    this.elements = {
      loading: document.getElementById('loading-screen'),
      start: document.getElementById('start-screen'),
      hud: document.getElementById('hud'),
      playerHealthFill: document.getElementById('player-health-fill'),
      playerHealthText: document.getElementById('player-health-text'),
      playerResourceFill: document.getElementById('player-resource-fill'),
      playerResourceText: document.getElementById('player-resource-text'),
      playerName: document.getElementById('player-name'),
      playerLevel: document.getElementById('player-level'),
      targetFrame: document.getElementById('target-frame'),
      targetName: document.getElementById('target-name'),
      targetHealthFill: document.getElementById('target-health-fill'),
      targetHealthText: document.getElementById('target-health-text'),
      questList: document.getElementById('quest-list'),
      combatLog: document.getElementById('combat-log'),
      xpFill: document.getElementById('xp-fill'),
      xpText: document.getElementById('xp-text'),
      interactPrompt: document.getElementById('interact-prompt'),
      interactName: document.getElementById('interact-name'),
      questDialog: document.getElementById('quest-dialog'),
      dialogNpcName: document.getElementById('dialog-npc-name'),
      dialogBody: document.getElementById('dialog-body'),
      dialogActions: document.getElementById('dialog-actions'),
      deathScreen: document.getElementById('death-screen'),
      minimapCanvas: document.getElementById('minimap-canvas'),
    };

    this.activeQuests = [];
    this.completedQuests = [];
    this.combatMessages = [];
  }

  hideLoading() {
    this.elements.loading.classList.add('hidden');
    this.elements.start.classList.remove('hidden');
  }

  showHUD(player) {
    this.elements.start.classList.add('hidden');
    this.elements.hud.classList.remove('hidden');
    this.elements.playerName.textContent = player.classData.name;
    this.updatePlayerFrame(player);
  }

  updatePlayerFrame(player) {
    const hpPct = (player.health / player.maxHealth) * 100;
    this.elements.playerHealthFill.style.width = `${hpPct}%`;
    this.elements.playerHealthText.textContent = `${Math.ceil(player.health)} / ${player.maxHealth}`;
    const resPct = (player.resource / player.maxResource) * 100;
    this.elements.playerResourceFill.style.width = `${resPct}%`;
    this.elements.playerResourceText.textContent = `${Math.ceil(player.resource)} / ${player.maxResource}`;
    this.elements.playerLevel.textContent = player.level;
  }

  updateTargetFrame(target) {
    if (!target || !target.alive) {
      this.elements.targetFrame.classList.add('hidden');
      return;
    }
    this.elements.targetFrame.classList.remove('hidden');
    this.elements.targetName.textContent = target.data?.name || target.name || 'Target';
    const hpPct = (target.health / target.maxHealth) * 100;
    this.elements.targetHealthFill.style.width = `${hpPct}%`;
    this.elements.targetHealthText.textContent = `${Math.ceil(target.health)} / ${target.maxHealth}`;
  }

  hideTargetFrame() {
    this.elements.targetFrame.classList.add('hidden');
  }

  updateXpBar(player, xpNeeded) {
    const pct = (player.xp / xpNeeded) * 100;
    this.elements.xpFill.style.width = `${pct}%`;
    this.elements.xpText.textContent = `${player.xp} / ${xpNeeded} XP`;
  }

  updateCooldowns(abilities) {
    const slots = document.querySelectorAll('.action-slot');
    abilities.forEach((ability, i) => {
      const overlay = slots[i]?.querySelector('.cooldown-overlay');
      if (!overlay) return;
      if (ability.cooldownRemaining > 0) {
        overlay.classList.add('active');
        overlay.textContent = Math.ceil(ability.cooldownRemaining);
      } else {
        overlay.classList.remove('active');
      }
    });
  }

  showCombatMessage(text, type = 'info') {
    const msg = document.createElement('div');
    msg.className = `combat-msg combat-${type}`;
    msg.textContent = text;
    this.elements.combatLog.appendChild(msg);
    this.combatMessages.push(msg);
    setTimeout(() => {
      msg.remove();
      this.combatMessages = this.combatMessages.filter(m => m !== msg);
    }, 2000);
  }

  addQuest(questId) {
    if (this.activeQuests.includes(questId)) return;
    const quest = QUESTS[questId];
    if (!quest) return;
    this.activeQuests.push(questId);
    this.renderQuests();
    this.showCombatMessage(`New Quest: ${quest.title}`, 'info');
  }

  updateQuestProgress(questId, objectiveIndex, current) {
    const quest = QUESTS[questId];
    if (!quest) return;
    quest.objectives[objectiveIndex].current = current;
    this.renderQuests();

    const allDone = quest.objectives.every(o => o.current >= o.count);
    if (allDone) {
      this.showCombatMessage(`Quest Complete: ${quest.title}!`, 'xp');
    }
  }

  completeQuest(questId) {
    const quest = QUESTS[questId];
    if (!quest) return;
    this.activeQuests = this.activeQuests.filter(id => id !== questId);
    this.completedQuests.push(questId);
    this.renderQuests();
    return quest.rewards;
  }

  renderQuests() {
    this.elements.questList.innerHTML = '';
    this.activeQuests.forEach(questId => {
      const quest = QUESTS[questId];
      if (!quest) return;
      const div = document.createElement('div');
      div.className = 'quest-item';
      const allDone = quest.objectives.every(o => o.current >= o.count);
      const titleClass = allDone ? 'quest-complete' : 'quest-title';
      let progressHtml = quest.objectives.map(o => {
        const done = o.current >= o.count;
        return `<div class="quest-progress ${done ? 'quest-complete' : ''}">${o.target}: ${o.current}/${o.count}</div>`;
      }).join('');
      div.innerHTML = `<div class="${titleClass}">${quest.title}</div>${progressHtml}`;
      this.elements.questList.appendChild(div);
    });
  }

  showInteractPrompt(npcName) {
    this.elements.interactName.textContent = npcName;
    this.elements.interactPrompt.classList.remove('hidden');
  }

  hideInteractPrompt() {
    this.elements.interactPrompt.classList.add('hidden');
  }

  showQuestDialog(npc, quests, onAccept, onComplete) {
    this.elements.dialogNpcName.textContent = npc.name;
    this.elements.dialogBody.innerHTML = '';
    this.elements.dialogActions.innerHTML = '';

    const available = quests.filter(q => !this.activeQuests.includes(q.id) && !this.completedQuests.includes(q.id));
    const completable = quests.filter(q => {
      if (!this.activeQuests.includes(q.id)) return false;
      const quest = QUESTS[q.id];
      return quest.objectives.every(o => o.current >= o.count);
    });
    const inProgress = quests.filter(q => this.activeQuests.includes(q.id) && !completable.find(c => c.id === q.id));

    if (completable.length > 0) {
      completable.forEach(q => {
        const quest = QUESTS[q.id];
        this.elements.dialogBody.innerHTML += `<p><strong>${quest.title}</strong> — Ready to turn in!<br>Reward: ${quest.rewards.xp} XP</p>`;
        const btn = document.createElement('button');
        btn.className = 'dialog-btn primary';
        btn.textContent = `Complete: ${quest.title}`;
        btn.onclick = () => { onComplete(q.id); this.hideQuestDialog(); };
        this.elements.dialogActions.appendChild(btn);
      });
    }

    if (available.length > 0) {
      available.forEach(q => {
        const quest = QUESTS[q.id];
        if (quest.requires && !this.completedQuests.includes(quest.requires)) return;
        this.elements.dialogBody.innerHTML += `<p><strong>${quest.title}</strong><br>${quest.description}<br><em>Reward: ${quest.rewards.xp} XP</em></p>`;
        const btn = document.createElement('button');
        btn.className = 'dialog-btn primary';
        btn.textContent = `Accept: ${quest.title}`;
        btn.onclick = () => { onAccept(q.id); this.hideQuestDialog(); };
        this.elements.dialogActions.appendChild(btn);
      });
    }

    if (inProgress.length > 0 && completable.length === 0 && available.length === 0) {
      inProgress.forEach(q => {
        const quest = QUESTS[q.id];
        const progress = quest.objectives.map(o => `${o.target}: ${o.current}/${o.count}`).join(', ');
        this.elements.dialogBody.innerHTML += `<p><strong>${quest.title}</strong> — In progress: ${progress}</p>`;
      });
    }

    if (this.elements.dialogBody.innerHTML === '') {
      this.elements.dialogBody.innerHTML = '<p>Greetings, adventurer. Safe travels in Eldergrove.</p>';
    }

    const closeBtn = document.createElement('button');
    closeBtn.className = 'dialog-btn';
    closeBtn.textContent = 'Goodbye';
    closeBtn.onclick = () => this.hideQuestDialog();
    this.elements.dialogActions.appendChild(closeBtn);

    this.elements.questDialog.classList.remove('hidden');
  }

  hideQuestDialog() {
    this.elements.questDialog.classList.add('hidden');
  }

  showDeathScreen() {
    this.elements.deathScreen.classList.remove('hidden');
  }

  hideDeathScreen() {
    this.elements.deathScreen.classList.add('hidden');
  }

  updateMinimap(player, enemies, worldSize = 120) {
    const canvas = this.elements.minimapCanvas;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const scale = w / worldSize;
    const center = worldSize / 2;

    ctx.fillStyle = '#2a4a2a';
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = '#1a3a1a';
    for (let i = 0; i < 20; i++) {
      const tx = (Math.random() * worldSize - center) * scale + w / 2;
      const tz = (Math.random() * worldSize - center) * scale + h / 2;
      ctx.beginPath();
      ctx.arc(tx, tz, 2, 0, Math.PI * 2);
      ctx.fill();
    }

    enemies.forEach(e => {
      if (!e.alive) return;
      const ex = (e.position.x + center) * scale;
      const ez = (e.position.z + center) * scale;
      ctx.fillStyle = '#ff4444';
      ctx.beginPath();
      ctx.arc(ex, ez, 3, 0, Math.PI * 2);
      ctx.fill();
    });

    const px = (player.position.x + center) * scale;
    const pz = (player.position.z + center) * scale;
    ctx.fillStyle = '#44ff44';
    ctx.beginPath();
    ctx.arc(px, pz, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#4a4a6e';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, w / 2 - 1, 0, Math.PI * 2);
    ctx.stroke();
  }
}
