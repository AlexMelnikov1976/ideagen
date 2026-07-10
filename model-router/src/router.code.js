// Code node "Model Router"
// Вход (от Execute Workflow Trigger): { task_type, prompt, system?, max_tokens? }
// Выход: провайдер, url, заголовки и готовое тело запроса — их подхватывает generic HTTP-нода.
const cfg = $('Config').first().json;
const inp = $json || {};

const taskType = String(inp.task_type || 'analyze').toLowerCase();
const prompt = String(inp.prompt || '');
const system = String(inp.system || '');
const maxTokens = Number(inp.max_tokens) || 1024;

// Дешёвые механические задачи → Claude Haiku. Всё «умное» → GLM (дешевле в 3-5x).
const CHEAP = ['extract', 'dedupe', 'classify', 'parse', 'filter', 'format', 'translate'];
const useGlm = !CHEAP.includes(taskType);

let provider, url, model, body;
let h_x_api_key = '';
let h_authorization = '';

if (useGlm) {
  provider = 'zai';
  url = String(cfg.ZAI_BASE_URL).replace(/\/+$/, '') + '/chat/completions';
  model = cfg.GLM_MODEL;
  h_authorization = 'Bearer ' + cfg.ZAI_API_KEY;
  const messages = [];
  if (system) messages.push({ role: 'system', content: system });
  messages.push({ role: 'user', content: prompt });
  body = JSON.stringify({ model: model, max_tokens: maxTokens, temperature: 0.7, messages: messages });
} else {
  provider = 'anthropic';
  url = 'https://api.anthropic.com/v1/messages';
  model = cfg.HAIKU_MODEL;
  h_x_api_key = cfg.ANTHROPIC_API_KEY;
  const payload = { model: model, max_tokens: maxTokens, messages: [{ role: 'user', content: prompt }] };
  if (system) payload.system = system;
  body = JSON.stringify(payload);
}

return [{ json: {
  provider: provider,
  url: url,
  model: model,
  body: body,
  h_x_api_key: h_x_api_key,
  h_authorization: h_authorization,
  task_type: taskType
} }];
