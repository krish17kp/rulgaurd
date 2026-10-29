#!/bin/sh
# Nightly: prediction-history volume + server env + nginx config. Keeps 14 days.
set -eu
dest=/opt/rulguard/backups; stamp=$(date +%F)
docker run --rm -v rulguard_rulguard-data:/data:ro -v "$dest":/out alpine \
  tar czf "/out/data-$stamp.tgz" -C /data .
tar czf "$dest/config-$stamp.tgz" /opt/rulguard/app/deploy/.env /etc/nginx/sites-available/rulguard /etc/letsencrypt 2>/dev/null || true
chmod 600 "$dest"/*-"$stamp".tgz
find "$dest" -name '*.tgz' -mtime +14 -delete
