#!/usr/bin/env bash
# Деплой Support Triage на VPS (Ubuntu/Debian)
# Сервер: 95.81.115.164
# Домен:  https://okihit.online
#
# Перед запуском:
# 1) DNS A-запись: okihit.online -> 95.81.115.164
# 2) DNS A-запись: www.okihit.online -> 95.81.115.164 (опционально)
# 3) Скопируйте проект на сервер в /opt/triage (НЕ в /opt/okihit — там другой проект)
# 4) Создайте /opt/triage/.env из EnvExample

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/triage}"
DOMAIN="okihit.online"
EMAIL="${CERTBOT_EMAIL:-}"
TRIAGE_PORT="8001"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запустите от root: sudo bash deploy/install-on-server.sh"
  exit 1
fi

if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo "Создайте ${APP_DIR}/.env (скопируйте из EnvExample и заполните)."
  exit 1
fi

if ss -tlnp | grep -q ":${TRIAGE_PORT} "; then
  echo "Порт ${TRIAGE_PORT} уже занят — пропускаем проверку (контейнер уже запущен)."
fi

apt-get update
apt-get install -y ca-certificates curl gnupg nginx certbot python3-certbot-nginx

if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

mkdir -p /var/www/certbot
NGINX_CONF="/etc/nginx/nginx.conf"
if ! grep -q "server_names_hash_bucket_size" "${NGINX_CONF}"; then
  sed -i '/http {/a\    server_names_hash_bucket_size 64;' "${NGINX_CONF}"
fi
install -m 644 "${APP_DIR}/deploy/nginx/okihit.online.conf" /etc/nginx/sites-available/okihit.online
ln -sf /etc/nginx/sites-available/okihit.online /etc/nginx/sites-enabled/okihit.online
# Не трогаем okihit.ru и другие сайты
nginx -t
systemctl enable nginx
systemctl restart nginx

cd "${APP_DIR}"
docker compose -f docker-compose.prod.yml up -d --build

if [[ -n "${EMAIL}" ]]; then
  certbot --nginx -d "${DOMAIN}" -d "www.${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" --redirect
  systemctl reload nginx
else
  echo ""
  echo "Docker запущен. Для HTTPS (Let's Encrypt) выполните:"
  echo "  sudo certbot --nginx -d ${DOMAIN} -d www.${DOMAIN} --redirect"
  echo "  (certbot добавит SSL и редирект HTTP -> HTTPS)"
  echo ""
fi

echo ""
echo "Готово. Проверка:"
echo "  curl -I http://127.0.0.1:${TRIAGE_PORT}/health"
echo "  curl -I https://${DOMAIN}/health"
echo ""
