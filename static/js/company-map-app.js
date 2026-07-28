(function (global) {
  'use strict';

  let map = null;
  let markers = [];
  let locations = [];
  let activeId = null;

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  async function loadLocations() {
    const status = document.getElementById('companyMapStatusFilter')?.value || 'Active';
    const res = await fetch(`/api/company-map/locations?status=${encodeURIComponent(status)}`);
    const data = await res.json();
    locations = data.locations || [];
    renderList();
    renderMarkers();
    const countEl = document.getElementById('companyMapCount');
    if (countEl) countEl.textContent = `${locations.length} job site${locations.length === 1 ? '' : 's'} on map`;
  }

  function filteredLocations() {
    const q = (document.getElementById('companyMapSearch')?.value || '').trim().toLowerCase();
    if (!q) return locations;
    return locations.filter(loc => {
      const hay = [
        loc.name, loc.number, loc.label, loc.address, loc.city, loc.state,
        loc.store_number, loc.client, loc.status,
      ].join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function renderList() {
    const el = document.getElementById('companyMapJobList');
    if (!el) return;
    const list = filteredLocations();
    if (!list.length) {
      el.innerHTML = '<div class="p-4 text-sm text-zinc-500">No mapped job sites match your filter.</div>';
      return;
    }
    el.innerHTML = list.map(loc => `
      <div class="company-map-job-card ${String(activeId) === String(loc.id) ? 'active' : ''}" data-job-id="${loc.id}">
        <h3>${esc(loc.name)}</h3>
        <p>${esc(loc.label)}</p>
        <div class="company-map-job-meta">
          <span>${esc(loc.status || 'Active')}</span>
          ${loc.store_number ? `<span>Store ${esc(loc.store_number)}</span>` : ''}
          ${loc.client ? `<span>${esc(loc.client)}</span>` : ''}
        </div>
      </div>
    `).join('');
    el.querySelectorAll('.company-map-job-card').forEach(card => {
      card.addEventListener('click', () => focusJob(card.getAttribute('data-job-id')));
    });
  }

  function ensureMap() {
    if (map) return map;
    const canvas = document.getElementById('companyMapCanvas');
    if (!canvas || !global.L) return null;
    map = L.map(canvas, { zoomControl: true }).setView([28.5383, -81.3792], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);
    return map;
  }

  function clearMarkers() {
    markers.forEach(m => m.remove());
    markers = [];
  }

  function renderMarkers() {
    const m = ensureMap();
    if (!m) return;
    clearMarkers();
    const list = filteredLocations();
    const bounds = [];
    list.forEach(loc => {
      if (loc.latitude == null || loc.longitude == null) return;
      const latlng = [loc.latitude, loc.longitude];
      bounds.push(latlng);
      const marker = L.marker(latlng).addTo(m);
      marker.bindPopup(`
        <div class="company-map-popup">
          <h4>${esc(loc.name)}</h4>
          <p>${esc(loc.label)}</p>
          <p><strong>Status:</strong> ${esc(loc.status || 'Active')}</p>
          ${loc.client ? `<p><strong>Client:</strong> ${esc(loc.client)}</p>` : ''}
          <p><a href="/email?tab=calendar&project_id=${encodeURIComponent(loc.id)}">Schedule meeting at this job</a></p>
        </div>
      `);
      marker._jobId = loc.id;
      marker.on('click', () => { activeId = loc.id; renderList(); });
      markers.push(marker);
    });
    if (bounds.length === 1) {
      m.setView(bounds[0], 12);
    } else if (bounds.length > 1) {
      m.fitBounds(bounds, { padding: [40, 40] });
    }
    setTimeout(() => m.invalidateSize(), 100);
  }

  function focusJob(id) {
    activeId = id;
    renderList();
    const loc = locations.find(l => String(l.id) === String(id));
    const m = ensureMap();
    if (!loc || !m || loc.latitude == null || loc.longitude == null) return;
    m.setView([loc.latitude, loc.longitude], 14);
    const marker = markers.find(x => String(x._jobId) === String(id));
    if (marker) marker.openPopup();
  }

  function bindEvents() {
    document.getElementById('companyMapStatusFilter')?.addEventListener('change', loadLocations);
    document.getElementById('companyMapSearch')?.addEventListener('input', () => {
      renderList();
      renderMarkers();
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    loadLocations();
  });
})(window);
