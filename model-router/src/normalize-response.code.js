// Code node "Normalize Response"
// Приводит ответ разных провайдеров к единому виду { text, provider, model }.
// Anthropic: content[0].text | OpenAI/Z.ai: choices[0].message.content
const meta = $('Model Router').first().json;
const r = $json || {};

let text = '';
if (meta.provider === 'anthropic') {
  text = (r.content && r.content[0] && r.content[0].text) || '';
} else {
  text = (r.choices && r.choices[0] && r.choices[0].message && r.choices[0].message.content) || '';
}

// Если провайдер вернул ошибку в теле — прокинем её, чтобы вызывающий workflow увидел.
const errMsg = (r.error && (r.error.message || r.error)) || (r.message && !text ? r.message : '');

return [{ json: {
  text: text,
  provider: meta.provider,
  model: meta.model,
  task_type: meta.task_type,
  ok: !!text,
  error: text ? '' : String(errMsg || 'empty response')
} }];
