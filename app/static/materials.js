const modal = document.querySelector('#upload-modal');
document.querySelector('#open-upload')?.addEventListener('click', () => { modal.hidden = false; });
document.querySelector('#close-upload')?.addEventListener('click', () => { modal.hidden = true; });
modal?.addEventListener('click', event => { if (event.target === modal) modal.hidden = true; });
document.querySelector('#search')?.addEventListener('input', event => {
  const query = event.target.value.toLocaleLowerCase();
  document.querySelectorAll('.item').forEach(item => { item.hidden = !item.textContent.toLocaleLowerCase().includes(query); });
});
document.querySelectorAll('.item').forEach(item => item.addEventListener('click', async () => {
  const response = await fetch(`/api/materials/${item.dataset.id}`, { credentials: 'same-origin' });
  if (!response.ok) { alert('无法读取该材料'); return; }
  const data = await response.json();
  document.querySelectorAll('.item').forEach(row => row.classList.toggle('active', row === item));
  const panel = document.querySelector('#reader-panel');
  panel.querySelector('#material-title').textContent = data.material.title;
  panel.querySelector('#material-content').textContent = data.content;
  panel.querySelector('#download-link').href = `/materials/${data.material.id}/download`;
}));
document.querySelector('#refresh-api')?.addEventListener('click', async () => {
  const response = await fetch('/api/materials', { credentials: 'same-origin' });
  if (!response.ok) { alert('获取材料失败'); return; }
  const data = await response.json();
  alert(`当前用户：${data.current_user.username}；班级：${data.current_user.class_id}；本班材料：${data.materials.length} 份。请在 Network 中查看此请求。`);
});
