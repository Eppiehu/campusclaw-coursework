document.querySelectorAll('form[action$="/logout"]').forEach(form => {
  form.addEventListener('submit', async event => {
    const token = localStorage.getItem('access_token');
    if (!token) return;
    event.preventDefault();
    try {
      const response = await fetch('/api/logout', {method: 'POST', credentials: 'omit',
        headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'}, body: '{}'});
      if (!response.ok && response.status !== 401) throw new Error('登出失败，请重试');
      localStorage.removeItem('access_token');
      // Also clear the old SSR Session through its original endpoint.
      form.submit();
    } catch (error) { alert(error.message); }
  });
});
