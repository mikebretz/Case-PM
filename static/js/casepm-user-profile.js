/**
 * Case PM — global user profile modal (header avatar).
 */
(function (global) {
  'use strict';

  let profileSignatureCtx = null;
  let profileSignatureCanvas = null;
  let profilePhotoDataUrl = null;

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
      job_title: body.dataset.currentUserJobTitle || '',
      address: body.dataset.currentUserAddress || '',
      profile_image_url: body.dataset.currentUserPhoto || '',
      require_2fa: body.dataset.currentUser2fa === '1',
      signature_legal_name: '',
      signature_initials: '',
      certificate_file_name: '',
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

  function avatarHtml(user, sizeClass) {
    const cls = sizeClass || 'w-14 h-14';
    const url = profilePhotoDataUrl || user.profile_image_url;
    if (url) {
      return `<img src="${esc(url)}" alt="" class="${cls} rounded-full object-cover border-2 border-zinc-600">`;
    }
    return `<div class="${cls} bg-emerald-600 rounded-full border-2 border-zinc-600 flex items-center justify-center text-lg font-bold">${esc(initials(user))}</div>`;
  }

  function updateHeaderAvatar(url) {
    const headerImg = document.querySelector('#appHeaderBar .w-8.h-8 img');
    const headerWrap = document.querySelector('#appHeaderBar .w-8.h-8');
    if (!headerWrap) return;
    if (url) {
      if (headerImg) {
        headerImg.src = url;
      } else {
        headerWrap.innerHTML = `<img src="${esc(url)}" class="w-full h-full object-cover" alt="">`;
      }
    }
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
    profilePhotoDataUrl = null;
  }

  function switchProfileTab(btn, tab) {
    document.querySelectorAll('.casepm-profile-tab').forEach((el) => {
      el.classList.remove('border-b-2', 'border-emerald-500', 'text-white');
      el.classList.add('text-zinc-400');
    });
    btn.classList.add('border-b-2', 'border-emerald-500', 'text-white');
    btn.classList.remove('text-zinc-400');
    ['general', 'signature', 'certificate'].forEach((t) => {
      document.getElementById(`profile-tab-${t}`)?.classList.toggle('hidden', tab !== t);
    });
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

    if (user.signature?.image_url) loadImage(user.signature.image_url);
    else if (global.CasePMEsign) {
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
          legal_name: document.getElementById('profileLegalName')?.value?.trim()
            || `${document.getElementById('profileFirstName')?.value?.trim() || ''} ${document.getElementById('profileLastName')?.value?.trim() || ''}`.trim(),
          initials: document.getElementById('profileInitials')?.value?.trim() || '',
        });
      }
      document.getElementById('profileSignatureUploadStatus').textContent = 'Signature saved.';
      global.CasePMDialog?.alert('Your signature has been saved.', 'success');
    } catch (err) {
      global.CasePMDialog?.alert(err.message || 'Could not save signature.', 'error');
    }
  }

  function setupProfileSignatureUpload() {
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
            await global.CasePMEsign.saveMySignature({
              signature_png: dataURL,
              legal_name: document.getElementById('profileLegalName')?.value?.trim() || '',
              initials: document.getElementById('profileInitials')?.value?.trim() || '',
            });
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

  function setupProfilePhotoUpload() {
    const input = document.getElementById('profilePhotoUpload');
    const preview = document.getElementById('profilePhotoPreview');
    if (!input || !preview) return;
    input.onchange = () => {
      if (!input.files?.length) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        profilePhotoDataUrl = ev.target.result;
        preview.innerHTML = `<img src="${profilePhotoDataUrl}" class="w-20 h-20 rounded-full object-cover border-2 border-zinc-600" alt="">`;
      };
      reader.readAsDataURL(input.files[0]);
    };
  }

  async function uploadProfilePhotoIfNeeded() {
    const input = document.getElementById('profilePhotoUpload');
    if (!input?.files?.length) return null;
    const fd = new FormData();
    fd.append('photo', input.files[0]);
    const res = await fetch('/api/profile/me/photo', { method: 'POST', body: fd, credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not upload profile photo');
    return json.profile;
  }

  async function saveSelfProfile(userId, btn) {
    const first = document.getElementById('profileFirstName')?.value?.trim() || '';
    const last = document.getElementById('profileLastName')?.value?.trim() || '';
    const phone = document.getElementById('profilePhone')?.value?.trim() || '';
    const jobTitle = document.getElementById('profileJobTitle')?.value?.trim() || '';
    const address = document.getElementById('profileAddress')?.value?.trim() || '';

    try {
      let profile = await uploadProfilePhotoIfNeeded();
      const res = await fetch('/api/profile/me', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: first,
          last_name: last,
          phone,
          job_title: jobTitle,
          address,
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || 'Could not save profile');
      profile = profile || json.profile;

      if (global.CASEPM_CURRENT_USER && profile) {
        Object.assign(global.CASEPM_CURRENT_USER, profile);
      }
      if (profile?.profile_image_url) {
        updateHeaderAvatar(profile.profile_image_url);
        document.body.dataset.currentUserPhoto = profile.profile_image_url;
      }
      const headerName = document.querySelector('#appHeaderBar .font-medium');
      if (headerName) headerName.textContent = `${first} ${last}`.trim();
      document.body.dataset.currentUser = `${first} ${last}`.trim();
      document.body.dataset.currentUserPhone = phone;
      document.body.dataset.currentUserJobTitle = jobTitle;
      document.body.dataset.currentUserAddress = address;

      closeProfileModal(btn);
      global.CasePMDialog?.alert('Your profile has been updated.', 'success');
    } catch (err) {
      global.CasePMDialog?.alert(err.message || 'Could not save profile.', 'error');
    }
  }

  function signOut() {
    window.location.href = '/logout';
  }

  async function showUserProfileModal() {
    let user = getCurrentUser();
    if (!user) {
      global.CasePMDialog?.alert('No user session found.');
      return;
    }

    try {
      const res = await fetch('/api/profile/me', { credentials: 'same-origin' });
      const json = await res.json().catch(() => ({}));
      if (res.ok && json.profile) user = { ...user, ...json.profile };
    } catch (_) { /* use cached user */ }

    document.getElementById('casepmUserProfileModal')?.remove();

    const modal = document.createElement('dialog');
    modal.id = 'casepmUserProfileModal';
    modal.className = 'modal rounded-md p-0 text-white w-full max-w-2xl';
    modal.style.backgroundColor = '#18181b';
    modal.style.border = '1px solid #3f3f46';

    const isDeveloper = document.body?.dataset?.isDeveloper === '1';

    modal.innerHTML = `
      <div class="p-6 max-h-[90vh] overflow-y-auto">
        <div class="flex justify-between items-start mb-6 gap-4">
          <div class="flex items-center gap-4 min-w-0">
            <div id="profilePhotoPreview">${avatarHtml(user)}</div>
            <div class="min-w-0">
              <div class="text-xl font-semibold truncate">${esc(user.full_name || `${user.first_name} ${user.last_name}`.trim())}</div>
              <div class="text-sm text-zinc-400">${esc(user.role)}</div>
              <div class="text-xs text-zinc-500 truncate">${esc(user.email)}</div>
            </div>
          </div>
          <button type="button" class="text-zinc-400 hover:text-white shrink-0" data-profile-close>
            <i class="fa-solid fa-times text-xl"></i>
          </button>
        </div>

        <div class="mb-4">
          <label class="block text-xs text-zinc-400 mb-1">Profile photo</label>
          <input type="file" id="profilePhotoUpload" accept="image/*" class="text-sm file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:bg-zinc-700 file:text-white hover:file:bg-zinc-600">
        </div>

        <div class="flex border-b border-zinc-700 mb-6">
          <button type="button" onclick="CasePMUserProfile.switchTab(this, 'general')" class="casepm-profile-tab px-5 py-3 text-sm font-medium border-b-2 border-emerald-500 text-white">General</button>
          <button type="button" onclick="CasePMUserProfile.switchTab(this, 'signature')" class="casepm-profile-tab px-5 py-3 text-sm font-medium text-zinc-400 hover:text-white">Signature</button>
          <button type="button" onclick="CasePMUserProfile.switchTab(this, 'certificate')" class="casepm-profile-tab px-5 py-3 text-sm font-medium text-zinc-400 hover:text-white">Certificate</button>
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
              <label class="block text-xs text-zinc-400 mb-1">Job Title</label>
              <input type="text" id="profileJobTitle" value="${esc(user.job_title || '')}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm">
            </div>
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Phone</label>
              <input type="tel" id="profilePhone" value="${esc(user.phone || '')}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm">
            </div>
            <div class="md:col-span-2">
              <label class="block text-xs text-zinc-400 mb-1">Address</label>
              <input type="text" id="profileAddress" value="${esc(user.address || '')}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm" placeholder="Street, city, state, ZIP">
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
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Legal name on signature</label>
              <input type="text" id="profileLegalName" value="${esc(user.signature_legal_name || user.full_name || '')}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm">
            </div>
            <div>
              <label class="block text-xs text-zinc-400 mb-1">Initials</label>
              <input type="text" id="profileInitials" maxlength="8" value="${esc(user.signature_initials || '')}" class="w-full bg-zinc-800 border border-zinc-700 rounded-md px-4 py-2 text-sm font-mono uppercase">
            </div>
          </div>
          <div class="mb-4">
            <label class="block text-sm mb-2 text-zinc-300">Draw your signature</label>
            <div class="border border-zinc-700 rounded-md bg-white p-2 inline-block">
              <canvas id="profileSignatureCanvas" width="520" height="140" class="cursor-crosshair rounded"></canvas>
            </div>
            <div class="flex gap-2 mt-2">
              <button type="button" onclick="CasePMUserProfile.clearSignature()" class="px-4 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 rounded">Clear</button>
              <button type="button" onclick="CasePMUserProfile.saveSignature()" class="px-4 py-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 rounded">Save Signature</button>
            </div>
          </div>
          <div>
            <label class="block text-sm mb-2 text-zinc-300">Upload signature image</label>
            <input type="file" id="profileSignatureUpload" accept="image/*" class="text-sm file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:bg-zinc-700 file:text-white hover:file:bg-zinc-600">
            <div id="profileSignatureUploadStatus" class="text-xs text-emerald-400 mt-1"></div>
          </div>
        </div>

        <div id="profile-tab-certificate" class="hidden">
          <p class="text-xs text-zinc-500 mb-3">Upload a digital certificate for formal signing packages. Only certificate metadata is stored — private keys never leave your device.</p>
          <label class="block text-sm mb-2 text-zinc-300">Certificate file</label>
          <input type="file" id="profileCertificateUpload" accept=".pdf,.pfx,.p12,image/*" class="text-sm file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:bg-zinc-700 file:text-white hover:file:bg-zinc-600">
          <div id="profileCertificateStatus" class="text-xs text-emerald-400 mt-2">${user.certificate_file_name ? `On file: ${esc(user.certificate_file_name)}` : ''}</div>
          <ul class="text-xs text-zinc-500 space-y-1 list-disc pl-4 mt-4">
            <li>Change order approvals</li>
            <li>Commitment execution</li>
            <li>Pay applications and formal document packages</li>
          </ul>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-3 mt-8 pt-6 border-t border-zinc-700">
          <div class="flex flex-wrap gap-2 text-sm">
            ${isDeveloper ? `<a href="/developer" class="px-3 py-2 rounded-md bg-red-950/40 hover:bg-red-950 text-red-300 border border-red-900/50"><i class="fa-solid fa-code mr-1"></i> Developer</a>` : ''}
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

    const certInput = modal.querySelector('#profileCertificateUpload');
    if (certInput) {
      certInput.addEventListener('change', async () => {
        if (!certInput.files?.length) return;
        const file = certInput.files[0];
        const status = document.getElementById('profileCertificateStatus');
        try {
          if (global.CasePMEsign) {
            await global.CasePMEsign.saveMySignature({
              certificate_file_name: file.name,
            });
          }
          if (status) status.textContent = `On file: ${file.name}`;
        } catch (err) {
          if (status) status.textContent = err.message || 'Upload failed.';
        }
      });
    }

    document.body.appendChild(modal);
    modal.showModal();

    setTimeout(() => {
      initProfileSignatureCanvas(user);
      setupProfileSignatureUpload();
      setupProfilePhotoUpload();
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
