/**
 * Case PM — global user profile modal (header avatar) with sign out.
 */
(function (global) {
  'use strict';

  let profileSignatureCtx = null;
  let profileSignatureCanvas = null;

  function getCurrentUser() {
    if (global.CASEPM_CURRENT_USER) return { ...global.CASEPM_CURRENT_USER };
    const body = document.body;
    if (!body) return null;
    const id = body.dataset.currentUserId;
    if (!id) return null;
    const full = body.dataset.currentUser || '';
    const parts = full.trim().split(/\s+/);
    return {
      id: parseInt(id, 10),
      first_name: parts[0] || '',
      last_name: parts.slice(1).join(' ') || '',
      full_name: full,
      email: body.dataset.currentUserEmail || '',
      role: body.dataset.currentUserRole || '',
      company: body.dataset.currentUserCompany || '',
      phone: body.dataset.currentUserPhone || '',
      require_2fa: body.dataset.currentUser2fa === '1',
    };
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }

  function initials(user) {
    const a = (user.first_name || user.full_name || '?')[0] || '?';
    const b = (user.last_name || '')[0] || '';
    return (a + b).toUpperCase();
  }

  function updateCompanyLogo(logoUrl) {
    const wrap = document.getElementById('headerCompanyLogoWrap');
    const img = document.getElementById('headerCompanyLogo');
    const iconWrap = document.getElementById('headerBrandIconWrap');
    if (!wrap || !img || !iconWrap) return;
    const url = (logoUrl || '').trim();
    if (url) {
      img.src = url;
      wrap.classList.remove('hidden');
      iconWrap.classList.add('hidden');
    } else {
      img.removeAttribute('src');
      wrap.classList.add('hidden');
      iconWrap.classList.remove('hidden');
    }
  }

  function closeProfileModal(btn) {
    const dlg = btn?.closest?.('dialog') || document.getElementById('casepmUserProfileModal');
    if (dlg) {
      dlg.close();
      dlg.remove();
    }
  }

  function switchProfileTab(btn, tab) {
    document.querySelectorAll('.casepm-profile-tab').forEach((el) => {
      el.classList.remove('border-b-2', 'border-emerald-500', 'text-white');
      el.classList.add('text-zinc-400');
    });
    btn.classList.add('border-b-2', 'border-emerald-500', 'text-white');
    btn.classList.remove('text-zinc-400');
    document.getElementById('profile-tab-general')?.classList.toggle('hidden', tab !== 'general');
    document.getElementById('profile-tab-signature')?.classList.toggle('hidden', tab !== 'signature');
  }

  function initProfileSignatureCanvas(user) {
    profileSignatureCanvas = document.getElementById('profileSignatureCanvas');
    if (!profileSignatureCanvas) return;
    profileSignatureCtx = profileSignatureCanvas.getContext('2d');
    profileSignatureCtx.strokeStyle = '#111827';
    profileSignatureCtx.lineWidth = 2.5;
    profileSignatureCtx.lineJoin = 'round';
    profileSignatureCtx.lineCap = 'round';

    const loadImage = (src) => {
      if (!src || !profileSignatureCtx) return;
      const img = new Image();
      img.onload = () => {
        profileSignatureCtx.clearRect(0, 0, profileSignatureCanvas.width, profileSignatureCanvas.height);
        profileSignatureCtx.drawImage(img, 0, 0, profileSignatureCanvas.width, profileSignatureCanvas.height);
      };
      img.src = src;
    };

    if (user.signatureDataURL) {
      loadImage(user.signatureDataURL);
    } else if (global.CasePMEsign) {
      global.CasePMEsign.fetchMySignature().then((sig) => {
        if (sig?.image_url) loadImage(sig.image_url);
      }).catch(() => {});
    }

    let drawing = false;
    let lastX = 0;
    let lastY = 0;
    profileSignatureCanvas.onmousedown = (e) => {
      drawing = true;
      const rect = profileSignatureCanvas.getBoundingClientRect();
      lastX = e.clientX - rect.left;
      lastY = e.clientY - rect.top;
    };
    profileSignatureCanvas.onmouseup = () => { drawing = false; };
    profileSignatureCanvas.onmouseout = () => { drawing = false; };
    profileSignatureCanvas.onmousemove = (e) => {
      if (!drawing) return;
      const rect = profileSignatureCanvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      profileSignatureCtx.beginPath();
      profileSignatureCtx.moveTo(lastX, lastY);
      profileSignatureCtx.lineTo(x, y);
      profileSignatureCtx.stroke();
      lastX = x;
      lastY = y;
    };
  }

  function clearProfileSignature() {
    if (profileSignatureCtx && profileSignatureCanvas) {
      profileSignatureCtx.clearRect(0, 0, profileSignatureCanvas.width, profileSignatureCanvas.height);
    }
  }

  async function saveProfileSignature() {
    if (!profileSignatureCanvas) return;
    const dataURL = profileSignatureCanvas.toDataURL('image/png');
    try {
      if (global.CasePMEsign) {
        await global.CasePMEsign.saveMySignature({
          signature_png: dataURL,
          legal_name: `${document.getElementById('profileFirstName')?.value?.trim() || ''} ${document.getElementById('profileLastName')?.value?.trim() || ''}`.trim(),
        });
      }
      const users = JSON.parse(localStorage.getItem('users') || '[]');
      const user = getCurrentUser();
      const local = users.find((u) => u.id == user?.id || u.email === user?.email);
      if (local) {
        local.signatureDataURL = dataURL;
        localStorage.setItem('users', JSON.stringify(users));
      }
      const status = document.getElementById('profileSignatureUploadStatus');
      if (status) status.textContent = 'Signature saved.';
      global.CasePMDialog?.alert('Your signature has been saved.', 'success');
    } catch (err) {
      global.CasePMDialog?.alert(err.message || 'Could not save signature.', 'error');
    }
  }

  function setupProfileSignatureUpload(userId) {
    const input = document.getElementById('profileSignatureUpload');
    const status = document.getElementById('profileSignatureUploadStatus');
    if (!input) return;
    input.onchange = async function () {
      if (!input.files?.length) return;
      const reader = new FileReader();
      reader.onload = async (ev) => {
        const dataURL = ev.target.result;
        try {
          if (global.CasePMEsign) {
            await global.CasePMEsign.saveMySignature({ signature_png: dataURL });
          }
          const users = JSON.parse(localStorage.getItem('users') || '[]');
          const local = users.find((u) => u.id == userId);
          if (local) {
            local.signatureDataURL = dataURL;
            localStorage.setItem('users', JSON.stringify(users));
          }
          if (status) status.textContent = 'Signature image uploaded.';
          if (profileSignatureCtx && profileSignatureCanvas) {
            const img = new Image();
            img.onload = () => {
              profileSignatureCtx.clearRect(0, 0, profileSignatureCanvas.width, profileSignatureCanvas.height);
              profileSignatureCtx.drawImage(img, 0, 0, profileSignatureCanvas.width, profileSignatureCanvas.height);
            };
            img.src = dataURL;
          }
        } catch (err) {
          if (status) status.textContent = err.message || 'Upload failed.';
        }
      };
      reader.readAsDataURL(input.files[0]);
    };
  }

  async function saveSelfProfile(userId, btn) {
    const first = document.getElementById('profileFirstName')?.value?.trim() || '';
    const last = document.getElementById('profileLastName')?.value?.trim() || '';
    const phone = document.getElementById('profilePhone')?.value?.trim() || '';

    try {
      const fd = new FormData();
      fd.append('first_name', first);
      fd.append('last_name', last);
      fd.append('phone', phone);
      const res = await fetch('/profile/update', { method: 'POST', body: fd, credentials: 'same-origin' });
      if (!res.ok && res.status !== 302) throw new Error('Could not save profile');

      const users = JSON.parse(localStorage.getItem('users') || '[]');
      const local = users.find((u) => u.id == userId);
      if (local) {
        local.firstName = first;
        local.lastName = last;
        local.phone = phone;
        local.jobTitle = document.getElementById('profileJobTitle')?.value?.trim() || local.jobTitle;
        localStorage.setItem('users', JSON.stringify(users));
        if (typeof global.renderUsersTable === 'function') global.renderUsersTable();
      }

      if (global.CASEPM_CURRENT_USER) {
        global.CASEPM_CURRENT_USER.first_name = first;
        global.CASEPM_CURRENT_USER.last_name = last;
        global.CASEPM_CURRENT_USER.full_name = `${first} ${last}`.trim();
        global.CASEPM_CURRENT_USER.phone = phone;
      }
      const headerName = document.querySelector('#appHeaderBar .font-medium');
      if (headerName) headerName.textContent = `${first} ${last}`.trim();

      closeProfileModal(btn);
      global.CasePMDialog?.alert('Your profile has been updated.', 'success');
    } catch (err) {
      global.CasePMDialog?.alert(err.message || 'Could not save profile.', 'error');
    }
  }

  function signOut() {
    window.location.href = '/logout';
  }

  function showUserProfileModal() {
    const user = getCurrentUser();
    if (!user) {
      global.CasePMDialog?.alert('No user session found.');
      return;
    }

    document.getElementById('casepmUserProfileModal')?.remove();

    const modal = document.createElement('dialog');
    modal.id = 'casepmUserProfileModal';
    modal.className = 'modal rounded-md p-0 text-white w-full max-w-2xl';
    modal.style.backgroundColor = '#18181b';
    modal.style.border = '1px solid #3f3f46';

    const isAdmin = document.body?.dataset?.isAdmin === '1';

    modal.innerHTML = `
      <div class="p-6">
        <div class="flex justify-between items-center mb-6">
          <div class="flex items-center gap-4">
            <div class="w-14 h-14 bg-emerald-600 rounded-full overflow-hidden border-2 border-zinc-600 flex items-center justify-center text-lg font-bold">
              ${esc(initials(user))}
            </div>
            <div>
              <div class="text-xl font-semibold">${esc(user.full_name || `${user.first_name} ${user.last_name}`.trim())}</div>
              <div class="text-sm text-zinc-400">${esc(user.role)}</div>
            </div>
          </div>
          <button type="button" class="text-zinc-400 hover:text-white" data-profile-close>
            <i class="fa-solid fa-times text-xl"></i>
          </button>
        </div>

        <div class="flex border-b border-zinc-700 mb-6">
          <button type="button" onclick="CasePMUserProfile.switchTab(this, 'general')" class="casepm-profile-tab px-6 py-3 text-sm font-medium border-b-2 border-emerald-500 text-white">General</button>
          <button type="button" onclick="CasePMUserProfile.switchTab(this, 'signature')" class="casepm-profile-tab px-6 py-3 text-sm font-medium text-zinc-400 hover:text-white">Signature</button>
        </div>

        <div id="profile-tab-general">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label class="block text-xs text-zinc-400 mb-1">First Name</label>
              <input type="text" id="profileFirstName" value="${esc(user.first_name)}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm">
            </div>
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Last Name</label>
              <input type="text" id="profileLastName" value="${esc(user.last_name)}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm">
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-zinc-400 mb-1">Email Address</label>
              <input type="email" id="profileEmail" value="${esc(user.email)}" readonly class="w-full bg-zinc-800/60 border border-zinc-700 rounded-md px-4 py-2 text-sm text-zinc-400 cursor-not-allowed">
            </div>
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Phone</label>
              <input type="tel" id="profilePhone" value="${esc(user.phone)}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm">
            </div>
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Role</label>
              <div class="px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-sm text-zinc-300">${esc(user.role)}</div>
            </div>
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Company</label>
              <div class="px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-sm text-zinc-300">${esc(user.company || '—')}</div>
            </div>
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Two-Factor Authentication</label>
              <div class="px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-sm text-zinc-300">${user.require_2fa ? 'Enabled' : 'Disabled'}</div>
            </div>
          </div>
        </div>

        <div id="profile-tab-signature" class="hidden">
          <div class="mb-4">
            <label class="block text-sm mb-2 text-zinc-300">Your Signature</label>
            <div class="border border-zinc-700 rounded-md bg-white p-2 inline-block">
              <canvas id="profileSignatureCanvas" width="520" height="140" class="cursor-crosshair rounded"></canvas>
            </div>
            <div class="flex gap-2 mt-2">
              <button type="button" onclick="CasePMUserProfile.clearSignature()" class="px-4 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 rounded">Clear</button>
              <button type="button" onclick="CasePMUserProfile.saveSignature()" class="px-4 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 rounded">Save Signature</button>
            </div>
          </div>
          <div class="mt-4">
            <label class="block text-sm mb-2 text-zinc-300">Upload Signature Image</label>
            <input type="file" id="profileSignatureUpload" accept="image/*" class="text-sm file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:bg-zinc-700 file:text-white hover:file:bg-zinc-600">
            <div id="profileSignatureUploadStatus" class="text-xs text-emerald-400 mt-1"></div>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3 mt-8 pt-6 border-t border-zinc-700">
          <div class="flex flex-wrap gap-2 text-sm">
            ${isAdmin ? `<a href="/program-settings" class="px-3 py-2 rounded-md bg-zinc-800 hover:bg-zinc-700"><i class="fa-solid fa-cog mr-1"></i> Program Settings</a>` : ''}
            ${isAdmin ? `<a href="/user-management" class="px-3 py-2 rounded-md bg-zinc-800 hover:bg-zinc-700"><i class="fa-solid fa-users mr-1"></i> User Management</a>` : ''}
            <button type="button" onclick="CasePMUserProfile.signOut()" class="px-3 py-2 rounded-md bg-red-950/50 hover:bg-red-950 text-red-400 border border-red-900/50">
              <i class="fa-solid fa-sign-out-alt mr-1"></i> Sign Out
            </button>
          </div>
          <div class="flex gap-3">
            <button type="button" data-profile-close class="px-6 py-2.5 rounded-md bg-zinc-700 hover:bg-zinc-600 text-sm">Close</button>
            <button type="button" onclick="CasePMUserProfile.saveProfile(${user.id}, this)" class="px-8 py-2.5 rounded-md bg-emerald-600 hover:bg-emerald-500 text-sm font-semibold">Save Changes</button>
          </div>
        </div>
      </div>
    `;

    modal.querySelectorAll('[data-profile-close]').forEach((btn) => {
      btn.addEventListener('click', () => closeProfileModal(btn));
    });

    document.body.appendChild(modal);
    modal.showModal();

    setTimeout(() => {
      initProfileSignatureCanvas(user);
      setupProfileSignatureUpload(user.id);
    }, 150);
  }

  global.CasePMUserProfile = {
    show: showUserProfileModal,
    switchTab: switchProfileTab,
    clearSignature: clearProfileSignature,
    saveSignature: saveProfileSignature,
    saveProfile: saveSelfProfile,
    signOut,
    updateCompanyLogo,
  };
  global.showUserProfileModal = showUserProfileModal;
})(window);
