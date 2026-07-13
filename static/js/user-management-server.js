/**
 * Case PM User Management — server-backed CRUD (replaces localStorage for user accounts).
 */
(function (global) {
  'use strict';

  async function fetchUsers() {
    const res = await fetch('/api/users', { credentials: 'same-origin' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Could not load users');
    }
    const json = await res.json();
    return json.users || [];
  }

  async function fetchCompanies() {
    const res = await fetch('/api/companies', { credentials: 'same-origin' });
    if (!res.ok) return [];
    const json = await res.json();
    return (json.companies || []).map(c => ({
      id: c.id,
      company_name: c.name || c.company_name,
      name: c.name || c.company_name,
      address: c.address || '',
      status: c.status || 'Active',
    }));
  }

  function buildUserPayload(formData) {
    return {
      firstName: formData.firstName,
      lastName: formData.lastName,
      email: formData.email,
      jobTitle: formData.jobTitle,
      department: formData.department,
      employeeId: formData.employeeId,
      licenseTier: formData.licenseTier,
      timezone: formData.timezone,
      locale: formData.locale,
      dateFormat: formData.dateFormat,
      officeLocation: formData.officeLocation,
      costCenter: formData.costCenter,
      hireDate: formData.hireDate,
      workPhoneExt: formData.workPhoneExt,
      linkedinUrl: formData.linkedinUrl,
      bio: formData.bio,
      reportsToUserId: formData.reportsToUserId,
      defaultProjectId: formData.defaultProjectId,
      emergencyContact: formData.emergencyContact,
      certifications: formData.certifications,
      notificationPrefs: formData.notificationPrefs,
      integrations: formData.integrations,
      mark_invite_sent: formData.mark_invite_sent,
      role: formData.role,
      company: formData.company,
      address: formData.address,
      phones: formData.phones,
      status: formData.status,
      accessEnabled: formData.accessEnabled,
      twoFactorEnabled: formData.twoFactorEnabled,
      notes: formData.notes,
      tempPassword: formData.tempPassword || undefined,
      permissions: formData.permissions,
      permissions_v2: formData.permissions,
    };
  }

  async function uploadHrDocument(userId, formData) {
    const res = await fetch(`/api/users/${userId}/hr-documents`, {
      method: 'POST',
      credentials: 'same-origin',
      body: formData,
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Upload failed');
    return json;
  }

  async function fetchUserAuditLog(userId, limit = 100) {
    const res = await fetch(`/api/users/${userId}/audit-log?limit=${limit}`, { credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not load activity');
    return json;
  }

  async function uploadProfileImage(userId, file) {
    const fd = new FormData();
    fd.append('photo', file);
    const res = await fetch(`/api/users/${userId}/profile-image`, {
      method: 'POST',
      credentials: 'same-origin',
      body: fd,
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Photo upload failed');
    return json;
  }

  async function createUser(payload) {
    const res = await fetch('/api/users', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Create failed');
    return json;
  }

  async function updateUser(userId, payload) {
    const res = await fetch(`/api/users/${userId}`, {
      method: 'PUT',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Update failed');
    return json;
  }

  async function deleteUserById(userId) {
    const res = await fetch(`/api/users/${userId}`, {
      method: 'DELETE',
      credentials: 'same-origin',
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Delete failed');
    return json;
  }

  async function resetPassword(userId, password) {
    const res = await fetch(`/api/users/${userId}/reset-password`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(password ? { password } : {}),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Password reset failed');
    return json;
  }

  global.CasePMUserMgmtServer = {
    fetchUsers,
    fetchCompanies,
    buildUserPayload,
    createUser,
    updateUser,
    deleteUserById,
    resetPassword,
    uploadHrDocument,
    fetchUserAuditLog,
    uploadProfileImage,
  };
})(window);
