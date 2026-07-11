/**
 * Case PM — Photos page (daily-log-style camera, speech naming, date timeline).
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_PHOTOS_CTX || {};
  const el = (id) => document.getElementById(id);
  const esc = (s) => {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  };

  const state = {
    photos: [],
    groups: [],
    stats: { total: 0, today: 0, this_week: 0, this_month: 0, locations: [] },
    groupMode: 'day',
    pendingUploads: [],
    photoSeq: 0,
    stream: null,
    facingMode: 'environment',
    armedPhoto: null,
    listening: false,
    recognition: null,
    selectedDate: new Date().toISOString().slice(0, 10),
  };

  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso + (iso.length === 10 ? 'T12:00:00' : ''));
      return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    } catch (_) {
      return iso;
    }
  }

  function autoPhotoName() {
    state.photoSeq += 1;
    const d = state.selectedDate || new Date().toISOString().slice(0, 10);
    return `Photo ${state.photoSeq} · ${d}`;
  }

  function queryParams() {
    const p = new URLSearchParams();
    const search = (el('photoSearch')?.value || '').trim();
    const location = el('locationFilter')?.value || '';
    const dateRange = el('dateFilter')?.value || '';
    const group = el('groupMode')?.value || state.groupMode;
    if (search) p.set('search', search);
    if (location) p.set('location', location);
    if (dateRange) p.set('date_range', dateRange);
    if (group) p.set('group', group);
    return p.toString();
  }

  async function loadPhotos() {
    try {
      const qs = queryParams();
      const res = await fetch(`/api/photos${qs ? `?${qs}` : ''}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Failed to load photos');
      state.photos = json.photos || [];
      state.groups = json.groups || [];
      state.stats = json.stats || state.stats;
      state.groupMode = json.group_mode || state.groupMode;
      renderStats();
      renderTimeline();
      populateLocationFilter();
    } catch (e) {
      console.error(e);
      if (global.showToast) global.showToast(e.message || 'Could not load photos', 'error');
    }
  }

  function renderStats() {
    const s = state.stats;
    if (el('statPhotoTotal')) el('statPhotoTotal').textContent = s.total || 0;
    if (el('statPhotoToday')) el('statPhotoToday').textContent = s.today || 0;
    if (el('statPhotoWeek')) el('statPhotoWeek').textContent = s.this_week || 0;
    if (el('statPhotoMonth')) el('statPhotoMonth').textContent = s.this_month || 0;
  }

  function populateLocationFilter() {
    const sel = el('locationFilter');
    if (!sel) return;
    const current = sel.value;
    const locs = state.stats.locations || [];
    sel.innerHTML = '<option value="">All Locations</option>' +
      locs.map((l) => `<option value="${esc(l)}">${esc(l)}</option>`).join('');
    if (current && locs.includes(current)) sel.value = current;
  }

  function renderTimeline() {
    const container = el('photosTimeline');
    const empty = el('emptyState');
    if (!container) return;

    if (!state.groups.length) {
      container.innerHTML = '';
      empty?.classList.remove('hidden');
      return;
    }
    empty?.classList.add('hidden');

    let html = '';
    state.groups.forEach((group) => {
      html += `<section class="photos-day-group mb-6" data-group="${esc(group.key)}">
        <div class="flex items-center justify-between mb-3 sticky top-0 z-10 bg-zinc-950/95 py-2 border-b border-zinc-800">
          <h2 class="text-sm font-semibold text-zinc-200"><i class="fa-regular fa-calendar mr-2 text-emerald-500"></i>${esc(group.label)}</h2>
          <span class="text-xs text-zinc-500">${group.photos.length} photo${group.photos.length === 1 ? '' : 's'}</span>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">`;
      group.photos.forEach((p) => {
        html += `<article class="photos-card group relative bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden cursor-pointer" data-photo-id="${p.id}">
          <div class="aspect-[4/3] bg-zinc-800">
            <img src="${esc(p.url || '')}" alt="${esc(p.caption)}" class="w-full h-full object-cover group-hover:scale-[1.02] transition-transform duration-200" loading="lazy">
          </div>
          <div class="p-2.5">
            <div class="font-medium text-xs line-clamp-2 leading-snug">${esc(p.caption)}</div>
            <div class="flex items-center justify-between mt-1.5 text-[10px] text-zinc-500 gap-2">
              <span class="truncate">${esc(p.location || '—')}</span>
              <span class="flex-shrink-0">${esc(p.uploaded_by || '')}</span>
            </div>
          </div>
        </article>`;
      });
      html += '</div></section>';
    });
    container.innerHTML = html;
    container.querySelectorAll('[data-photo-id]').forEach((card) => {
      card.addEventListener('click', () => {
        const id = parseInt(card.getAttribute('data-photo-id'), 10);
        const photo = state.photos.find((p) => p.id === id);
        if (photo) openDetail(photo);
      });
    });
  }

  function openDetail(photo) {
    el('photoDetailImg').src = photo.url || '';
    el('photoDetailImg').alt = photo.caption || '';
    el('photoDetailTitle').textContent = photo.caption || 'Photo';
    el('photoDetailMeta').innerHTML = `
      <div><span class="text-zinc-500">Taken:</span> ${esc(fmtDate(photo.taken_date))}</div>
      <div><span class="text-zinc-500">Location:</span> ${esc(photo.location || '—')}</div>
      <div><span class="text-zinc-500">Uploaded by:</span> ${esc(photo.uploaded_by || '—')}</div>
      ${photo.document_id ? `<div><span class="text-zinc-500">Documents:</span> <a href="/documents?project_id=${photo.project_id}" class="text-emerald-400 hover:underline">View in Documents › Photos › ${esc(fmtDate(photo.taken_date))}</a></div>` : ''}
    `;
    el('photoDetailOpen').href = photo.url || '#';
    el('photoDetailDelete').onclick = () => deletePhoto(photo.id);
    el('photoDetailModal').showModal();
  }

  async function deletePhoto(id) {
    if (!confirm('Delete this photo?')) return;
    try {
      const res = await fetch(`/api/photos/${id}`, { method: 'DELETE' });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Delete failed');
      el('photoDetailModal').close();
      await loadPhotos();
      if (global.showToast) global.showToast('Photo deleted');
    } catch (e) {
      alert(e.message || 'Could not delete photo');
    }
  }

  // ---------------- Camera (daily-log pattern) ----------------
  async function openCamera() {
    state.selectedDate = el('photoTakenDate')?.value || new Date().toISOString().slice(0, 10);
    state.photoSeq = state.pendingUploads.length;
    el('photosCamError')?.classList.add('hidden');
    el('photosCameraModal')?.showModal();
    await startStream();
    renderCamThumbs();
  }

  async function startStream() {
    stopStream();
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: state.facingMode }, audio: false,
      });
      const v = el('photosVideo');
      v.srcObject = state.stream;
      v.classList.remove('hidden');
      el('photosCamError')?.classList.add('hidden');
    } catch (e) {
      el('photosVideo')?.classList.add('hidden');
      const err = el('photosCamError');
      if (!err) return;
      if (!window.isSecureContext) {
        err.innerHTML = 'The in-app camera needs HTTPS. Use <b>Browse</b> to add photos instead.';
      } else if (e && e.name === 'NotAllowedError') {
        err.innerHTML = 'Camera permission denied. Allow access or use <b>Browse</b>.';
      } else {
        err.innerHTML = 'Camera unavailable. Use <b>Browse</b> to add photos.';
      }
      err.classList.remove('hidden');
    }
  }

  function stopStream() {
    if (state.stream) {
      state.stream.getTracks().forEach((t) => t.stop());
      state.stream = null;
    }
  }

  function captureFrame() {
    const v = el('photosVideo');
    if (!v || !v.videoWidth) return null;
    const canvas = el('photosSnapCanvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext('2d').drawImage(v, 0, 0);
    return canvas;
  }

  function onCamShoot() {
    if (state.armedPhoto) {
      commitArmed('');
      return;
    }
    const canvas = captureFrame();
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      state.armedPhoto = { blob, url };
      el('photosCamShootLabel').textContent = 'Save';
      el('photosCamShoot')?.classList.add('armed');
      el('photosCamHint').innerHTML = 'Captured! Tap <b>Name (talk)</b> to name &amp; save, or <b>Save</b> for auto name.';
      renderCamThumbs();
    }, 'image/jpeg', 0.9);
  }

  async function commitArmed(name) {
    if (!state.armedPhoto) return;
    const finalName = (name || '').trim() || autoPhotoName();
    const location = (el('photoLocation')?.value || '').trim();
    const takenDate = el('photoTakenDate')?.value || new Date().toISOString().slice(0, 10);
    const blob = state.armedPhoto.blob;
    const url = state.armedPhoto.url;
    state.armedPhoto = null;
    stopListening();
    el('photosCamShootLabel').textContent = 'Capture';
    el('photosCamShoot')?.classList.remove('armed');
    el('photosCamNameInput')?.classList.add('hidden');
    if (el('photosCamNameInput')) el('photosCamNameInput').value = '';
    el('photosCamNameLabel').textContent = 'Name (talk)';
    el('photosCamHint').innerHTML = 'Tap <b>Capture</b> to snap. Then tap <b>Name (talk)</b> to name &amp; save, or <b>Save</b> for auto name.';

    await uploadBlob(blob, finalName, location, takenDate, url);
    renderCamThumbs();
  }

  async function uploadBlob(blob, name, location, takenDate, previewUrl) {
    const fd = new FormData();
    fd.append('file', blob, `${name}.jpg`);
    fd.append('name', name);
    fd.append('location', location);
    fd.append('taken_date', takenDate);
    try {
      const res = await fetch('/api/photos', { method: 'POST', body: fd });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Upload failed');
      if (previewUrl) {
        try { URL.revokeObjectURL(previewUrl); } catch (_) {}
      }
      if (global.showToast) global.showToast(`Saved: ${name}`);
      await loadPhotos();
    } catch (e) {
      alert(e.message || 'Upload failed');
    }
  }

  function renderCamThumbs() {
    const wrap = el('photosCamThumbs');
    if (!wrap) return;
    let html = '';
    if (state.armedPhoto) {
      html += `<div class="photos-thumb ring-2 ring-blue-500"><img src="${state.armedPhoto.url}"><div class="photos-thumb-name">Unsaved</div></div>`;
    }
    wrap.innerHTML = html;
  }

  function onCamName() {
    if (!state.armedPhoto) {
      el('photosCamHint').innerHTML = 'Capture a photo first, then name it.';
      return;
    }
    if (!state.listening) startListening();
    else commitArmed(el('photosCamNameInput')?.value || '');
  }

  function startListening() {
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    const input = el('photosCamNameInput');
    const hint = el('photosCamHint');
    input?.classList.remove('hidden');
    input?.focus();
    el('photosCamNameLabel').textContent = 'Stop & Save';
    el('photosCamName')?.classList.add('listening');
    state.listening = true;
    if (!window.isSecureContext) {
      hint.innerHTML = '<span class="text-amber-400">Voice needs HTTPS. Type the name, then tap Stop &amp; Save.</span>';
      return;
    }
    if (!SR) {
      hint.innerHTML = '<span class="text-amber-400">Voice not supported — type the name, then tap Stop &amp; Save.</span>';
      return;
    }
    try {
      const rec = new SR();
      rec.lang = 'en-US';
      rec.interimResults = true;
      rec.continuous = true;
      rec.onstart = () => {
        hint.innerHTML = '<span class="text-emerald-400"><i class="fa-solid fa-microphone"></i> Listening… say the file name.</span>';
      };
      rec.onresult = (event) => {
        let t = '';
        for (let i = 0; i < event.results.length; i++) t += event.results[i][0].transcript;
        if (input) input.value = t.trim();
      };
      rec.onerror = () => {
        hint.innerHTML = '<span class="text-amber-400">Voice error — type the name, then tap Stop &amp; Save.</span>';
      };
      rec.start();
      state.recognition = rec;
    } catch (_) {
      hint.innerHTML = '<span class="text-amber-400">Voice unavailable — type the name.</span>';
    }
  }

  function stopListening() {
    state.listening = false;
    el('photosCamName')?.classList.remove('listening');
    el('photosCamNameLabel').textContent = 'Name (talk)';
    if (state.recognition) {
      try { state.recognition.stop(); } catch (_) {}
      state.recognition = null;
    }
  }

  function closeCamera() {
    if (state.armedPhoto) commitArmed('');
    stopListening();
    stopStream();
    el('photosCameraModal')?.close();
  }

  function clearFilters() {
    if (el('photoSearch')) el('photoSearch').value = '';
    if (el('locationFilter')) el('locationFilter').value = '';
    if (el('dateFilter')) el('dateFilter').value = '';
    loadPhotos();
  }

  function bind() {
    el('photosBtnRefresh')?.addEventListener('click', loadPhotos);
    el('photosOpenCamera')?.addEventListener('click', openCamera);
    el('photosBrowseBtn')?.addEventListener('click', () => el('photosBrowseInput')?.click());
    el('photosCamClose')?.addEventListener('click', closeCamera);
    el('photosCamDone')?.addEventListener('click', closeCamera);
    el('photosCamShoot')?.addEventListener('click', onCamShoot);
    el('photosCamName')?.addEventListener('click', onCamName);
    el('photosCamSwitch')?.addEventListener('click', () => {
      state.facingMode = state.facingMode === 'environment' ? 'user' : 'environment';
      startStream();
    });
    el('photosDetailClose')?.addEventListener('click', () => el('photoDetailModal')?.close());

    el('photosBrowseInput')?.addEventListener('change', async (e) => {
      const location = (el('photoLocation')?.value || '').trim();
      const takenDate = el('photoTakenDate')?.value || new Date().toISOString().slice(0, 10);
      for (const f of e.target.files) {
        state.photoSeq += 1;
        await uploadBlob(f, autoPhotoName(), location, takenDate);
      }
      e.target.value = '';
    });

    ['photoSearch', 'locationFilter', 'dateFilter', 'groupMode'].forEach((id) => {
      const node = el(id);
      if (!node) return;
      node.addEventListener('input', () => loadPhotos());
      node.addEventListener('change', () => loadPhotos());
    });

    el('photosClearFilters')?.addEventListener('click', clearFilters);

    if (el('photoTakenDate')) {
      el('photoTakenDate').value = new Date().toISOString().slice(0, 10);
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get('action') === 'upload') {
      setTimeout(openCamera, 300);
    }

    global.addEventListener('casepm:project-changed', loadPhotos);
    global.onCasePmProjectChanged = () => loadPhotos();
  }

  function init() {
    bind();
    loadPhotos();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  global.CasePMPhotos = { refresh: loadPhotos, openCamera };
})(window);
