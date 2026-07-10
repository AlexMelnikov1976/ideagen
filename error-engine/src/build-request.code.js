// Code node "Build Claude Request"
// Вход: payload от Error Trigger. Выход: контекст ошибки + тело запроса к Claude.
const cfg = $('Config').first().json;
const e = $json || {};

const wf = e.workflow || {};
const ex = e.execution || {};
let err = ex.error || {};
if (typeof err === 'string') err = { message: err };

const ctx = {
  workflow_name: wf.name || 'unknown',
  workflow_id: String(wf.id || ''),
  failed_node: ex.lastNodeExecuted || 'unknown',
  error_name: err.name || '',
  error_message: err.message || JSON.stringify(err).slice(0, 500),
  error_stack: String(err.stack || '').slice(0, 1500),
  execution_url: ex.url || '',
  mode: ex.mode || ''
};

const prompt =
  'Ты — SRE-инженер, диагностирующий сбой n8n workflow. ' +
  'Верни СТРОГО валидный JSON без markdown и без пояснений, по схеме:\n' +
  '{\n' +
  '  "problem_type": "transient|config|logic|auth|data|external_api",\n' +
  '  "root_cause": "1-2 предложения на русском",\n' +
  '  "fix_summary": "что сделать, 1-2 предложения",\n' +
  '  "fix_steps": ["шаг 1", "шаг 2"],\n' +
  '  "can_auto_retry": true,\n' +
  '  "severity": "low|medium|high|critical",\n' +
  '  "confidence": 0.0\n' +
  '}\n' +
  'can_auto_retry=true только если ошибка временная (rate limit, timeout, 5xx, сеть). ' +
  'Для logic/config/auth/data ставь false.\n\n' +
  'Данные об ошибке:\n' + JSON.stringify(ctx, null, 2);

const claude_body = JSON.stringify({
  model: cfg.CLAUDE_MODEL,
  max_tokens: 1024,
  messages: [{ role: 'user', content: prompt }]
});

return [{ json: Object.assign({}, ctx, {
  anthropic_api_key: cfg.ANTHROPIC_API_KEY,
  claude_body: claude_body
}) }];
