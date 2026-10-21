export async function api(path, options={}) {
  const headers = {...options.headers, Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`};
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {...options, headers, credentials: 'omit'});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `请求失败 (${response.status})`);
  }
  return response;
}

export function node(tag, text, className='') {
  const element = document.createElement(tag);
  element.textContent = text;
  element.className = className;
  return element;
}

export function sources(citations) {
  const list = node('div', '', 'source-list');
  for (const source of citations) {
    const card = node('article', '', 'source-card');
    card.append(node('h3', `[${source.id}] ${source.title}`),
      node('p', `切片 ${source.chunk_index} · 偏移 ${source.start_offset}-${source.end_offset}`, 'source-meta'),
      node('pre', source.content || '', 'source-content'));
    list.append(card);
  }
  return list;
}
