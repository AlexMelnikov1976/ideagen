# IdeaGen — YouTube AI Ideas to Notion

Автоматический мониторинг YouTube-каналов → анализ через Claude → лучшие идеи в Notion.

**Стоимость:** ~$0.04/день
**Время настройки:** 20 минут
**Требует:** n8n (self-hosted или cloud), аккаунты в Notion и Anthropic

---

## Что делает

1. Каждые 2 дня проверяет новые видео на 13+ YouTube-каналах про AI и бизнес
2. Фильтрует Shorts и дубли (уже сохранённые пропускает)
3. Извлекает транскрипт каждого видео
4. Claude Haiku анализирует содержание и ставит оценку 1–10
5. Видео с оценкой 7+ сохраняет в Notion с кратким резюме

---

## Схема

```
Schedule (каждые 2 дня)
    ↓
YouTube Search API → список новых видео
    ↓
Dedupe → проверка что ещё не в Notion
    ↓
Supadata API → транскрипт видео
    ↓
Claude Haiku → анализ + оценка 1–10
    ↓
Notion → сохранить (только 7+)
    ↓
Telegram → краткий дайджест (опционально)
```

---

## Быстрый старт

### 1. Импортируй воркфлоу

В n8n: **Settings → Import workflow** → загрузи `ideagen_template.json`

### 2. Получи API ключи

| Ключ | Где взять | Стоимость |
|------|-----------|-----------|
| YouTube Data API v3 | console.cloud.google.com | Бесплатно (10k req/день) |
| Anthropic API | console.anthropic.com | ~$0.03/день |
| Notion API | notion.so/my-integrations | Бесплатно |
| Supadata API | supadata.ai | Бесплатно (план Free) |

### 3. Настрой ноду "API Keys and Config"

```json
YOUTUBE_API_KEY:    "AIza..."
ANTHROPIC_API_KEY:  "sk-ant-..."
NOTION_API_KEY:     "secret_..."
NOTION_DATABASE_ID: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
TELEGRAM_CHAT_ID:   "-100xxxxxxxxxx"  (опционально)
```

### 4. Создай Notion Database

Нужны поля:
- `Name` (title)
- `Video ID` (text) — для дедупликации
- `Score` (number)
- `Channel` (text)
- `Published` (date)
- `Summary` (text)

### 5. Настрой каналы

В поле `CHANNELS` замени на свои YouTube-каналы:

```json
[
  {"id": "UCxxxxxxxx", "name": "Название канала"},
  {"id": "UCxxxxxxxx", "name": "Другой канал"}
]
```

Найти ID канала: зайди на канал → правая кнопка → "Просмотр кода страницы" → ищи `channelId`

### 6. Запусти вручную и проверь

Нажми **Test workflow** → убедись что идеи появились в Notion.

---

## Параметры конфигурации

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `PUBLISHED_DAYS_AGO` | 3 | Смотреть видео не старше N дней |
| `MAX_VIDEOS` | 10 | Максимум видео за один запуск |
| `MIN_SCORE` | 7 | Минимальная оценка для сохранения |
| `TRANSCRIPT_LANG` | ru | Язык транскрипта |

---

## Вопросы и поддержка

Telegram-канал автора: [@kraft_ai](https://t.me/kraft_ai)
