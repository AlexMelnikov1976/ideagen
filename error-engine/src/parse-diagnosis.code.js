// Code node "Parse Diagnosis"
// Вход: ответ Claude. Выход: сообщение Telegram + тело для Notion + флаги авто-ретрая.
const cfg = $('Config').first().json;
const ctx = $('Build Claude Request').first().json;
const resp = $json || {};

function esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

let diag;
try {
  const raw = (resp.content && resp.content[0] && resp.content[0].text) || '{}';
  const clean = raw.replace(/```json/gi, '').replace(/```/g, '').trim();
  diag = JSON.parse(clean);
} catch (err) {
  diag = {
    problem_type: 'unknown',
    root_cause: 'Не удалось распарсить ответ Claude — проверь вручную.',
    fix_summary: 'Открой выполнение в n8n и разбери ошибку руками.',
    fix_steps: [],
    can_auto_retry: false,
    severity: 'high',
    confidence: 0
  };
}

const now = new Date().toISOString();
const sev = String(diag.severity || 'medium').toLowerCase();
const emoji = sev === 'critical' ? '🚨' : sev === 'high' ? '🔴' : sev === 'medium' ? '🟡' : '🟢';
const steps = Array.isArray(diag.fix_steps) ? diag.fix_steps : [];

let msg = '';
msg += emoji + ' <b>Сбой n8n workflow</b>\n';
msg += '<b>Workflow:</b> ' + esc(ctx.workflow_name) + '\n';
msg += '<b>Нода:</b> ' + esc(ctx.failed_node) + '\n';
msg += '<b>Ошибка:</b> ' + esc(ctx.error_message) + '\n\n';
msg += '<b>Диагноз</b> (' + esc(diag.problem_type) + ', conf ' + esc(diag.confidence) + '):\n';
msg += esc(diag.root_cause) + '\n\n';
msg += '<b>Что сделать:</b> ' + esc(diag.fix_summary) + '\n';
if (steps.length) msg += steps.map(function (s, i) { return (i + 1) + '. ' + esc(s); }).join('\n') + '\n';
if (ctx.execution_url) msg += '\n<a href="' + ctx.execution_url + '">Открыть выполнение</a>';

const notion_body = JSON.stringify({
  parent: { database_id: cfg.NOTION_ERROR_LOG_DB_ID },
  properties: {
    'Name':       { title:     [{ text: { content: (ctx.workflow_name + ' — ' + ctx.error_message).slice(0, 200) } }] },
    'Workflow':   { rich_text: [{ text: { content: String(ctx.workflow_name).slice(0, 200) } }] },
    'Node':       { rich_text: [{ text: { content: String(ctx.failed_node).slice(0, 200) } }] },
    'Error':      { rich_text: [{ text: { content: String(ctx.error_message).slice(0, 1900) } }] },
    'Type':       { select:    { name: String(diag.problem_type || 'unknown').slice(0, 50) } },
    'Severity':   { select:    { name: sev } },
    'Auto retry': { checkbox:  !!diag.can_auto_retry },
    'When':       { date:      { start: now } }
  }
});

const autoRestart = String(cfg.AUTO_RESTART).toLowerCase() === 'true';

return [{ json: {
  chat_id: cfg.TELEGRAM_CHAT_ID,
  message: msg,
  notion_body: notion_body,
  can_auto_retry: !!diag.can_auto_retry,
  do_retry: (!!diag.can_auto_retry) && autoRestart,
  workflow_id: ctx.workflow_id,
  severity: sev
} }];
