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

Сервер: `95.81.115.164` · домен: **https://okihit.online** · каталог на VPS: `/opt/triage`

### Первый запуск (с нуля)

**1. DNS** (у регистратора):

- `okihit.online` → A → `95.81.115.164`
- `www.okihit.online` → A → `95.81.115.164`

**2. На VPS (SSH):**

```bash
sudo apt-get update
sudo apt-get install -y git

sudo mkdir -p /opt/triage
sudo git clone https://github.com/alwawista/VPk04.1.git /opt/triage
cd /opt/triage

cp EnvExample .env
nano .env   # для демо: LLM_PROVIDER=mock
```

**3. Установка nginx + Docker + HTTPS:**

```bash
sudo CERTBOT_EMAIL=your@email.com bash deploy/install-on-server.sh
# или без SSL сразу:
sudo bash deploy/install-on-server.sh
sudo bash deploy/setup-https.sh
```

**4. Импорт 60 примеров + экспорт лога (как локально):**

```bash
sudo bash deploy/post_deploy.sh
```

Скрипт внутри контейнера:

- `seed_from_csv.py --clear` → 60 записей в SQLite
- `export_response_log.py` → файлы в `/opt/triage/reports/`

**5. Проверка в браузере:**

| Что | URL |
|-----|-----|
| Демо UI | https://okihit.online/ |
| Health | https://okihit.online/health |
| Swagger | https://okihit.online/docs |
| Тикеты JSON | https://okihit.online/tickets?limit=60 |

### Обновление после `git push`

На VPS:

```bash
sudo bash /opt/triage/deploy/update_from_git.sh
```

Или вручную:

```bash
cd /opt/triage
git pull
sudo bash deploy/post_deploy.sh
```

### Скачать лог откликов с VPS на ПК

```powershell
scp user@95.81.115.164:/opt/triage/reports/response_log.csv .
scp user@95.81.115.164:/opt/triage/reports/response_log.html .
```

### Логи Docker на сервере

```bash
cd /opt/triage
docker compose -f docker-compose.prod.yml logs -f --tail=50
```

Используется `docker-compose.prod.yml` (порт `127.0.0.1:8001` → nginx → `okihit.online`).

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

### Импорт 60 примеров в историю (демо UI)

В репозитории есть `data/samples/tickets_60.csv` — готовые обращения с категориями и черновиками.

```powershell
python scripts/seed_from_csv.py --clear
```

- `--clear` — очистить таблицу перед импортом (без флага строки добавляются к существующим)
- `--csv путь\к\файлу.csv` — другой файл

После импорта откройте http://127.0.0.1:8000/ — в блоке «История обращений» появятся записи (API `GET /tickets` возвращает последние 10; увеличьте `?limit=60` при необходимости).

## Сдача: лог откликов (таблица + скрины / ссылки)

### 1. Подготовить таблицу

Убедитесь, что в БД есть записи (импорт или живые `POST /triage`):

```powershell
python scripts/seed_from_csv.py --clear
# или отправьте несколько запросов в /triage — они тоже пишутся в tickets
```

Экспорт для отчёта:

```powershell
python scripts/export_response_log.py
```

Создаёт в папке `reports/`:

| Файл | Для чего |
|------|----------|
| `response_log.csv` | Excel / Google Sheets, приложение к работе |
| `response_log.html` | открыть в браузере → **скрин всей таблицы** |
| `response_log.md` | вставить в документ или конвертировать в PDF |

Колонки: `id`, `created_at`, `client_id`, `channel`, `text`, `category`, `confidence`, `escalate`, `draft_reply`, `error`.

### 2. Скриншоты (минимум 4)

| № | Что снять | Зачем |
|---|-----------|--------|
| 1 | `reports/response_log.html` или Excel с `response_log.csv` | **таблица лога** |
| 2 | https://okihit.online/ — форма + результат | запрос → ответ в UI |
| 3 | https://okihit.online/docs → POST `/triage` | JSON-контракт |
| 4 | `docker compose logs` на VPS или `reports/response_log.html` | технический лог / таблица |

### 3. Ссылки для отчёта

**Публичный деплой (okihit.online):**

| Объект | URL |
|--------|-----|
| Репозиторий | https://github.com/alwawista/VPk04.1 |
| Демо UI | https://okihit.online/ |
| Swagger | https://okihit.online/docs |
| Health | https://okihit.online/health |
| Тикеты JSON | https://okihit.online/tickets?limit=60 |

**Локально (разработка):**

| Объект | URL |
|--------|-----|
| Демо UI | http://127.0.0.1:8000/ |
| Swagger | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/health |

Таблица лога: `reports/response_log.csv` / `.html` (локально или `/opt/triage/reports/` на VPS).

### 4. Пример текста для пояснительной записки

> Лог откликов хранится в SQLite (`tickets`). Каждый `POST /triage` сохраняет вход (text, channel, client_id) и ответ (category, draft_reply, confidence, escalate). Экспорт: `python scripts/export_response_log.py`. Приложены таблица (CSV/HTML) и скриншоты UI, Swagger и логов uvicorn.

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
