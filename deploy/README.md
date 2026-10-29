# RULGuard on a VPS (Docker Compose + host nginx)

| Host | Serves |
|---|---|
| `DOMAIN` | landing site (`web/dist`) + `/api` |
| `DOMAIN/upload`, `/trajectory`, ... | Next.js analyzer (`frontend/`), every path not listed here |
| `DOMAIN/lab/` | Streamlit research dashboard (public; `RULGUARD_LAB_READONLY=1` turns off server-path analysis) |
| `app.DOMAIN`, `lab.DOMAIN` | 301 redirects into the one site, so old links keep working |

Containers (`compose.yaml`) bind to 127.0.0.1 only; host nginx terminates TLS (certbot).

## First install
```sh
rsync the repo (minus /datasets /data /context /.venv node_modules) to /opt/rulguard/app
python3 deploy/fetch_models.py artifacts/models/manifest.json /opt/rulguard/models   # sha256-verified
rsync data/interim/femto/ -> /opt/rulguard/datasets/femto                              # raw explorer, read-only
cp deploy/.env.example deploy/.env && chmod 600 deploy/.env                            # fill GROQ_API_KEY
cd deploy && docker compose up -d --build
sed "s/DOMAIN/<your domain>/g" nginx/rulguard.conf > /etc/nginx/sites-available/rulguard
certbot --nginx -d DOMAIN -d app.DOMAIN -d lab.DOMAIN --redirect
```
Landing build: `npm run build` in `web/` (links are same-domain paths),
then rsync `web/dist/` to `/opt/rulguard/site/`.

## Operate
- Update after a change: commit, then `deploy/update.sh`. It pushes to GitHub (backup), sends the
  committed files to the server, rebuilds the containers and the landing page, and prints health.
  The server is not connected to GitHub, so a push alone never changes the live site.
- Set the Groq key without echoing it:
  `ssh -t <host> 'read -rsp "Groq key: " k; sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$k|" /opt/rulguard/app/deploy/.env; cd /opt/rulguard/app/deploy && docker compose up -d api dashboard'`
- Logs: `docker compose logs -f api` (rotated, 5x10MB per service)
- Backups: `backup.sh` nightly 03:30 via `/etc/cron.d/rulguard-backup` -> `/opt/rulguard/backups` (14 days)
- Restart policy `unless-stopped` + docker/nginx enabled at boot.
