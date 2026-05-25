#!/usr/bin/env bash
# Render build script. Runs on every deploy.
set -euo pipefail

echo "==> Installing backend Python deps"
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "==> Building frontend"
pushd frontend > /dev/null
npm ci --no-audit --no-fund
npm run build
popd > /dev/null

echo "==> Django migrate + collectstatic + seed"
pushd backend > /dev/null
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py seed_tenant
python manage.py load_lookups
popd > /dev/null

echo "==> Build complete"
