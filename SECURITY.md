# Безопасность Support Triage MVP

## Секреты

- Ключи LLM и API хранятся только в `.env` (не коммитить).
- `load_dotenv()` подключается в `app/config.py` при старте.
- Шаблон переменных — в `EnvExample`.

## Аутентификация

По умолчанию `REQUIRE_API_AUTH=false` (как в задании). Для продакшена:

```env
REQUIRE_API_AUTH=true
API_KEYS=your-secret-key,another-key
```

Клиент передаёт заголовок: `Authorization: Bearer your-secret-key`.

## Rate limiting

- **client_id** — 10 запросов/мин (настраивается `RATE_LIMIT_CLIENT_PER_MINUTE`)
- Дополнительно: лимиты по IP, глобальный и по API-ключу
- In-memory лимитер сбрасывается при рестарте; для кластера — `REDIS_URL`

## Валидация и безопасность LLM

- Pydantic: длина `text` 1–2000, enum `channel`, паттерн `client_id`
- Лимит тела запроса: `MAX_REQUEST_BODY_BYTES=8192`
- Детекция prompt injection → эскалация оператору
- Пост-валидация ответа LLM: 1–6 предложений, без выдуманных фактов/сумм/дат
- Низкая уверенность без эскалации → принудительная эскалация
- Сбой LLM / невалидный JSON → `escalate=true`, шаблон оператору

## Аудит и отказоустойчивость

- Все обращения пишутся в SQLite (`tickets`)
- При недоступности БД — emergency spool (`SPOOL_PATH`, JSONL)

## Рекомендации для продакшена

- HTTPS перед приложением (nginx / reverse proxy)
- `REQUIRE_API_AUTH=true`
- PostgreSQL вместо SQLite
- Redis для rate limit
- Мониторинг логов и spool-файла
