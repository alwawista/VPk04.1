# ИИ-сервис первичной обработки обращений

Учебный MVP: классификация обращений, черновик ответа, эскалация оператору, журнал в SQLite.

**Кейс:** менеджеры тратят время на первичную сортировку → сервис автоматизирует triage и сохраняет аудит.

## Что реализовано

| Требование | Статус |
|---|---|
| `POST /triage` — контракт JSON | ✅ |
| `POST /lead` — алиас для совместимости | ✅ |
| Категории: billing, support, complaint, other | ✅ |
| Поля ответа: category, draft_reply, confidence, escalate | ✅ |
| SQLite-таблица `tickets` с аудитом | ✅ |
| Секреты через `.env` (`load_dotenv`) | ✅ |
| Лимит запросов на `client_id` | ✅ |
| Fallback при сбое LLM → escalate + шаблон оператору | ✅ |
| Валидация входа (text 1–2000 символов) | ✅ |
| Docker / docker-compose | ✅ |
| Mock LLM для демо без расходов | ✅ |
| Веб-UI демо (`GET /`) | ✅ |

## Архитектура (5 блоков)

```
Клиент → FastAPI (/triage) → Rate limit → SQLite (аудит)
                              ↓
                         LLM (mock/OpenAI)
                              ↓
                    Валидатор безопасности → Ответ JSON
                              ↓
                    При сбое → escalate + «передано оператору»
```

## Быстрый старт (5–10 минут)

### 1. Зависимости

```powershell
cd D:\vibe-coding\VPk04.1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

### 2. Переменные окружения

Скопируйте `EnvExample` в `.env` и при необходимости измените значения. Для демо достаточно:

```env
LLM_PROVIDER=mock
DATABASE_URL=sqlite:///./data/triage.db
```

### 3. Запуск

```powershell
uvicorn app.main:app --reload
```

Проверка:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Откройте в браузере `http://127.0.0.1:8000/` — веб-интерфейс демо.

### 4. Пример запроса к POST /triage

```powershell
$body = @{
  text = "Форма обратной связи не работает"
  channel = "form"
  client_id = "student-1"
} | ConvertTo-Json -Compress

Invoke-RestMethod http://127.0.0.1:8000/triage -Method Post -Body $body -ContentType "application/json"
```

Пример ответа:

```json
{
  "category": "support",
  "draft_reply": "Спасибо за обращение. Опишите, пожалуйста, что именно не работает...",
  "confidence": "medium",
  "escalate": false
}
```

### 5. Пример запроса к POST /lead

`POST /lead` — полный алиас `/triage` (для совместимости с формулировкой задания).

```powershell
Invoke-RestMethod http://127.0.0.1:8000/lead -Method Post -Body $body -ContentType "application/json"
```

## Docker

```powershell
docker compose up --build
```

Сервис будет доступен на `http://localhost:8000`. База и spool монтируются в `./data` и `./spool`.

## Деплой на VPS (okihit.online)

```bash
# На сервере в /opt/triage
sudo bash deploy/install-on-server.sh
# или для HTTPS после настройки DNS:
sudo bash deploy/setup-https.sh
```

Используется `docker-compose.prod.yml` (порт `127.0.0.1:8001`) + nginx reverse proxy.

## Где смотреть SQLite и логи

**SQLite (аудит):**

```powershell
sqlite3 .\data\triage.db "SELECT id, created_at, client_id, channel, category, confidence, escalate, substr(draft_reply,1,60) FROM tickets ORDER BY id DESC LIMIT 5;"
```

Таблица `tickets`:

| Поле | Описание |
|---|---|
| id | ID записи |
| created_at | Время создания |
| client_id | Идентификатор клиента |
| channel | email / form / chat |
| text | Текст обращения |
| category | billing / support / complaint / other |
| confidence | high / medium / low |
| escalate | 0 / 1 |
| draft_reply | Черновик ответа |
| error | Ошибка LLM/валидации (если была) |

**Emergency spool** (если SQLite недоступен): `./spool/emergency.jsonl`

**Логи uvicorn** — в консоли, где запущен сервер.

## Контракт API

### POST /triage

**Вход:**

```json
{
  "text": "Не пришёл чек за оплату",
  "channel": "email",
  "client_id": "user-42"
}
```

**Выход:**

```json
{
  "category": "billing",
  "draft_reply": "...",
  "confidence": "low",
  "escalate": true
}
```

### GET /tickets?limit=10

Список последних обращений для демо-UI (аудит).

## Надёжность и безопасность

- **Эскалация:** при сбое LLM, невалидном JSON, prompt injection, низкой уверенности → `escalate=true`, `draft_reply="Ваше обращение передано оператору."`
- **Лимиты:** `RATE_LIMIT_CLIENT_PER_MINUTE` (по умолчанию 10/мин на `client_id`)
- **Температура LLM:** `LLM_TEMPERATURE=0.2` (меньше «фантазии»)
- **Опциональная авторизация:** `REQUIRE_API_AUTH=true` + `Authorization: Bearer <API_KEYS>`

Подробнее: [SECURITY.md](SECURITY.md)

## Тесты

```powershell
pytest
```

Тесты используют mock LLM — внешние API не нужны.

## Демо для сдачи (путь B)

1. `uvicorn app.main:app --reload`
2. Открыть `http://127.0.0.1:8000/` или отправить запрос в `POST /triage`
3. Показать запись в SQLite: `SELECT ... FROM tickets`
4. Записать видео 2–3 мин: **запрос → ответ → запись в БД** + скрин логов uvicorn

## Итог

- **Проблема:** хаос в обращениях и нагрузка на менеджеров.
- **Решение:** API + LLM + журналирование + эскалация при сбоях + Docker + веб-UI.
- **Результат:** быстрее реакция, ниже нагрузка, прозрачная история.

## v2 (что улучшить)

- RAG / база знаний
- Prometheus-метрики и алерты
- PostgreSQL + Redis в продакшене
