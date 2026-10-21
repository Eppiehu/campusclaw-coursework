document.querySelector('#login-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const error = document.querySelector('#login-error');
  button.disabled = true;
  error.textContent = '';
  const previousToken = localStorage.getItem('access_token');

  try {
    const response = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(previousToken ? { Authorization: `Bearer ${previousToken}` } : {}) },
      credentials: 'same-origin',
      body: JSON.stringify({
        username: form.elements.username.value,
        password: form.elements.password.value
      })
    });
    const result = await response.json();
    if (!response.ok) {
      error.textContent = result.error || '登录失败';
      return;
    }
    localStorage.setItem('access_token', result.token);
    window.location.href = '/materials';
  } catch {
    error.textContent = '登录请求失败，请重试';
  } finally {
    button.disabled = false;
  }
});
