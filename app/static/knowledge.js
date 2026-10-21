const tabs = document.querySelectorAll('.knowledge-tab');
const form = document.querySelector('#knowledge-form');
const output = document.querySelector('#knowledge-output');
const error = document.querySelector('#knowledge-error');
const submit = document.querySelector('#knowledge-submit');
let mode = 'search';


tabs.forEach(tab => tab.addEventListener('click', () => {
  mode = tab.dataset.mode;
  tabs.forEach(item => item.classList.toggle('active', item === tab));
  document.querySelector('#question-label').textContent = mode === 'ask' ? '向本班知识库提问' : '检索本班知识';
  submit.textContent = mode === 'ask' ? '提问' : '检索';
  error.textContent = '';
  output.replaceChildren();
}));

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderSources(sources) {
  const list = element('div', 'source-list');
  sources.forEach(source => {
    const card = element('article', 'source-card');
    card.append(element('h3', '', `[${source.id ?? source.rank}] ${source.title}`));
    card.append(element('p', 'source-meta', `切片 ${source.chunk_index} · 偏移 ${source.start_offset}–${source.end_offset} · score ${source.score.toFixed(3)}`));
    card.append(element('pre', 'source-content', source.content));
    list.append(card);
  });
  return list;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const question = form.elements.question.value.trim();
  const token = localStorage.getItem('access_token');
  error.textContent = '';
  if (!token) { error.textContent = '缺少 Token，请重新登录。'; return; }
  submit.disabled = true;
  output.replaceChildren(element('p', 'muted', '正在处理…'));
  try {
    const response = await fetch(`/api/knowledge/${mode}`, {
      method: 'POST',
      credentials: 'omit',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(mode === 'ask' ? { question } : { query: question, mode: document.querySelector('#search-mode').value })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '请求失败');
    output.replaceChildren();
    if (mode === 'ask') {
      output.append(element('div', 'chat-label', '你'));
      output.append(element('p', 'chat-question', question));
      output.append(element('div', 'chat-label', '依据回答'));
      output.append(element('p', 'chat-answer', data.answer));
      if (data.sources.length) output.append(renderSources(data.sources));
    } else {
      output.append(element('h2', '', `检索结果 · ${data.results.length} 条`));
      output.append(data.results.length ? renderSources(data.results) : element('p', 'muted', '本班资料中没有找到相关内容。'));
    }
  } catch (caught) {
    error.textContent = caught.message;
    output.replaceChildren();
  } finally {
    submit.disabled = false;
  }
});
