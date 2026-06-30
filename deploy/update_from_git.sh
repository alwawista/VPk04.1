#!/usr/bin/env bash
# Обновление кода с GitHub и повторный post-deploy.
# На VPS: sudo bash deploy/update_from_git.sh

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/triage}"
REPO_URL="${REPO_URL:-https://github.com/alwawista/VPk04.1.git}"
BRANCH="${BRANCH:-main}"

cd "${APP_DIR}"

if [[ ! -d .git ]]; then
  echo "Клонируйте репозиторий в ${APP_DIR}:"
  echo "  git clone ${REPO_URL} ${APP_DIR}"
  exit 1
fi

echo "=== git pull ==="
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull origin "${BRANCH}"

bash "${APP_DIR}/deploy/post_deploy.sh"
