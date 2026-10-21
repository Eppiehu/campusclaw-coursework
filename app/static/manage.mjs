import {api, node} from './api.mjs';
const error = document.querySelector('#manage-error');
const skillForm = document.querySelector('#skill-form');
const agentForm = document.querySelector('#agent-form');
const templateForm = document.querySelector('#template-form');
let allAgents = [];

function button(label, action) {
  const element = node('button', label, 'outline'); element.type = 'button';
  element.onclick = () => action().catch(showError); return element;
}
function showError(caught) { error.textContent = caught.message; }
function selectOptions(selector, items) {
  const select = document.querySelector(selector); select.replaceChildren();
  for (const item of items) { const option = node('option', item.name || item.title); option.value = item.id; select.append(option); }
}
function selected(selector) { return [...document.querySelector(selector).selectedOptions].map(option => Number(option.value)); }

async function refresh() {
  const [skills, agents, materials, templates, mcp] = await Promise.all(['/api/skills','/api/agents','/api/materials','/api/prompt-templates','/api/mcp/tools'].map(async path => (await api(path)).json()));
  allAgents = agents.agents;
  selectOptions('#agent-skills', skills.skills); selectOptions('#agent-materials', materials.materials);
  selectOptions('#agent-template', templates.templates.filter(item => item.enabled));
  const blank = node('option','使用下方角色设定'); blank.value=''; document.querySelector('#agent-template').prepend(blank); document.querySelector('#agent-template').value='';
  selectOptions('#agent-tools', mcp.tools.map(tool => ({id:tool.name, name:`${tool.name} · ${tool.description || ''}`})));
  const templateList = document.querySelector('#template-list'); templateList.replaceChildren();
  for (const template of templates.templates) {
    const row = node('div','','config-row'); row.append(node('strong',`${template.name} · ${template.enabled ? '启用' : '停用'}`));
    row.append(button('编辑',async () => {
      document.querySelector('#template-id').value=template.id; document.querySelector('#template-name').value=template.name;
      document.querySelector('#template-content').value=template.content; document.querySelector('#template-enabled').checked=template.enabled;
    }),button(template.enabled?'停用':'启用',async () => {await api(`/api/prompt-templates/${template.id}`,{method:'PATCH',body:JSON.stringify({enabled:!template.enabled})});await refresh();}),
    button('删除',async () => {await api(`/api/prompt-templates/${template.id}`,{method:'DELETE'});await refresh();}));
    templateList.append(row);
  }
  const skillList = document.querySelector('#skill-list'); skillList.replaceChildren();
  for (const skill of skills.skills) {
    const row = node('div', '', 'config-row'); row.append(node('strong', `${skill.name} · ${skill.enabled ? '启用' : '停用'}`));
    row.append(button('替换文件', async () => { document.querySelector('#skill-id').value = skill.id; document.querySelector('#skill-file').click(); }),
      button(skill.enabled ? '停用' : '启用', async () => { await api(`/api/skills/${skill.id}`, {method:'PATCH',body:JSON.stringify({enabled:!skill.enabled})}); await refresh(); }),
      button('删除', async () => { await api(`/api/skills/${skill.id}`, {method:'DELETE'}); await refresh(); }));
    skillList.append(row);
  }
  const agentList = document.querySelector('#agent-list'); agentList.replaceChildren();
  for (const agent of allAgents) {
    const row = node('div', '', 'config-row'); row.append(node('strong', `${agent.name} · ${agent.enabled ? '启用' : '停用'}`));
    row.append(button('编辑', async () => {
      document.querySelector('#agent-id').value = agent.id; document.querySelector('#agent-name').value = agent.name;
      document.querySelector('#agent-prompt').value = agent.prompt; document.querySelector('#agent-enabled').checked = agent.enabled;
      const templateSelect = document.querySelector('#agent-template');
      if (agent.prompt_template_id && ![...templateSelect.options].some(option=>option.value===String(agent.prompt_template_id))) {
        const option=node('option','当前已停用模板（使用角色设定）'); option.value=agent.prompt_template_id;templateSelect.append(option);
      }
      templateSelect.value = agent.prompt_template_id || '';
      for (const option of document.querySelector('#agent-tools').options) option.selected=agent.mcp_tools.includes(option.value);
      for (const [selector, ids] of [['#agent-skills',agent.skill_ids],['#agent-materials',agent.material_ids]]) {
        for (const option of document.querySelector(selector).options) option.selected = ids.includes(Number(option.value));
      }
    }), button(agent.enabled ? '停用' : '启用', async () => { await api(`/api/agents/${agent.id}`, {method:'PATCH',body:JSON.stringify({enabled:!agent.enabled})}); await refresh(); }),
      button('删除', async () => {await api(`/api/agents/${agent.id}`, {method:'DELETE'});await refresh();}));
    agentList.append(row);
  }
}
skillForm.onsubmit = async event => {
  event.preventDefault(); error.textContent = '';
  const file = document.querySelector('#skill-file').files[0];
  const id = document.querySelector('#skill-id').value;
  const body = new FormData(); body.append('file',file);
  try { await api(id ? `/api/skills/${id}` : '/api/skills', {method:id?'PUT':'POST',body}); skillForm.reset(); await refresh(); }
  catch (caught) { showError(caught); }
};
agentForm.onsubmit = async event => {
  event.preventDefault(); error.textContent = '';
  const id = document.querySelector('#agent-id').value;
  const data = {name:document.querySelector('#agent-name').value,prompt:document.querySelector('#agent-prompt').value,
    enabled:document.querySelector('#agent-enabled').checked,skill_ids:selected('#agent-skills'),material_ids:selected('#agent-materials'),
    prompt_template_id:document.querySelector('#agent-template').value ? Number(document.querySelector('#agent-template').value) : null,
    mcp_tools:[...document.querySelector('#agent-tools').selectedOptions].map(option=>option.value)};
  try { await api(id?`/api/agents/${id}`:'/api/agents',{method:id?'PUT':'POST',body:JSON.stringify(data)}); agentForm.reset(); document.querySelector('#agent-id').value=''; await refresh(); }
  catch (caught) { showError(caught); }
};
document.querySelector('#reset-agent').onclick = () => {agentForm.reset();document.querySelector('#agent-id').value='';};
document.querySelector('#reset-skill').onclick = () => {skillForm.reset();document.querySelector('#skill-id').value='';};
templateForm.onsubmit = async event => {
  event.preventDefault(); error.textContent='';
  const id=document.querySelector('#template-id').value;
  const data={name:document.querySelector('#template-name').value,content:document.querySelector('#template-content').value,enabled:document.querySelector('#template-enabled').checked};
  try {await api(id?`/api/prompt-templates/${id}`:'/api/prompt-templates',{method:id?'PUT':'POST',body:JSON.stringify(data)});templateForm.reset();document.querySelector('#template-id').value='';await refresh();}
  catch(caught){showError(caught);}
};
document.querySelector('#reset-template').onclick=()=>{templateForm.reset();document.querySelector('#template-id').value='';};
refresh().catch(showError);
