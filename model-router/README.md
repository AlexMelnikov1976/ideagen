# Model Router — умный выбор LLM (GLM ↔ Claude)

Переиспользуемый под-workflow: заменяет прямые вызовы Claude во всех твоих воркфлоу.
Простые задачи → дешёвый Claude Haiku, «умные» → GLM 5.2 (в 3–5× дешевле).
Источник: Weekly Advisor #2 (05.07) + конспект «Sonnet 5» (GLM $4.88/81% против Sonnet $9.40/55%).

**Экономия:** ~$30 → $10–12/мес на LLM без потери качества.

---

## Как работает

```
Другой workflow ──(Execute Workflow)──▶ Model Router
                                          │
   When Called → Config → Model Router → LLM Call → Normalize Response
                            (выбор       (generic   (единый формат
                             модели)      HTTP)       {text, provider, model})
```

Вызывающий workflow передаёт `{ task_type, prompt, system?, max_tokens? }`, получает обратно `{ text, provider, model, ok, error }`.

### Правило маршрутизации
- **Дешёвые задачи** (`extract, dedupe, classify, parse, filter, format, translate`) → Claude Haiku.
- **Всё остальное** (`analyze, generate, ideas, summary, …`) → GLM 5.2 через Z.ai.
- Правило меняется в одном месте — массив `CHEAP` в ноде `Model Router`.

---

## Установка

1. Импортируй `model-router.n8n.json` (вставь JSON на холст n8n, Ctrl+V).
2. В ноде `Config` впиши:
   - `ANTHROPIC_API_KEY`, `ZAI_API_KEY`
   - `ZAI_BASE_URL` — **проверь актуальный адрес** OpenAI-совместимого API Z.ai (в шаблоне `https://api.z.ai/api/paas/v4`; у Zhipu/Z.ai путь может отличаться — сверься в личном кабинете).
   - `GLM_MODEL` — точное имя модели у провайдера (напр. `glm-5.2`).
3. Сохрани workflow.

### Как подключить к существующему воркфлоу (IdeaGen / Weekly Advisor)
Заменяешь связку «Подготовить запрос к Claude → HTTP Анализ Claude» на одну ноду **Execute Workflow**, которая зовёт `Model Router` и передаёт:
- `task_type` = `analyze` (для генерации идей) или `extract` (для парсинга)
- `prompt` = текст запроса
- `system` = системная инструкция (опц.)

Дальше работаешь с `{{ $json.text }}` как раньше с ответом Claude.

---

## Отказоустойчивость (fallback)
`LLM Call` стоит в режиме `neverError`, поэтому пустой/ошибочный ответ не роняет процесс — `Normalize Response` вернёт `ok:false` и `error`. В вызывающем воркфлоу добавь после Execute Workflow ветку **IF `ok == false`** → второй вызов `Model Router` с тем же `prompt`, но заведомо на Claude (например, форсни `task_type:'extract'` или заведи параметр `force_provider`). Так при недоступности Z.ai работа продолжится на Claude.

---

## Экономика
| Задача | Куда идёт | Порядок цены |
|---|---|---|
| Извлечение/парсинг | Claude Haiku | доли цента |
| Анализ/генерация идей | GLM 5.2 | в 3–5× дешевле Claude |

При объёме IdeaGen + Weekly Advisor + Chicko ожидаемо **$10–12/мес вместо $30**.

Исходники code-нод — в `src/`.
