# Error Engine — авто-диагностика и восстановление n8n

AI-инженер, который следит за сбоями во всех твоих n8n workflow, диагностирует их через Claude и восстанавливает.
Источник идеи: Игорь Зуевич «ИИ инженер для n8n» + Weekly Advisor #1 (05.07.2026).

**Что делает:** любой сбой → Claude Haiku ставит диагноз → алерт в Telegram с готовым фиксом → лог в Notion → авто-ретрай для временных ошибок.

**ROI:** простой критичных автоматизаций падает с часов до 2–5 минут; ~8–12 ч/мес экономии на ручном разборе.

---

## Схема

```
Error Trigger (ловит сбой любого workflow)
    ↓
Config (ключи и флаги)
    ↓
Build Claude Request (собирает контекст ошибки)
    ↓
Claude Diagnose (Haiku 4.5 → JSON-диагноз)
    ↓
Parse Diagnosis
    ├──→ Notion Error Log (запись в таблицу аудита)
    └──→ Telegram Alert (сообщение с диагнозом и шагами фикса)
            ↓
        Авто-ретрай?  (только transient + AUTO_RESTART=true)
            ↓ true
        Перезапустить workflow
```

---

## Что это делает и чего НЕ делает

**Делает (MVP, безопасно):**
- Мгновенно детектит сбой любого workflow, где выставлен этот Error Workflow.
- Ставит диагноз: тип проблемы, причина, конкретные шаги фикса, severity, уверенность.
- Шлёт форматированный алерт в Telegram и пишет строку в Notion «Error Log».
- Для **временных** ошибок (rate limit, timeout, 5xx, сеть) может авто-перезапустить упавший workflow.

**НЕ делает (фаза 2):**
- Не переписывает код упавшей ноды и не передеплоит workflow сам — для этого нужен доступ к n8n REST API на запись (нода n8n API / MCP). Это отдельный этап под guardrails.
- Для `logic/config/auth/data` ошибок авто-ретрай выключен намеренно — они не чинятся повтором, только твоим фиксом по шагам из алерта.

---

## Установка (20 минут)

### 1. Импортируй workflow
n8n → **Import from File** → `error-handler.n8n.json`.

### 2. Заполни ноду `Config`
| Ключ | Значение |
|------|----------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` (по умолчанию) |
| `TELEGRAM_CHAT_ID` | твой личный chat id |
| `NOTION_API_KEY` | `secret_...` (та же интеграция, что в IdeaGen) |
| `NOTION_ERROR_LOG_DB_ID` | id базы «Error Log» (см. шаг 3) |
| `AUTO_RESTART` | `false` — включи `true`, когда протестируешь |

### 3. Создай Notion Database «Error Log»
Поля (важно точное имя и тип):
- `Name` (title)
- `Workflow` (text)
- `Node` (text)
- `Error` (text)
- `Type` (select)
- `Severity` (select)
- `Auto retry` (checkbox)
- `When` (date)

Дай доступ к базе своей Notion-интеграции.

### 4. Подключи Telegram-креды
На ноде `Telegram Alert` → Credentials → токен бота из @BotFather.

### 5. Назначь этот workflow как Error Workflow
Для КАЖДОГО боевого workflow (Weekly Automation Advisor, IdeaGen, Chicko Analytics):
**Settings воркфлоу → Error Workflow → выбери «Error Engine…»**.

### 6. Проверь
Временно сломай тестовый workflow (например, битый URL в HTTP-ноде) → запусти → в течение минуты должен прийти Telegram-алерт с диагнозом и появиться строка в Notion «Error Log».

---

## Безопасность авто-ретрая
- Держи `AUTO_RESTART=false`, пока не увидишь на реальных ошибках, что диагнозы адекватны.
- Ретрай срабатывает только когда Claude пометил ошибку как временную (`can_auto_retry=true`) **и** `AUTO_RESTART=true`.
- Ретрай одноразовый на событие (перезапуск исходного workflow). Если сбой устойчивый — он снова упадёт и снова придёт алерт, но без бесконечного цикла в этом workflow.

---

## Стоимость
Claude Haiku на диагноз ошибки — доли цента за инцидент. При десятках ошибок в месяц — считанные центы.

Исходники code-нод для правок — в `src/`.
