#!/usr/bin/env bash
# После деплоя: импорт 60 примеров и экспорт лога откликов (внутри Docker).
# Запуск на VPS: sudo bash deploy/post_deploy.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/triage}"
COMPOSE_FILE="docker-compose.prod.yml"
SERVICE="triage"

cd "${APP_DIR}"
mkdir -p data spool reports

echo "=== Пересборка и запуск контейнера ==="
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "=== Импорт tickets_60.csv в SQLite ==="
docker compose -f "${COMPOSE_FILE}" exec -T "${SERVICE}" \
  python scripts/seed_from_csv.py --clear

echo "=== Экспорт лога откликов в reports/ ==="
docker compose -f "${COMPOSE_FILE}" exec -T "${SERVICE}" \
  python scripts/export_response_log.py

echo ""
echo "Готово."
echo "  UI:        https://okihit.online/"
echo "  Health:    https://okihit.online/health"
echo "  Swagger:   https://okihit.online/docs"
echo "  Tickets:   https://okihit.online/tickets?limit=60"
echo "  Лог (CSV): ${APP_DIR}/reports/response_log.csv"
echo "  Лог (HTML): ${APP_DIR}/reports/response_log.html"
echo ""
echo "Проверка:"
curl -fsS "http://127.0.0.1:8001/health" | head -c 200 || true
echo ""
