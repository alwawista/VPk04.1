#!/usr/bin/env bash
# Привязка okihit.online → triage в Docker (порт 8001) + HTTPS
# Запуск на VPS: bash /opt/triage/deploy/setup-https.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/triage}"
DOMAIN="okihit.online"
EMAIL="${CERTBOT_EMAIL:-vedernikov75@mail.ru}"
SERVER_IP="95.81.115.164"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запустите от root: sudo bash deploy/setup-https.sh"
  exit 1
fi

echo "=== Проверка DNS ==="
DNS_IP="$(dig +short "${DOMAIN}" A @ns1.reg.ru | tail -n1)"
if [[ -z "${DNS_IP}" ]]; then
  DNS_IP="$(dig +short "${DOMAIN}" A | tail -n1)"
fi
if [[ "${DNS_IP}" != "${SERVER_IP}" ]]; then
  echo "ВНИМАНИЕ: ${DOMAIN} сейчас указывает на ${DNS_IP:-<пусто>}, а VPS: ${SERVER_IP}"
  echo "В панели регистратора домена задайте A-запись:"
  echo "  okihit.online     -> ${SERVER_IP}"
  echo "  www.okihit.online -> ${SERVER_IP}"
  echo ""
  echo "Без этого HTTPS (Let's Encrypt) не выпустится."
  echo "Продолжаем настройку nginx..."
fi

echo "=== Проверка triage в Docker ==="
if ! curl -fsS "http://127.0.0.1:8001/health" >/dev/null; then
  echo "Сервис на :8001 не отвечает. Сначала:"
  echo "  cd ${APP_DIR} && docker compose -f docker-compose.prod.yml up -d --build"
  exit 1
fi

echo "=== nginx ==="
apt-get install -y nginx certbot python3-certbot-nginx

NGINX_CONF="/etc/nginx/nginx.conf"
if ! grep -q "server_names_hash_bucket_size" "${NGINX_CONF}"; then
  sed -i '/http {/a\    server_names_hash_bucket_size 64;' "${NGINX_CONF}"
fi

install -m 644 "${APP_DIR}/deploy/nginx/okihit.online.conf" /etc/nginx/sites-available/okihit.online
ln -sf /etc/nginx/sites-available/okihit.online /etc/nginx/sites-enabled/okihit.online
nginx -t
systemctl enable nginx
systemctl reload nginx

echo "=== Локальная проверка прокси ==="
curl -fsS -H "Host: ${DOMAIN}" "http://127.0.0.1/health" | head -c 200
echo ""

if [[ "${DNS_IP}" == "${SERVER_IP}" ]]; then
  echo "=== SSL (Let's Encrypt) ==="
  certbot --nginx -d "${DOMAIN}" -d "www.${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" --redirect
  systemctl reload nginx
  echo ""
  echo "Готово: https://${DOMAIN}/"
else
  echo ""
  echo "nginx настроен. После смены DNS на ${SERVER_IP} выполните:"
  echo "  certbot --nginx -d ${DOMAIN} -d www.${DOMAIN} --redirect"
fi
