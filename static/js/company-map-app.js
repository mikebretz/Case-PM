(function (global) {
  'use strict';

  let map = null;
  let streetLayer = null;
  let satelliteLayer = null;
  let activeBaseLayer = 'street';
  let markers = [];
  let locations = [];
  let activeId = null;
  let routeLayer = null;
  let originMarker = null;
  let userLocation = null;
  let currentDirections = null;
  let directionsDest = null;
  let lastDirectionsOrigin = null;
  let pendingDirectionsJobId = null;
  let selectedOriginAddress = null;

  const HARDHAT_ICON = () => L.divIcon({
    className: 'company-map-hardhat-marker',
    html: '<div class="company-map-hardhat-pin"><i class="fa-solid fa-hard-hat"></i></div>',
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -28],
  });

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  async function loadLocations() {
    const status = document.getElementById('companyMapStatusFilter')?.value || 'current';
    const res = await fetch(`/api/company-map/locations?status=${encodeURIComponent(status)}&include_unmapped=1`);
    const data = await res.json();
    locations = data.locations || [];
    renderList();
    renderMarkers();
    const countEl = document.getElementById('companyMapCount');
    const mapped = data.mapped_count != null ? data.mapped_count : locations.filter(l => l.mapped).length;
    if (countEl) {
      countEl.textContent = `${mapped} on map · ${locations.length} current job${locations.length === 1 ? '' : 's'}`;
    }
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
      el.innerHTML = '<div class="p-4 text-sm text-zinc-500">No current jobs match your filter. Try <strong>All projects</strong> or add addresses on the Projects page.</div>';
      return;
    }
    el.innerHTML = list.map(loc => `
      <div class="company-map-job-card ${String(activeId) === String(loc.id) ? 'active' : ''} ${loc.mapped ? '' : 'unmapped'}" data-job-id="${loc.id}">
        <h3>${esc(loc.name)}</h3>
        <p>${esc(loc.label)}</p>
        <div class="company-map-job-meta">
          <span>${esc(loc.status || 'Active')}</span>
          ${loc.mapped ? '<span class="text-emerald-400">On map</span>' : '<span class="text-amber-400">Needs geocode</span>'}
          ${loc.store_number ? `<span>Store ${esc(loc.store_number)}</span>` : ''}
          ${loc.client ? `<span>${esc(loc.client)}</span>` : ''}
        </div>
        ${loc.mapped ? `<button type="button" class="company-map-directions-btn" data-directions-id="${loc.id}"><i class="fa-solid fa-route"></i> Directions</button>` : ''}
      </div>
    `).join('');
    el.querySelectorAll('.company-map-job-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.company-map-directions-btn')) return;
        focusJob(card.getAttribute('data-job-id'));
      });
    });
    el.querySelectorAll('.company-map-directions-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openOriginPicker(btn.getAttribute('data-directions-id'));
      });
    });
  }

  function ensureMap() {
    if (map) return map;
    const canvas = document.getElementById('companyMapCanvas');
    if (!canvas || !global.L) return null;

    streetLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    });
    satelliteLayer = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics',
      },
    );

    map = L.map(canvas, {
      zoomControl: true,
      layers: [streetLayer],
    }).setView([28.5383, -81.3792], 7);

    return map;
  }

  function setMapLayer(layer) {
    const m = ensureMap();
    if (!m || !streetLayer || !satelliteLayer) return;
    activeBaseLayer = layer === 'satellite' ? 'satellite' : 'street';
    if (activeBaseLayer === 'satellite') {
      if (m.hasLayer(streetLayer)) m.removeLayer(streetLayer);
      if (!m.hasLayer(satelliteLayer)) satelliteLayer.addTo(m);
    } else {
      if (m.hasLayer(satelliteLayer)) m.removeLayer(satelliteLayer);
      if (!m.hasLayer(streetLayer)) streetLayer.addTo(m);
    }
    document.getElementById('companyMapLayerStreet')?.classList.toggle('active', activeBaseLayer === 'street');
    document.getElementById('companyMapLayerSatellite')?.classList.toggle('active', activeBaseLayer === 'satellite');
  }

  function clearMarkers() {
    markers.forEach(m => m.remove());
    markers = [];
  }

  function clearRoute() {
    if (routeLayer) {
      routeLayer.remove();
      routeLayer = null;
    }
    if (originMarker) {
      originMarker.remove();
      originMarker = null;
    }
  }

  function renderMarkers() {
    const m = ensureMap();
    if (!m) return;
    clearMarkers();
    const list = filteredLocations().filter(loc => loc.mapped && loc.latitude != null && loc.longitude != null);
    const bounds = [];
    list.forEach(loc => {
      const latlng = [loc.latitude, loc.longitude];
      bounds.push(latlng);
      const marker = L.marker(latlng, { icon: HARDHAT_ICON() }).addTo(m);
      marker.bindPopup(`
        <div class="company-map-popup">
          <h4>${esc(loc.name)}</h4>
          <p>${esc(loc.label)}</p>
          <p><strong>Status:</strong> ${esc(loc.status || 'Active')}</p>
          ${loc.client ? `<p><strong>Client:</strong> ${esc(loc.client)}</p>` : ''}
          <p>
            <button type="button" class="company-map-popup-btn" onclick="window.__casepmMapDirections && window.__casepmMapDirections('${loc.id}')">Get directions</button>
          </p>
          <p><a href="/email?tab=calendar&project_id=${encodeURIComponent(loc.id)}&new=1">Schedule meeting</a></p>
        </div>
      `);
      marker._jobId = loc.id;
      marker.on('click', () => { activeId = loc.id; renderList(); });
      markers.push(marker);
    });
    if (bounds.length === 1) {
      m.setView(bounds[0], 13);
    } else if (bounds.length > 1) {
      m.fitBounds(bounds, { padding: [48, 48], maxZoom: 12 });
    }
    setTimeout(() => m.invalidateSize(), 120);
  }

  global.__casepmMapDirections = (id) => openOriginPicker(id);

  function focusJob(id) {
    activeId = id;
    renderList();
    const loc = locations.find(l => String(l.id) === String(id));
    const m = ensureMap();
    if (!loc || !m) return;
    if (loc.latitude == null || loc.longitude == null) return;
    m.setView([loc.latitude, loc.longitude], 14);
    const marker = markers.find(x => String(x._jobId) === String(id));
    if (marker) marker.openPopup();
  }

  function getOriginType() {
    return document.querySelector('input[name="companyMapOriginType"]:checked')?.value || 'gps';
  }

  function updateOriginFormVisibility() {
    const isAddress = getOriginType() === 'address';
    document.getElementById('companyMapOriginAddressWrap')?.classList.toggle('hidden', !isAddress);
    document.getElementById('companyMapOriginGpsHint')?.classList.toggle('hidden', isAddress);
  }

  function openOriginPicker(jobId) {
    const loc = locations.find(l => String(l.id) === String(jobId));
    if (!loc || loc.latitude == null || loc.longitude == null) {
      alert('This job does not have map coordinates yet. Add a street address on the Projects page.');
      return;
    }
    pendingDirectionsJobId = jobId;
    directionsDest = loc;
    selectedOriginAddress = null;
    const modal = document.getElementById('companyMapOriginModal');
    const destLabel = document.getElementById('companyMapOriginDestLabel');
    if (destLabel) destLabel.textContent = `To: ${loc.name} — ${loc.label || ''}`;
    const gpsRadio = document.querySelector('input[name="companyMapOriginType"][value="gps"]');
    if (gpsRadio) gpsRadio.checked = true;
    const addrInput = document.getElementById('companyMapOriginAddress');
    if (addrInput) addrInput.value = '';
    updateOriginFormVisibility();
    modal?.classList.remove('hidden');
    if (addrInput && global.CasePMAddressAutocomplete && !addrInput.dataset.autocompleteBound) {
      global.CasePMAddressAutocomplete.attach(addrInput, {
        getNearLat: () => directionsDest?.latitude,
        getNearLng: () => directionsDest?.longitude,
        onSelect(item) {
          selectedOriginAddress = {
            lat: item.latitude,
            lng: item.longitude,
            label: item.label || item.address || addrInput.value,
          };
        },
      });
      addrInput.dataset.autocompleteBound = '1';
    }
  }

  function closeOriginPicker() {
    document.getElementById('companyMapOriginModal')?.classList.add('hidden');
    pendingDirectionsJobId = null;
  }

  async function resolveOriginFromPicker() {
    const type = getOriginType();
    if (type === 'gps') {
      try {
        const loc = await ensureUserLocation(true);
        return { lat: loc.lat, lng: loc.lng, label: loc.label };
      } catch (e) {
        throw new Error('Could not get your location. Allow GPS in your browser or enter a starting address.');
      }
    }

    const input = document.getElementById('companyMapOriginAddress');
    const typed = (input?.value || '').trim();
    if (!typed) throw new Error('Enter a starting address.');

    if (selectedOriginAddress && selectedOriginAddress.label === typed) {
      return selectedOriginAddress;
    }

    const res = await fetch(`/api/geocode/search?q=${encodeURIComponent(typed)}&limit=1&near_lat=${encodeURIComponent(directionsDest?.latitude ?? '')}&near_lng=${encodeURIComponent(directionsDest?.longitude ?? '')}`);
    const data = await res.json();
    const hit = data.closest || (data.suggestions || [])[0];
    if (!hit || hit.latitude == null || hit.longitude == null) {
      throw new Error('Could not find that address. Pick a suggestion from the list or try a city/state.');
    }
    return {
      lat: hit.latitude,
      lng: hit.longitude,
      label: hit.label || typed,
    };
  }

  async function ensureUserLocation(forceRefresh) {
    if (userLocation && !forceRefresh) return userLocation;
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('Geolocation not supported'));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        pos => {
          userLocation = { lat: pos.coords.latitude, lng: pos.coords.longitude, label: 'My current location' };
          resolve(userLocation);
        },
        () => reject(new Error('GPS unavailable')),
        { enableHighAccuracy: true, timeout: 12000 },
      );
    });
  }

  async function submitOriginAndRoute() {
    const jobId = pendingDirectionsJobId;
    if (!jobId) return;
    const loc = locations.find(l => String(l.id) === String(jobId));
    if (!loc) return;

    const goBtn = document.getElementById('companyMapOriginGo');
    if (goBtn) {
      goBtn.disabled = true;
      goBtn.textContent = 'Calculating…';
    }
    try {
      const origin = await resolveOriginFromPicker();
      lastDirectionsOrigin = origin;
      closeOriginPicker();
      await fetchAndShowDirections(origin, loc);
    } catch (e) {
      alert(e.message || 'Could not start directions.');
    } finally {
      if (goBtn) {
        goBtn.disabled = false;
        goBtn.innerHTML = '<i class="fa-solid fa-route"></i> Get directions';
      }
    }
  }

  async function fetchAndShowDirections(origin, loc) {
    directionsDest = loc;
    const res = await fetch('/api/company-map/directions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        origin_lat: origin.lat,
        origin_lng: origin.lng,
        dest_lat: loc.latitude,
        dest_lng: loc.longitude,
        origin_label: origin.label,
        dest_label: loc.label || loc.name,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Could not get directions');
      return;
    }
    currentDirections = data;
    showDirectionsPanel(data, loc, origin);
    drawRoute(data.geometry || [], origin);
  }

  function drawRoute(coords, origin) {
    const m = ensureMap();
    if (!m || !coords.length) return;
    clearRoute();
    const latlngs = coords.map(c => [c[1], c[0]]);
    routeLayer = L.polyline(latlngs, { color: '#10b981', weight: 5, opacity: 0.85 }).addTo(m);
    if (origin) {
      originMarker = L.circleMarker([origin.lat, origin.lng], {
        radius: 7,
        color: '#3b82f6',
        fillColor: '#60a5fa',
        fillOpacity: 0.9,
        weight: 2,
      }).addTo(m).bindTooltip('Start: ' + (origin.label || 'Origin'), { permanent: false });
    }
    const bounds = routeLayer.getBounds();
    if (origin) bounds.extend([origin.lat, origin.lng]);
    m.fitBounds(bounds, { padding: [40, 40] });
  }

  function showDirectionsPanel(data, dest, origin) {
    const panel = document.getElementById('companyMapDirectionsPanel');
    const summary = document.getElementById('companyMapDirectionsSummary');
    const steps = document.getElementById('companyMapDirectionsSteps');
    const mileage = document.getElementById('companyMapMileageNote');
    if (!panel || !summary) return;
    panel.classList.remove('hidden');
    summary.innerHTML = `
      <div><strong>To:</strong> ${esc(dest.name)}</div>
      <div class="text-zinc-400 text-xs mt-1">${esc(dest.label)}</div>
      <div class="company-map-distance">${data.distance_miles} miles · ~${data.duration_minutes} min</div>
      <div class="text-xs text-zinc-500 mt-1">From: ${esc(origin.label)}</div>
    `;
    if (steps) {
      steps.innerHTML = (data.steps || []).slice(0, 12).map(s =>
        `<li>${esc(s.instruction || 'Continue')}${s.name ? ` on ${esc(s.name)}` : ''} <span class="text-zinc-500">(${s.distance_miles} mi)</span></li>`
      ).join('');
    }
    if (mileage) {
      mileage.textContent = `Mileage for reimbursement: ${data.distance_miles} miles (save or email for superintendent pay apps)`;
    }
    const g = document.getElementById('companyMapGoogleLink');
    const a = document.getElementById('companyMapAppleLink');
    if (g && data.links) g.href = data.links.google_maps;
    if (a && data.links) a.href = data.links.apple_maps;
  }

  async function emailDirections() {
    if (!currentDirections || !directionsDest) return;
    const to = prompt('Send directions to email:', '') || '';
    if (!to.trim()) return;
    const origin = lastDirectionsOrigin || userLocation || { lat: 28.5383, lng: -81.3792, label: 'Office' };
    const res = await fetch('/api/company-map/directions/email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        to: to.trim(),
        origin_lat: origin.lat,
        origin_lng: origin.lng,
        dest_lat: directionsDest.latitude,
        dest_lng: directionsDest.longitude,
        origin_label: origin.label,
        dest_label: directionsDest.label || directionsDest.name,
        note: `Directions to ${directionsDest.name} — ${currentDirections.distance_miles} miles for field travel / mileage.`,
      }),
    });
    const data = await res.json();
    alert(data.message || (data.sent ? 'Directions sent.' : 'Could not send email.'));
  }

  function bindEvents() {
    document.getElementById('companyMapStatusFilter')?.addEventListener('change', loadLocations);
    document.getElementById('companyMapSearch')?.addEventListener('input', () => {
      renderList();
      renderMarkers();
    });
    document.getElementById('companyMapLayerStreet')?.addEventListener('click', () => setMapLayer('street'));
    document.getElementById('companyMapLayerSatellite')?.addEventListener('click', () => setMapLayer('satellite'));

    document.querySelectorAll('input[name="companyMapOriginType"]').forEach(radio => {
      radio.addEventListener('change', updateOriginFormVisibility);
    });
    document.getElementById('companyMapOriginAddress')?.addEventListener('input', () => {
      selectedOriginAddress = null;
    });
    document.getElementById('companyMapOriginGo')?.addEventListener('click', submitOriginAndRoute);
    document.getElementById('companyMapOriginCancel')?.addEventListener('click', closeOriginPicker);
    document.getElementById('companyMapOriginClose')?.addEventListener('click', closeOriginPicker);
    document.getElementById('companyMapOriginModal')?.addEventListener('click', (e) => {
      if (e.target.id === 'companyMapOriginModal') closeOriginPicker();
    });

    document.getElementById('companyMapUseMyLocation')?.addEventListener('click', async () => {
      try {
        const loc = await ensureUserLocation(true);
        const m = ensureMap();
        if (m) m.setView([loc.lat, loc.lng], 11);
        alert('Map centered on your current location.');
      } catch (e) {
        alert('Could not get your location. Check browser permissions.');
      }
    });
    document.getElementById('companyMapCloseDirections')?.addEventListener('click', () => {
      document.getElementById('companyMapDirectionsPanel')?.classList.add('hidden');
      clearRoute();
    });
    document.getElementById('companyMapEmailDirections')?.addEventListener('click', emailDirections);
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    loadLocations();
  });
})(window);
