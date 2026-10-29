#!/usr/bin/env bash
# Back up to GitHub and update the live site in one go. Run from anywhere after committing:
#   deploy/update.sh            (HOST and DOMAIN override the defaults below)
set -euo pipefail
HOST=${HOST:-rulvps}
DOMAIN=${DOMAIN:-forevue.tech}
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Uncommitted changes. Commit first, so GitHub and the server get the same code." >&2
  exit 1
fi

echo "== 1/4 GitHub backup"
git push origin HEAD

echo "== 2/4 Code to the server (committed files only; raw datasets stay local)"
git ls-files | grep -v '^datasets/' | rsync -az --files-from=- ./ "$HOST:/opt/rulguard/app/"

echo "== 3/4 Rebuild containers (unchanged images are reused)"
ssh "$HOST" 'cd /opt/rulguard/app/deploy && docker compose up -d --build'

echo "== 4/4 Landing page"
(cd web && npm ci --silent && npm run build >/dev/null)
rsync -az --delete web/dist/ "$HOST:/opt/rulguard/site/"

echo "== Health"
for _ in $(seq 30); do
  ssh "$HOST" 'cd /opt/rulguard/app/deploy && ! docker compose ps --format "{{.Status}}" | grep -qv "(healthy)"' && break
  sleep 5
done
for u in "https://$DOMAIN/" "https://$DOMAIN/api/health" "https://$DOMAIN/upload" "https://$DOMAIN/results" "https://$DOMAIN/api/lab/signals"; do
  echo "$(curl -s -o /dev/null -w '%{http_code}' "$u") $u"
done
