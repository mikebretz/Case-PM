(function () {
  'use strict';

  const form = document.getElementById('prRegisterForm');
  const msg = document.getElementById('prRegisterMsg');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (msg) msg.textContent = 'Submitting…';
    const fd = new FormData(form);
    const specialties = [...form.querySelectorAll('input[name="specialty"]:checked')].map((el) => el.value);
    fd.delete('specialty');
    fd.append('specialties', JSON.stringify(specialties));
    try {
      const res = await fetch('/api/public/bidder-network/register', { method: 'POST', body: fd, credentials: 'same-origin' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || 'Registration failed');
      if (msg) msg.textContent = data.message || 'Thank you — your application is pending review.';
      form.reset();
    } catch (err) {
      if (msg) msg.textContent = err.message || 'Could not submit. Please try again.';
    }
  });
})();
