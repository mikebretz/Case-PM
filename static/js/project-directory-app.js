(function () {
  const SOURCE_BADGE_CLASS = 'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-zinc-800 text-zinc-300 border border-zinc-700';

  function resolveProjectId() {
    const ctx = window.CASEPM_PROJECT_DIRECTORY_CTX || {};
    if (ctx.projectId) {
      return Number(ctx.projectId);
    }
    const params = new URLSearchParams(window.location.search);
    const fromUrl = parseInt(params.get('project_id') || '', 10);
    return Number.isFinite(fromUrl) && fromUrl > 0 ? fromUrl : null;
  }

  function initProjectDirectory() {
    const projectId = resolveProjectId();
    const state = {
      project: null,
      directory: [],
      companies: [],
      staff: [],
      counts: {},
      scope: 'all_project',
      view: 'people',
      search: '',
    };

    const els = {
      subtitle: document.getElementById('pdSubtitle'),
      projectCard: document.getElementById('pdProjectCard'),
      projectName: document.getElementById('pdProjectName'),
      projectNumber: document.getElementById('pdProjectNumber'),
      projectStatus: document.getElementById('pdProjectStatus'),
      projectManager: document.getElementById('pdProjectManager'),
      projectAddress: document.getElementById('pdProjectAddress'),
      projectDescription: document.getElementById('pdProjectDescription'),
      contactsBody: document.getElementById('pdContactsBody'),
      companiesBody: document.getElementById('pdCompaniesBody'),
      peoplePanel: document.getElementById('pdPeoplePanel'),
      companiesPanel: document.getElementById('pdCompaniesPanel'),
      contactCount: document.getElementById('pdContactCount'),
      statusText: document.getElementById('pdStatusText'),
      refresh: document.getElementById('pdRefresh'),
      search: document.getElementById('pdSearch'),
      scopeFilters: document.querySelectorAll('[data-pd-scope]'),
      viewFilters: document.querySelectorAll('[data-pd-view]'),
    };

    function esc(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    function setText(el, value, fallback) {
      if (!el) return;
      el.textContent = (value || '').trim() || fallback || '—';
    }

    function normalizeSearch(value) {
      return String(value || '').trim().toLowerCase();
    }

    function matchesSearch(row, haystackFields) {
      const query = normalizeSearch(state.search);
      if (!query) return true;
      const hay = haystackFields.map((field) => String(field || '')).join(' ').toLowerCase();
      return hay.includes(query);
    }

    function renderSourceBadges(labels) {
      const items = Array.isArray(labels) ? labels.filter(Boolean) : [];
      if (!items.length) return '—';
      return items.map((label) => `<span class="${SOURCE_BADGE_CLASS} mr-1 mb-1">${esc(label)}</span>`).join('');
    }

    function peopleForScope() {
      const directory = Array.isArray(state.directory) ? state.directory : [];
      const staff = Array.isArray(state.staff) ? state.staff : [];
      if (state.scope === 'on_project') {
        return directory.filter((entry) => entry.on_project);
      }
      if (state.scope === 'all_personnel') {
        const merged = new Map();
        directory.forEach((entry) => {
          const key = entry.user_id != null
            ? `user:${entry.user_id}`
            : `email:${(entry.email || '').toLowerCase()}|${(entry.company || '').toLowerCase()}|${(entry.name || '').toLowerCase()}`;
          merged.set(key, { ...entry, on_project: Boolean(entry.on_project) });
        });
        staff.forEach((entry) => {
          const key = entry.user_id != null
            ? `user:${entry.user_id}`
            : `email:${(entry.email || '').toLowerCase()}|${(entry.company || '').toLowerCase()}|${(entry.name || '').toLowerCase()}`;
          const existing = merged.get(key);
          if (existing) {
            existing.on_project = true;
            const labels = new Set([...(existing.source_labels || []), ...(entry.source_labels || [])]);
            existing.source_labels = Array.from(labels);
            return;
          }
          merged.set(key, { ...entry, on_project: Boolean(entry.on_project) });
        });
        return Array.from(merged.values());
      }
      return directory;
    }

    function renderPeople(contacts) {
      const rows = Array.isArray(contacts) ? contacts : [];
      if (!els.contactsBody) return;
      const filtered = rows.filter((contact) => matchesSearch(contact, [
        contact.name,
        contact.position,
        contact.job_title,
        contact.role_label,
        contact.company,
        contact.firm,
        contact.email,
        contact.phone,
        (contact.source_labels || []).join(' '),
      ]));
      if (!filtered.length) {
        els.contactsBody.innerHTML = '<tr><td colspan="6" class="pd-empty">No people match the current filters. Team members, subcontractors with SOV values, RFI assignees, schedule resources, and other module contacts appear here when linked to this project.</td></tr>';
        setText(els.contactCount, '0 people');
        return;
      }
      els.contactsBody.innerHTML = filtered.map((contact) => {
        const position = contact.position || contact.job_title || contact.role_label || '—';
        const company = contact.company || contact.firm || '—';
        const email = contact.email
          ? `<a href="mailto:${esc(contact.email)}" class="text-sky-400 hover:text-sky-300">${esc(contact.email)}</a>`
          : '—';
        const phone = contact.phone
          ? `<a href="tel:${esc(contact.phone)}" class="text-sky-400 hover:text-sky-300">${esc(contact.phone)}</a>`
          : '—';
        const onProject = contact.on_project
          ? '<span class="text-emerald-400 text-xs">On project</span>'
          : '<span class="text-zinc-500 text-xs">Module link</span>';
        return `<tr>
          <td class="text-zinc-300">${esc(position)}</td>
          <td class="text-white">${esc(contact.name || '—')}</td>
          <td class="text-zinc-300">${esc(company)}</td>
          <td>${email}</td>
          <td>${phone}</td>
          <td><div class="flex flex-wrap gap-1 mb-1">${renderSourceBadges(contact.source_labels)}</div>${onProject}</td>
        </tr>`;
      }).join('');
      setText(els.contactCount, `${filtered.length} people`);
    }

    function renderCompanies(companies) {
      const rows = Array.isArray(companies) ? companies : [];
      if (!els.companiesBody) return;
      const filtered = rows.filter((company) => matchesSearch(company, [
        company.name,
        (company.source_labels || []).join(' '),
        (company.people || []).map((person) => [person.name, person.position, person.email].join(' ')).join(' '),
      ]));
      if (!filtered.length) {
        els.companiesBody.innerHTML = '<tr><td colspan="4" class="pd-empty">No companies match the current filters.</td></tr>';
        return;
      }
      els.companiesBody.innerHTML = filtered.map((company) => {
        const peoplePreview = (company.people || [])
          .slice(0, 3)
          .map((person) => esc(person.name || '—'))
          .join(', ');
        const extra = (company.people || []).length > 3 ? ` +${company.people.length - 3} more` : '';
        const roster = peoplePreview ? `${peoplePreview}${extra}` : '—';
        const onProject = company.on_project
          ? '<span class="text-emerald-400 text-xs">On project</span>'
          : '<span class="text-zinc-500 text-xs">Module link</span>';
        return `<tr>
          <td class="text-white font-medium">${esc(company.name || '—')}</td>
          <td class="text-zinc-300">${esc(String(company.people_count || 0))}</td>
          <td class="text-zinc-300">${roster}</td>
          <td><div class="flex flex-wrap gap-1 mb-1">${renderSourceBadges(company.source_labels)}</div>${onProject}</td>
        </tr>`;
      }).join('');
    }

    function updateFilterButtons(buttons, activeValue, attr) {
      buttons.forEach((button) => {
        const value = button.getAttribute(attr);
        const active = value === activeValue;
        button.classList.toggle('bg-sky-600', active);
        button.classList.toggle('text-white', active);
        button.classList.toggle('bg-zinc-800', !active);
        button.classList.toggle('text-zinc-300', !active);
      });
    }

    function renderAll() {
      const people = peopleForScope();
      const showPeople = state.view === 'people' || state.view === 'all';
      const showCompanies = state.view === 'companies' || state.view === 'all';

      if (els.peoplePanel) els.peoplePanel.classList.toggle('hidden', !showPeople);
      if (els.companiesPanel) els.companiesPanel.classList.toggle('hidden', !showCompanies);

      if (showPeople) renderPeople(people);
      if (showCompanies) renderCompanies(state.companies);

      updateFilterButtons(els.scopeFilters, state.scope, 'data-pd-scope');
      updateFilterButtons(els.viewFilters, state.view, 'data-pd-view');
    }

    function renderProject(project) {
      if (!project) {
        if (els.projectCard) els.projectCard.classList.add('hidden');
        state.directory = [];
        state.companies = [];
        state.staff = [];
        renderAll();
        setText(els.statusText, 'No project selected.');
        return;
      }
      if (els.projectCard) els.projectCard.classList.remove('hidden');
      setText(els.projectName, project.name);
      setText(els.projectNumber, project.number);
      setText(els.projectStatus, project.status);
      setText(els.projectManager, project.project_manager);
      setText(els.projectAddress, project.address_display || project.address);
      setText(els.projectDescription, project.description);
      setText(els.subtitle, `${project.number ? project.number + ' · ' : ''}${project.name || 'Project directory'}`);
      renderAll();
      const counts = state.counts || {};
      const summary = [
        `${counts.directory || state.directory.length || 0} linked`,
        `${counts.on_project || 0} on project`,
        `${counts.companies || state.companies.length || 0} companies`,
      ].join(' · ');
      setText(els.statusText, `Directory loaded · ${summary}`);
    }

    async function loadDirectory() {
      if (!projectId) {
        state.project = null;
        renderProject(null);
        setText(els.subtitle, 'Select a project using the project switcher.');
        return;
      }
      setText(els.statusText, 'Loading directory…');
      try {
        const response = await fetch(`/api/project-directory/${projectId}`, { credentials: 'same-origin' });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `Unable to load directory (${response.status})`);
        }
        state.project = payload.project || null;
        state.directory = payload.directory || payload.team_contacts || [];
        state.companies = payload.companies || [];
        state.staff = payload.staff || [];
        state.counts = payload.counts || {};
        renderProject(state.project);
      } catch (error) {
        if (els.projectCard) els.projectCard.classList.add('hidden');
        state.directory = [];
        state.companies = [];
        state.staff = [];
        renderAll();
        setText(els.statusText, error.message || 'Unable to load directory.');
      }
    }

    els.scopeFilters.forEach((button) => {
      button.addEventListener('click', () => {
        state.scope = button.getAttribute('data-pd-scope') || 'all_project';
        renderAll();
      });
    });
    els.viewFilters.forEach((button) => {
      button.addEventListener('click', () => {
        state.view = button.getAttribute('data-pd-view') || 'people';
        renderAll();
      });
    });
    if (els.search) {
      els.search.addEventListener('input', () => {
        state.search = els.search.value || '';
        renderAll();
      });
    }
    if (els.refresh) {
      els.refresh.addEventListener('click', loadDirectory);
    }

    loadDirectory();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initProjectDirectory);
  } else {
    initProjectDirectory();
  }
})();
