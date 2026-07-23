(function () {
  const ctx = window.CASEPM_PROJECT_DIRECTORY_CTX || {};
  const projectId = ctx.projectId;
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
    contactCount: document.getElementById('pdContactCount'),
    statusText: document.getElementById('pdStatusText'),
    refresh: document.getElementById('pdRefresh'),
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

  function renderContacts(contacts) {
    const rows = Array.isArray(contacts) ? contacts : [];
    if (!rows.length) {
      els.contactsBody.innerHTML = '<tr><td colspan="5" class="pd-empty">No team contacts have been added for this project yet.</td></tr>';
      setText(els.contactCount, '0 contacts');
      return;
    }
    els.contactsBody.innerHTML = rows.map((contact) => {
      const role = contact.role_label || contact.role || 'Contact';
      const email = contact.email
        ? `<a href="mailto:${esc(contact.email)}" class="text-sky-400 hover:text-sky-300">${esc(contact.email)}</a>`
        : '—';
      const phone = contact.phone
        ? `<a href="tel:${esc(contact.phone)}" class="text-sky-400 hover:text-sky-300">${esc(contact.phone)}</a>`
        : '—';
      return `<tr>
        <td class="text-zinc-300">${esc(role)}</td>
        <td class="text-white">${esc(contact.name || '—')}</td>
        <td class="text-zinc-300">${esc(contact.firm || '—')}</td>
        <td>${email}</td>
        <td>${phone}</td>
      </tr>`;
    }).join('');
    setText(els.contactCount, `${rows.length} contact${rows.length === 1 ? '' : 's'}`);
  }

  function renderProject(project) {
    if (!project) {
      els.projectCard.classList.add('hidden');
      renderContacts([]);
      setText(els.statusText, 'No project selected.');
      return;
    }
    els.projectCard.classList.remove('hidden');
    setText(els.projectName, project.name);
    setText(els.projectNumber, project.number);
    setText(els.projectStatus, project.status);
    setText(els.projectManager, project.project_manager);
    setText(els.projectAddress, project.address_display || project.address);
    setText(els.projectDescription, project.description);
    setText(els.subtitle, `${project.number ? project.number + ' · ' : ''}${project.name || 'Project directory'}`);
    renderContacts(project.team_contacts || []);
    setText(els.statusText, 'Directory loaded.');
  }

  async function loadDirectory() {
    if (!projectId) {
      renderProject(null);
      setText(els.subtitle, 'Select a project using the project switcher.');
      return;
    }
    setText(els.statusText, 'Loading directory…');
    try {
      const response = await fetch(`/api/project-directory/${projectId}`, { credentials: 'same-origin' });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `Unable to load directory (${response.status})`);
      }
      const payload = await response.json();
      renderProject(payload.project || null);
    } catch (error) {
      renderProject(null);
      setText(els.statusText, error.message || 'Unable to load directory.');
    }
  }

  if (els.refresh) {
    els.refresh.addEventListener('click', loadDirectory);
  }

  loadDirectory();
})();
