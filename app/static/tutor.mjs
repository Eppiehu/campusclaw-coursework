import {api, node, sources} from './api.mjs';
import {streamEvents} from './sse.mjs';
const select = document.querySelector('#agent-select');
const messages = document.querySelector('#messages');
const error = document.querySelector('#stream-error');
const send = document.querySelector('#send-message');
let conversationId = null;
let busy = false;

async function refreshList() {
  const data = await (await api('/api/conversations')).json();
  const list = document.querySelector('#conversation-list');
  list.replaceChildren();
  for (const conversation of data.conversations) {
    const button = node('button', conversation.title, 'item');
    button.type = 'button';
    button.onclick = () => { if (!busy) loadConversation(conversation.id).catch(showError); };
    list.append(button);
  }
}

function showError(caught) { error.textContent = caught.message; }
function bubble(role, content='') {
  const article = node('article', '', `chat-bubble ${role}`);
  const body = node('p', content, 'chat-answer');
  article.append(node('div', role === 'user' ? '你' : '助手', 'chat-label'), body);
  messages.append(article);
  return {article, body};
}

async function loadConversation(identifier) {
  const data = await (await api(`/api/conversations/${identifier}`)).json();
  conversationId = identifier;
  select.disabled = true;
  document.querySelector('#locked-agent').textContent = `本会话固定使用助手 #${data.conversation.agent_id}`;
  document.querySelector('#conversation-title').textContent = data.conversation.title;
  messages.replaceChildren();
  for (const message of data.messages) {
    const view = bubble(message.role, message.content);
    if (message.skill_name) view.article.append(node('span', `技能：${message.skill_name}`, 'pill'));
    if (message.citations?.length) view.article.append(sources(message.citations));
  }
  send.disabled = false;
}

document.querySelector('#new-conversation').onclick = async () => {
  if (busy) return;
  error.textContent = '';
  if (select.disabled) {
    select.disabled = false;
    conversationId = null;
    send.disabled = true;
    document.querySelector('#locked-agent').textContent = '选择助手后，再点一次“新建会话”。';
    return;
  }
  if (!select.value) { error.textContent = '请先选择已启用助手'; return; }
  try {
    const data = await (await api('/api/conversations', {method: 'POST', body: JSON.stringify({agent_id: Number(select.value)})})).json();
    await loadConversation(data.conversation.id);
    await refreshList();
  } catch (caught) { showError(caught); }
};

document.querySelector('#chat-form').onsubmit = async event => {
  event.preventDefault();
  if (!conversationId || busy) return;
  const input = document.querySelector('#chat-question');
  const question = input.value.trim();
  if (!question) return;
  error.textContent = '';
  busy = true; send.disabled = true;
  bubble('user', question);
  const assistant = bubble('assistant');
  let finished = false;
  try {
    const response = await api(`/api/conversations/${conversationId}/messages`, {method: 'POST', body: JSON.stringify({question})});
    for await (const frame of streamEvents(response.body)) {
      if (frame.event === 'meta') {
        assistant.article.prepend(node('span', frame.data.skill ? `技能：${frame.data.skill}` : '未选用技能', 'pill'));
        assistant.article.append(sources(frame.data.citations || []));
      } else if (frame.event === 'delta') {
        assistant.body.textContent += frame.data.text;
      } else if (frame.event === 'done') {
        assistant.article.dataset.messageId = frame.data.message_id;
        finished = true;
      } else if (frame.event === 'error') {
        finished = true;
        throw new Error(frame.data.error || '生成中断');
      }
    }
    if (!finished) throw new Error('连接提前结束，请重新打开会话检查已保存的内容');
    input.value = '';
    await refreshList();
  } catch (caught) { showError(caught); }
  finally { busy = false; send.disabled = false; }
};

try {
  const data = await (await api('/api/agents')).json();
  for (const agent of data.agents.filter(item => item.enabled)) {
    const option = node('option', agent.name); option.value = agent.id; select.append(option);
  }
  await refreshList();
} catch (caught) { showError(caught); }
